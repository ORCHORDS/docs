# Webhook Reliability Pattern on Cloudflare Workers and Queues

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project receives inbound webhooks from content moderation vendors, payment providers for premium feature toggles, and abuse-detection pipelines. Early implementations processed these synchronously inside the receiving Worker. Downstream processing failures caused the vendor to retry, resulting in duplicate side effects (duplicate moderation actions, duplicate feature activations). Worker timeouts (30 s CPU limit) caused vendor retries for legitimately long operations, making the problem worse.

## Context

Reliable webhook processing requires three independent concerns to be solved separately:

1. **Ingestion** — validate the webhook authenticity, acknowledge immediately with 200, and hand off to a durable queue.
2. **Processing** — consume from the queue idempotently; retry on failure with backoff.
3. **Fan-out** — trigger downstream side effects (mobile push notifications, moderation flags, KV updates) from the queue consumer.

Cloudflare Workers Queues provide at-least-once delivery with configurable retry and delay semantics, making them the correct primitive for the durable hand-off.

## Architecture Overview

```
Vendor (GitHub, Stripe, moderator API)
        │
        │  POST /webhooks/<source>
        ▼
Ingestion Worker
  ├── HMAC signature verification  ← reject 401 if invalid
  ├── Idempotency key extraction   ← X-Webhook-Id or header hash
  ├── Deduplication check (KV)     ← return 200 immediately if already seen
  ├── Enqueue to Workers Queue     ← JSON envelope with metadata
  └── Return 200 OK                ← vendor stops retrying

Workers Queue (at-least-once, 3 retries with backoff)
        │
        ▼
Consumer Worker
  ├── Re-verify idempotency key against D1 processed_events table
  ├── Execute business logic
  ├── Fan out: mobile push (via push Queue), KV update, D1 write
  └── ack() message on success / nack() to trigger retry
```

## HMAC Signature Verification

Each webhook source uses a different signature scheme. The ingestion Worker normalises them into a common `verifySignature` abstraction.

```typescript
// src/webhook/verify.ts
export async function verifyHmacSha256(
  payload: string,
  signatureHeader: string,
  secret: string
): Promise<boolean> {
  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify']
  );

  // Strip vendor prefix, e.g. "sha256=<hex>" → "<hex>"
  const hexSig = signatureHeader.replace(/^sha256=/, '');
  const sigBytes = hexToUint8Array(hexSig);
  const bodyBytes = new TextEncoder().encode(payload);

  return crypto.subtle.verify('HMAC', keyMaterial, sigBytes, bodyBytes);
}

function hexToUint8Array(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes;
}
```

Signature header map per source:

| Source            | Header                     | Prefix      | Algorithm  |
|-------------------|----------------------------|-------------|------------|
| Moderation vendor | `X-Mod-Signature`          | `sha256=`   | HMAC-SHA256 |
| Stripe            | `Stripe-Signature`         | `t=,v1=`    | HMAC-SHA256 |
| GitHub            | `X-Hub-Signature-256`      | `sha256=`   | HMAC-SHA256 |
| Abuse detection   | `X-Abuse-Sig`              | none (raw)  | HMAC-SHA256 |

## Ingestion Worker

```typescript
// ingestion-worker/src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response(null, { status: 405 });
    }

    const source = new URL(request.url).pathname.split('/')[2]; // /webhooks/<source>
    const rawBody = await request.text();
    const sigHeader = request.headers.get('X-Mod-Signature')
      ?? request.headers.get('X-Hub-Signature-256')
      ?? request.headers.get('X-Abuse-Sig')
      ?? '';

    const secret = (env as any)[`WEBHOOK_SECRET_${source.toUpperCase()}`] as string;
    if (!secret) return new Response(null, { status: 400 });

    const valid = await verifyHmacSha256(rawBody, sigHeader, secret);
    if (!valid) {
      return new Response(null, { status: 401 });
    }

    // Idempotency: hash the body as a stable key
    const idempKey = request.headers.get('X-Webhook-Id') ?? await sha256Hex(rawBody);

    // Check if already enqueued / processed
    const seen = await env.WEBHOOK_KV.get(`idemp:${idempKey}`);
    if (seen) return new Response(null, { status: 200 }); // already handled

    // Mark as seen (TTL: 24 h to cover vendor retry window)
    await env.WEBHOOK_KV.put(`idemp:${idempKey}`, '1', { expirationTtl: 86400 });

    // Enqueue for reliable async processing
    await env.WEBHOOK_QUEUE.send({
      source,
      idempKey,
      payload: JSON.parse(rawBody),
      receivedAt: Date.now(),
    });

    return new Response(null, { status: 200 });
  },
};

async function sha256Hex(input: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

## Queue Configuration (wrangler.toml)

```toml
[[queues.producers]]
binding = "WEBHOOK_QUEUE"
queue = "example project-webhooks"

