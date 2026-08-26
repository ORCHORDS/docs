# Claim Check Pattern with R2 and Queues

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Queue message contains a large payload — a multi-megabyte webhook body, a bulk CSV
upload, a generated PDF, or a rich AI response — that exceeds the Queue message size
limit (currently 128 KB). Alternatively, the same large object needs to be processed
by several independent consumers; duplicating it in every message wastes bandwidth and
storage. You need to decouple the *reference* to the data from the *data itself*.

## Context

The Claim Check pattern (also called "Reference-based messaging") stores the large
payload out-of-band in a durable object store (R2 on Cloudflare) and sends only a
lightweight *claim token* — a storage key — through the messaging channel (Queues). A
consumer exchanges the claim token for the actual data when it needs it.

Benefits:
- Queue messages stay well under size limits regardless of payload size.
- Multiple consumers can read the same R2 object independently without re-sending it.
- The producer and consumer are decoupled: the producer can write to R2 before the
  consumer is ready, and the consumer can retry without the producer resending bytes.
- Large objects can be deleted from R2 after all consumers have acknowledged them, giving
  explicit lifecycle control.

This pattern is complementary to the Outbox pattern (for reliable publish) and the
Inbox pattern (for idempotent consumption).

## Storing the Payload (Producer Side)

```typescript
// producer.ts
interface ClaimCheckMessage {
  claimKey: string;       // R2 object key
  contentType: string;
  byteLength: number;
  metadata: Record<string, string>;
  producedAt: string;
}

export async function storeAndEnqueue(
  payload: ArrayBuffer | ReadableStream,
  contentType: string,
  metadata: Record<string, string>,
  r2: R2Bucket,
  queue: Queue<ClaimCheckMessage>,
): Promise<string> {
  // Use a time-sortable key: epoch-ms + random suffix avoids hot-spot partitioning
  const claimKey = `claims/${Date.now()}-${crypto.randomUUID()}`;

  const body = payload instanceof ReadableStream
    ? await new Response(payload).arrayBuffer()
    : payload;

  await r2.put(claimKey, body, {
    httpMetadata: { contentType },
    customMetadata: metadata,
  });

  const message: ClaimCheckMessage = {
    claimKey,
    contentType,
    byteLength: body.byteLength,
    metadata,
    producedAt: new Date().toISOString(),
  };

  await queue.send(message, { contentType: 'json' });
  return claimKey;
}
```

## Consuming the Claim (Consumer Side)

```typescript
// consumer.ts
interface Env {
  PAYLOAD_BUCKET: R2Bucket;
  RESULTS_BUCKET: R2Bucket;
  DB: D1Database;
}

export async function handleBatch(
  batch: MessageBatch<ClaimCheckMessage>,
  env: Env,
): Promise<void> {
  for (const msg of batch.messages) {
    const { claimKey, contentType, metadata } = msg.body;

    // Retrieve the actual payload from R2
    const obj = await env.PAYLOAD_BUCKET.get(claimKey);
    if (!obj) {
      // Payload was already deleted or key is wrong — dead-letter the message
      console.error({ claimKey, event: 'claim_not_found' });
      msg.retry({ delaySeconds: 0 });
      continue;
    }

    try {
      const raw = await obj.arrayBuffer();
      const result = await processPayload(raw, contentType, metadata);

      // Write result to a separate R2 key, keeping input and output separate
      const resultKey = `results/${claimKey.replace('claims/', '')}`;
      await env.RESULTS_BUCKET.put(resultKey, JSON.stringify(result), {
        httpMetadata: { contentType: 'application/json' },
      });

      // Record completion in D1
      await env.DB.prepare(
        'INSERT INTO claim_log (claim_key, result_key, processed_at) VALUES (?, ?, ?)',
      )
        .bind(claimKey, resultKey, new Date().toISOString())
        .run();

      msg.ack();
    } catch (err) {
      console.error({ claimKey, err });
      msg.retry({ delaySeconds: 30 });
    }
  }
}

async function processPayload(
  raw: ArrayBuffer,
  contentType: string,
  metadata: Record<string, string>,
): Promise<unknown> {
  // Domain-specific processing — CSV parse, PDF analysis, etc.
  return { bytes: raw.byteLength, contentType, metadata };
}
```

## Claim Lifecycle and Expiry

```typescript
// lifecycle.ts — run as a scheduled Worker (Cron Trigger)
interface ClaimLogRow {
  claim_key: string;
  processed_at: string | null;
  consumer_count: number;
}

export async function expireOldClaims(
  db: D1Database,
  bucket: R2Bucket,
  retentionDays = 7,
): Promise<void> {
  const cutoff = new Date(Date.now() - retentionDays * 86_400_000).toISOString();

  // Find fully processed claims older than the retention window
  const { results } = await db
    .prepare(
      `SELECT claim_key FROM claim_log
       WHERE processed_at < ?
         AND consumer_count >= expected_consumers`,
    )
    .bind(cutoff)
    .all<ClaimLogRow>();

  const keys = results.map((r) => r.claim_key);
  if (keys.length === 0) return;

  // Batch-delete from R2 (max 1000 per call)
  const chunks = chunkArray(keys, 1000);
  for (const chunk of chunks) {
    await bucket.delete(chunk);
  }

  // Remove from D1 log
  const placeholders = keys.map(() => '?').join(',');
  await db
    .prepare(`DELETE FROM claim_log WHERE claim_key IN (${placeholders})`)
    .bind(...keys)
    .run();

  console.log({ event: 'claims_expired', count: keys.length });
}

function chunkArray<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}
```

