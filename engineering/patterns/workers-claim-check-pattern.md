# Claim Check Pattern for Large Payloads in Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You try to enqueue a message to a Cloudflare Queue and hit the **128 KB per-message size limit**. The payload — a full order export, a user-uploaded document, a batch of telemetry events — simply does not fit. Splitting it into smaller messages breaks semantic atomicity. You need a way to pass large payloads through a queue without violating the size constraint.

---

## Context

The [Claim Check pattern](https://www.enterpriseintegrationpatterns.com/patterns/messaging/StoreInLibrary.html) replaces a large message body with a lightweight **claim ticket** (a reference to where the full payload is stored). The producer stores the payload in an object store (R2), enqueues a small ticket containing the storage key, and the consumer retrieves the full payload from R2 using the key.

This pattern also reduces queue infrastructure costs (charged per byte on most platforms), decouples payload lifecycle from message lifecycle, and allows the same payload to be referenced by multiple consumers.

---

## Solution

```typescript
// src/types.ts
export interface Env {
  PAYLOAD_STORE: R2Bucket;
  PROCESSING_QUEUE: Queue<ClaimTicket>;
  PAYLOAD_TTL_SECONDS: string; // e.g. "86400" (1 day)
}

export interface ClaimTicket {
  ticketId: string;       // UUID — unique per enqueue
  r2Key: string;          // Key in R2 where payload is stored
  payloadSize: number;    // Original payload size in bytes
  contentType: string;    // MIME type of the stored payload
  producer: string;       // Who produced the message
  enqueuedAt: string;     // ISO-8601
  expiresAt: string;      // ISO-8601 — when to clean up R2 object
  metadata: Record<string, string>; // Domain-specific routing hints
}

export interface FullPayload {
  // Example domain payload — replace with your own type
  exportId: string;
  records: unknown[];
}

// src/producer.ts
import { Env, ClaimTicket, FullPayload } from './types';

const QUEUE_MAX_BYTES = 128 * 1024; // 128 KB

/**
 * Enqueue a potentially large payload.
 * Small payloads (< QUEUE_MAX_BYTES) are inlined as JSON in the queue message.
 * Large payloads are stored in R2 and replaced with a claim ticket.
 */
export async function enqueuePayload(
  env: Env,
  payload: FullPayload,
  producer: string,
  metadata: Record<string, string> = {},
): Promise<{ mode: 'inline' | 'claim-check'; ticketId: string }> {
  const ticketId = crypto.randomUUID();
  const serialized = JSON.stringify(payload);
  const byteSize = new TextEncoder().encode(serialized).byteLength;

  if (byteSize < QUEUE_MAX_BYTES) {
    // Small enough to inline — no R2 needed
    await env.PROCESSING_QUEUE.send({ ticketId, inline: true, payload } as any);
    return { mode: 'inline', ticketId };
  }

  // Large payload: store in R2 and send claim ticket
  const r2Key = `payloads/${producer}/${ticketId}.json`;
  const ttlSeconds = Number(env.PAYLOAD_TTL_SECONDS ?? 86400);
  const expiresAt = new Date(Date.now() + ttlSeconds * 1000).toISOString();

  await env.PAYLOAD_STORE.put(r2Key, serialized, {
    httpMetadata: { contentType: 'application/json' },
    customMetadata: {
      ticketId,
      producer,
      expiresAt,
      payloadSize: String(byteSize),
    },
  });

  console.log(JSON.stringify({
    event: 'claim_check_stored',
    ticketId,
    r2Key,
    byteSize,
    expiresAt,
  }));

  const ticket: ClaimTicket = {
    ticketId,
    r2Key,
    payloadSize: byteSize,
    contentType: 'application/json',
    producer,
    enqueuedAt: new Date().toISOString(),
    expiresAt,
    metadata,
  };

  // The ticket is tiny — well within the 128 KB limit
  await env.PROCESSING_QUEUE.send(ticket);

  return { mode: 'claim-check', ticketId };
}

// src/consumer.ts
import { Env, ClaimTicket, FullPayload } from './types';

export default {
  async queue(batch: MessageBatch<ClaimTicket>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const ticket = message.body;

      try {
        const payload = await retrievePayload(env, ticket);
        await processPayload(payload, ticket);
        // Clean up R2 after successful processing
        await env.PAYLOAD_STORE.delete(ticket.r2Key);
        console.log(JSON.stringify({
          event: 'claim_check_consumed',
          ticketId: ticket.ticketId,
          r2Key: ticket.r2Key,
        }));
        message.ack();
      } catch (err) {
        if (err instanceof PayloadMissingError) {
          // R2 object is gone (expired or never written) — cannot recover.
          // Ack the message to avoid infinite retry, and log for investigation.
          console.error(JSON.stringify({
            event: 'claim_check_payload_missing',
            ticketId: ticket.ticketId,
            r2Key: ticket.r2Key,
            error: String(err),
          }));
          message.ack(); // Dead-letter or alert here in production
        } else {
          console.error(JSON.stringify({
            event: 'claim_check_processing_failed',
            ticketId: ticket.ticketId,
            error: String(err),
          }));
          message.retry();
        }
      }
    }
  },
};

class PayloadMissingError extends Error {
  constructor(r2Key: string) {
    super(`R2 object not found: ${r2Key}`);
    this.name = 'PayloadMissingError';
  }
}

async function retrievePayload(env: Env, ticket: ClaimTicket): Promise<FullPayload> {
  // Check expiry before fetching
  if (new Date(ticket.expiresAt) < new Date()) {
    throw new PayloadMissingError(ticket.r2Key);
  }

  const object = await env.PAYLOAD_STORE.get(ticket.r2Key);

  if (!object) {
    throw new PayloadMissingError(ticket.r2Key);
  }

  const text = await object.text();
  return JSON.parse(text) as FullPayload;
}

async function processPayload(payload: FullPayload, ticket: ClaimTicket): Promise<void> {
  console.log(JSON.stringify({
    event: 'processing_payload',
    ticketId: ticket.ticketId,
    recordCount: Array.isArray(payload.records) ? payload.records.length : 'n/a',
  }));
  // --- Your domain processing logic here ---
}

// src/cleanup.ts — scheduled Worker to remove expired R2 objects
export async function cleanupExpiredPayloads(env: Env): Promise<void> {
  const now = new Date();
  let cursor: string | undefined;
  let deleted = 0;

  do {
    const listing = await env.PAYLOAD_STORE.list({
      prefix: 'payloads/',
      cursor,
      limit: 100,
    });

    const toDelete: string[] = [];

    for (const obj of listing.objects) {
      const expiresAt = obj.customMetadata?.expiresAt;
      if (expiresAt && new Date(expiresAt) < now) {
        toDelete.push(obj.key);
      }
    }

    if (toDelete.length > 0) {
      await Promise.all(toDelete.map((key) => env.PAYLOAD_STORE.delete(key)));
      deleted += toDelete.length;
      console.log(JSON.stringify({ event: 'expired_payloads_deleted', count: toDelete.length }));
    }

    cursor = listing.truncated ? listing.cursor : undefined;
  } while (cursor);

  console.log(JSON.stringify({ event: 'cleanup_complete', totalDeleted: deleted }));
}

// src/worker.ts — entry point wiring
import { enqueuePayload } from './producer';
import { cleanupExpiredPayloads } from './cleanup';
import { Env, FullPayload } from './types';

export { default as QueueConsumer } from './consumer';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'POST' && new URL(request.url).pathname === '/enqueue') {
      const body = await request.json<{ exportId: string; records: unknown[] }>();
      const result = await enqueuePayload(
        env,
        body,
        'api',
        { source: request.headers.get('X-Source') ?? 'unknown' },
      );
      return Response.json(result);
    }
    return new Response('Not found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await cleanupExpiredPayloads(env);
  },
};
```

```jsonc
// wrangler.toml (relevant excerpt)
[[r2_buckets]]
binding = "PAYLOAD_STORE"
bucket_name = "claim-check-payloads"

[[queues.producers]]
binding = "PROCESSING_QUEUE"
queue = "large-payload-processing"

[[queues.consumers]]
queue = "large-payload-processing"
max_batch_size = 10
max_batch_timeout = 10
max_retries = 3
dead_letter_queue = "large-payload-processing-dlq"

[triggers]
crons = ["0 2 * * *"] // Daily cleanup at 02:00 UTC

[vars]
PAYLOAD_TTL_SECONDS = "86400"
```

---

## Implementation Details

**Size detection** uses `TextEncoder` to get the actual byte length of the serialized JSON, not the character count. For ASCII content these are the same, but multi-byte Unicode characters count for more bytes than characters.

**R2 key naming** follows a `payloads/{producer}/{ticketId}.json` convention. The `producer` prefix enables per-producer cleanup and access control policies. The `.json` suffix allows serving directly from R2 with the correct content type if needed.

**Custom metadata** on the R2 object stores `expiresAt`, `ticketId`, and `payloadSize`. This enables the cleanup job to list and delete expired objects without fetching their bodies, and the consumer to detect expiry before downloading.

**Inline fallback** for small payloads keeps the producer API uniform — callers always call `enqueuePayload`; the routing decision (inline vs. claim check) is internal. This avoids two code paths in the consumer.

**Post-processing deletion** removes the R2 object immediately after successful processing, rather than waiting for the TTL-based cleanup. The scheduled cleanup is a safety net for objects whose consumer messages were lost or whose consumer crashed after ack but before deletion.

**TTL-based R2 cleanup** runs daily. R2 does not natively support object TTL, so the cleanup Worker lists objects, reads `expiresAt` from custom metadata, and deletes expired ones. Use a short TTL (1 day) relative to your queue's maximum retention period to avoid accumulating orphaned objects.

---

## Anti-patterns

- **Storing the payload in the queue message body and base64-encoding it.** Base64 increases size by ~33%; a 90 KB payload becomes 120 KB, still within the limit but wasting capacity. The claim check is the right tool for large payloads.
- **Using a random R2 key with no TTL metadata.** Without `expiresAt` in custom metadata, the cleanup job cannot determine which objects to delete without fetching every object's body.
- **Deleting the R2 object before the message is acked.** If the consumer crashes after deletion but before ack, the Queue redelivers the message but the payload is gone. Always delete after a successful ack or at the end of processing inside the same `try` block after `processPayload`.
- **Setting too long a TTL.** A 30-day TTL means orphaned objects accumulate for 30 days. Balance recovery time (how long can a consumer be down?) against storage cost.

---

## Gotchas

- **R2 `list()` returns at most 1000 objects per call.** Use the `cursor` returned in the listing response to paginate through all objects during cleanup.
- **R2 object size limit is 5 TB.** There is no practical upper bound for this pattern, but very large objects (> 1 GB) should be uploaded with R2's multipart upload API rather than a single `put()`.
- **Queue message ordering is not guaranteed.** If two messages reference the same R2 key (unlikely with UUIDs), they could race on deletion. Using per-ticket UUIDs as R2 keys eliminates this risk.
- **`object.text()` loads the entire object into memory.** For very large payloads (hundreds of MB), stream the R2 body with `object.body` (a `ReadableStream`) rather than calling `.text()` to avoid Worker memory limits.
- **Inline and claim-check messages share the same queue.** The consumer must handle both shapes. In the example above, add a discriminant field (`inline: true` vs. a `r2Key` field) and branch accordingly.

---

## Verification

```bash
# Enqueue a small payload (inline path)
curl -X POST https://your-worker.workers.dev/enqueue \
  -H 'Content-Type: application/json' \
  -d '{"exportId": "e-001", "records": [{"id": 1}]}'
# Expect: {"mode": "inline", "ticketId": "..."}

# Enqueue a large payload (claim-check path)
# Generate ~200 KB of JSON
PAYLOAD=$(node -e "console.log(JSON.stringify({exportId:'e-002', records: Array.from({length:5000},(_,i)=>({id:i,data:'x'.repeat(40)}))}))")
curl -X POST https://your-worker.workers.dev/enqueue \
  -H 'Content-Type: application/json' \
  -d "$PAYLOAD"
# Expect: {"mode": "claim-check", "ticketId": "..."}

# Verify the R2 object was created
wrangler r2 object get claim-check-payloads payloads/api/<ticketId>.json

# After queue consumer processes, R2 object should be deleted
wrangler r2 object get claim-check-payloads payloads/api/<ticketId>.json
# Expect: NoSuchKey error
```

---

## Related

- `workers-inbox-outbox-pattern.md` — outbox events may exceed 128 KB and need claim check
- `workers-compensating-transaction-pattern.md` — saga steps that pass large payloads between services
- Cloudflare Docs: [R2 Storage](https://developers.cloudflare.com/r2/)
- Cloudflare Docs: [Workers Queues](https://developers.cloudflare.com/queues/)

---

## Sources

- Claim Check pattern — Enterprise Integration Patterns: https://www.enterpriseintegrationpatterns.com/patterns/messaging/StoreInLibrary.html
- Cloudflare R2 documentation: https://developers.cloudflare.com/r2/
- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
- Cloudflare Queues limits: https://developers.cloudflare.com/queues/platform/limits/