[[queues.consumers]]
queue = "example project-webhooks"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "example project-webhooks-dlq"
retry_delay = 30   # seconds; first retry after 30 s, backoff applies
```

Retry timing with `retry_delay = 30`:

| Attempt | Delay     | Cumulative wait |
|---------|-----------|-----------------|
| 1       | immediate | 0 s             |
| 2       | 30 s      | 30 s            |
| 3       | 60 s      | 90 s            |
| 4       | 120 s     | 210 s → DLQ     |

## Consumer Worker with Idempotent Processing

```typescript
// consumer-worker/src/index.ts
export default {
  async queue(batch: MessageBatch<WebhookEnvelope>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { source, idempKey, payload } = msg.body;

      try {
        // Double-check idempotency against D1 (KV may have evicted the key)
        const already = await env.DB.prepare(
          'SELECT 1 FROM processed_webhooks WHERE idemp_key = ?'
        ).bind(idempKey).first();

        if (already) {
          msg.ack(); // already processed — do not retry
          continue;
        }

        // Route to handler
        await handleWebhook(source, payload, env);

        // Record as processed in D1
        await env.DB.prepare(
          'INSERT INTO processed_webhooks (idemp_key, source, processed_at) VALUES (?,?,?)'
        ).bind(idempKey, source, Date.now()).run();

        msg.ack();
      } catch (err) {
        // nack() lets the Queue retry with backoff
        console.error(`Webhook processing failed: ${idempKey}`, err);
        msg.retry({ delaySeconds: 60 }); // override retry delay
      }
    }
  },
};

async function handleWebhook(source: string, payload: unknown, env: Env): Promise<void> {
  if (source === 'moderation') {
    await applyModerationAction(payload as ModerationPayload, env);
  } else if (source === 'abuse') {
    await flagAbuseEvent(payload as AbusePayload, env);
  }
}
```

## Mobile Push via Separate Queue Consumer

After processing, the consumer enqueues a mobile push notification to a dedicated push Queue rather than sending the push inline. This prevents a failed push (network timeout to the push provider) from causing the webhook message to retry unnecessarily.

```typescript
// Inside applyModerationAction
async function applyModerationAction(payload: ModerationPayload, env: Env): Promise<void> {
  // Update D1
  await env.DB.prepare(
    'UPDATE posts SET moderation_status = ? WHERE id = ?'
  ).bind(payload.action, payload.postId).run();

  // Invalidate KV cache for affected post
  await env.KV.delete(`post:${payload.postId}`);

  // Enqueue mobile push (separate concern, separate Queue)
  await env.PUSH_QUEUE.send({
    type: 'moderation_update',
    postId: payload.postId,
    action: payload.action,
    targetAnonId: payload.authorHash,
  });
}
```

Fan-out concerns separation:

| Side effect          | Mechanism          | Failure impact           |
|----------------------|--------------------|--------------------------|
| D1 status update     | Inline in consumer | Retry whole message      |
| KV cache invalidation| Inline in consumer | Retry whole message      |
| Mobile push          | Push Queue         | Push retries independently |
| Analytics event      | Analytics Engine   | Fire-and-forget          |

## Anti-patterns

- **Processing the webhook payload synchronously in the ingestion Worker** — any downstream failure causes the vendor to receive a non-200 and retry, producing duplicates.
- **Using only the request body hash for idempotency without D1 backup** — KV TTL expiry (24 h) means a slow vendor retrying after 25 hours will be re-processed; D1 `processed_webhooks` table has no TTL.
- **Verifying the HMAC after parsing JSON** — parse the body as text first, verify the HMAC over the raw text, then parse JSON; JSON serialisation is not stable across serialisers and may not match the vendor's canonical form.
- **Calling `msg.ack()` before the business logic completes** — if the Worker crashes mid-execution after ack, the event is lost permanently.
- **Sending mobile push inline in the consumer** — a push provider timeout (common on free-tier providers) kills the consumer's CPU budget and causes the Queue message to retry, re-running all side effects.

## Gotchas

- `msg.retry({ delaySeconds })` requires the consumer to have `max_retries` > 0 in `wrangler.toml`; calling it without retries remaining sends the message to the DLQ immediately.
- Workers Queue delivers messages in batches; if one message in a batch panics uncaught, the entire batch may redeliver. Always wrap per-message logic in try/catch and ack/nack individually.
- `crypto.subtle.verify` returns `false` for invalid signatures rather than throwing; always check the boolean return, never assume a non-exception means success.
- HMAC verification must use the raw request body bytes, not a re-serialised JSON string; read with `request.text()` not `request.json()`.
- Dead-letter queue messages do not auto-retry; a separate consumer on `example project-webhooks-dlq` must alert on-call and optionally re-enqueue after manual inspection.

## Verification

```bash
# Send a test webhook with valid HMAC
SECRET="my-test-secret"
BODY='{"event":"post.flagged","postId":"abc","action":"hide"}'
SIG="sha256=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')"

curl -i -X POST https://api.example.com/webhooks/moderation \
  -H "Content-Type: application/json" \
  -H "X-Mod-Signature: $SIG" \
  -d "$BODY"
# Expect: 200 OK

# Replay same body (idempotency)
curl -i -X POST https://api.example.com/webhooks/moderation \
  -H "Content-Type: application/json" \
  -H "X-Mod-Signature: $SIG" \
  -d "$BODY"
# Expect: 200 OK (not 409 or 422 — vendor sees success, no retry)

# Confirm D1 record written
wrangler d1 execute example project-db \
  --command="SELECT * FROM processed_webhooks ORDER BY processed_at DESC LIMIT 5"

# Check DLQ for unprocessed failures
wrangler queues messages get example project-webhooks-dlq --batch-size 5
```

## Related

- `webhook-architecture.md`
- `workers-queue-fanout-architecture.md`
- `at-least-once-delivery.md`
- `idempotency-design.md`
- `dead-letter-queue-architecture.md`
- `outbox-pattern.md`

## Sources

- Cloudflare Workers Queues documentation — delivery guarantees, retry semantics, DLQ configuration
- Cloudflare Workers documentation — `crypto.subtle`, CPU time limits, `waitUntil`
- Stripe webhook documentation — HMAC-SHA256 signature validation
- GitHub webhooks documentation — `X-Hub-Signature-256` verification