## Fan-Out with a Single Claim

```typescript
// fanout-producer.ts — one R2 object, multiple consumers via separate queues
interface FanOutMessage {
  claimKey: string;
  topic: string;
}

export async function publishToAll(
  payload: ArrayBuffer,
  topic: string,
  r2: R2Bucket,
  queues: Queue<FanOutMessage>[],
): Promise<void> {
  const claimKey = `claims/${topic}/${Date.now()}-${crypto.randomUUID()}`;
  await r2.put(claimKey, payload);

  // All consumers receive the same R2 key — no payload duplication
  await Promise.all(
    queues.map((q) => q.send({ claimKey, topic }, { contentType: 'json' })),
  );
}
```

## Pre-signed Temporary URL for Direct Client Upload

```typescript
// presign.ts — client uploads directly to R2, Worker receives only the claim key
export async function createUploadClaim(
  filename: string,
  contentType: string,
  r2: R2Bucket,
  queue: Queue<ClaimCheckMessage>,
): Promise<{ uploadUrl: string; claimKey: string }> {
  const claimKey = `uploads/${Date.now()}-${encodeURIComponent(filename)}`;

  // R2 presigned URL — Workers-compatible via the R2 bucket.createMultipartUpload
  // or via signed fetch URLs when using a public bucket + Workers proxy
  // Here we illustrate the envelope: actual presigning uses Cloudflare Access or
  // a signed token validated by a separate upload Worker.
  const uploadUrl = `https://upload.example.com/presign?key=<redacted-secret>

  // Register the pending claim in D1 so the upload Worker can validate the key
  // (actual implementation enqueues only after the upload completes via a callback)
  return { uploadUrl, claimKey };
}
```

## Anti-patterns

- **Putting large payloads in Queue messages anyway** — the 128 KB limit will cause
  `Message too large` errors at runtime. Always route payloads above ~64 KB through R2.
- **Deleting the R2 object before all consumers ack** — if one consumer acks and the
  producer deletes the object, other consumers that retry will get `null` from `r2.get`.
  Track consumer counts in D1 before deleting.
- **Using sequential R2 key prefixes** — `claims/0000001`, `claims/0000002`, etc. creates
  a hot partition in R2. Prefix with a timestamp or UUID segment to spread objects.
- **Not handling `obj === null` in the consumer** — `r2.get` returns `null` for missing
  keys; an unchecked `null.arrayBuffer()` throws and burns a retry slot.
- **Ignoring R2 eventual consistency** — on extremely high write rates, a consumer polling
  immediately after enqueue may see `null` before the object is fully visible. Add a
  short `delaySeconds` on the first Queue send (`{ delaySeconds: 1 }`) if this matters.

## Gotchas

- R2 `put` and Queue `send` are not atomic. If `put` succeeds but `send` fails, the
  payload sits in R2 indefinitely. Pair with a claim registry in D1 that marks keys as
  `pending_enqueue` until the send confirms.
- Queue retries re-execute `r2.get` — ensure the consumer logic is idempotent and that
  a second read of the same R2 object produces the same outcome.
- R2 object sizes returned by `obj.size` are in bytes. Budget your Worker CPU time
  against `byteLength` before processing — very large objects may require streaming.
- Claim keys become the shared contract between producer and consumer. Changing the key
  format is a breaking change if old messages with the old format are still in-flight.

## Verification

```typescript
// Miniflare / Vitest integration test sketch
import { unstable_dev } from 'wrangler';

test('consumer retrieves correct payload from R2', async () => {
  const payload = new TextEncoder().encode('hello world');
  const claimKey = 'claims/test-001';

  // Seed R2
  await r2Mock.put(claimKey, payload);

  // Feed a claim-check message to the consumer
  const result = await handleBatch(
    { messages: [{ body: { claimKey, contentType: 'text/plain', metadata: {}, producedAt: '', byteLength: 11 }, ack: jest.fn(), retry: jest.fn() }] } as any,
    { PAYLOAD_BUCKET: r2Mock, RESULTS_BUCKET: r2ResultsMock, DB: dbMock },
  );

  expect(r2ResultsMock.objects.size).toBe(1);
});
```

## Related

- `dead-letter-queue-pattern.md`
- `fan-out-queues-workers.md`
- `outbox-pattern-d1-reliable-publishing.md`
- `inbox-pattern-idempotent-consumption.md`
- `competing-consumers-workers-queues.md`

## Sources

- Enterprise Integration Patterns — Hohpe & Woolf (Claim Check)
- Cloudflare R2 API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cloudflare Queues — https://developers.cloudflare.com/queues/
