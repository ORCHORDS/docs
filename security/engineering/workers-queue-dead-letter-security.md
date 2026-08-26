# Cloudflare Queues Dead-Letter Security Patterns

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A example project moderation pipeline retries failed queue messages indefinitely,
leaking user PII in stalled dead-letter payloads, or a bad actor crafts an
oversized message to exhaust consumer CPU via repeated retries. You need secure
dead-letter handling: bounded retries, payload scrubbing, and authenticated
re-ingestion.

## Context

Cloudflare Queues deliver messages at-least-once. When a consumer throws, the
message is retried up to `max_retries` times, then routed to a dead-letter
queue (DLQ) if configured. DLQ messages are still Workers-readable: they can
sit in plaintext, carry stale secrets, or be reprocessed by attacker-controlled
Workers if bindings are misconfigured. On an anonymous platform every queued
payload may include ephemeral session tokens or content that must not persist
beyond TTL.

## 1. Limiting Retries and Setting a DLQ Binding

```toml
# wrangler.toml
[[queues.consumers]]
queue = "moderation-jobs"
max_batch_size  = 10
max_batch_timeout = 5
max_retries     = 3
dead_letter_queue = "moderation-dlq"
```

Three retries keeps blast radius small. Without `dead_letter_queue` the message
is silently dropped after `max_retries`, losing audit evidence.

## 2. Payload Envelope with Expiry and Signature

```typescript
import { SignJWT, jwtVerify } from "jose";

interface QueueEnvelope {
  jobId: string;
  expiresAt: number; // unix seconds
  payload: unknown;
}

async function enqueue(
  queue: Queue,
  payload: unknown,
  secret: string,
): Promise<void> {
  const envelope: QueueEnvelope = {
    jobId: crypto.randomUUID(),
    expiresAt: Math.floor(Date.now() / 1000) + 300, // 5-min TTL
    payload,
  };
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const data = new TextEncoder().encode(JSON.stringify(envelope));
  const sig = await crypto.subtle.sign("HMAC", key, data);
  const token = btoa(String.fromCharCode(...new Uint8Array(sig)));
  await queue.send({ envelope, sig: token });
}
```

## 3. Consumer Validates Envelope Before Processing

```typescript
export default {
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(env.QUEUE_SECRET),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["verify"],
    );

    for (const msg of batch.messages) {
      const { envelope, sig } = msg.body as {
        envelope: QueueEnvelope;
        sig: string;
      };

      // 1. Reject expired messages — prevents stale-payload replay
      if (envelope.expiresAt < Math.floor(Date.now() / 1000)) {
        console.warn("expired message", envelope.jobId);
        msg.ack(); // don't retry; scrub it
        continue;
      }

      // 2. Verify signature
      const sigBytes = Uint8Array.from(atob(sig), (c) => c.charCodeAt(0));
      const data = new TextEncoder().encode(JSON.stringify(envelope));
      const valid = await crypto.subtle.verify("HMAC", key, sigBytes, data);
      if (!valid) {
        msg.ack(); // reject forgeries without retry
        continue;
      }

      try {
        await processJob(envelope, env);
        msg.ack();
      } catch (err) {
        msg.retry(); // counted against max_retries
      }
    }
  },
};
```

## 4. DLQ Consumer: Scrub PII Before Persisting

```typescript
// Bound to "moderation-dlq"
export default {
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { envelope } = msg.body as { envelope: QueueEnvelope };

      // Strip payload; only retain audit metadata
      await env.DB.prepare(
        `INSERT INTO dlq_audit (job_id, expired_at, reason)
         VALUES (?, ?, 'max_retries_exceeded')`,
      )
        .bind(envelope.jobId, envelope.expiresAt)
        .run();

      // PII never written to D1
      msg.ack();
    }
  },
};
```

## 5. Alerting on DLQ Spikes via Analytics Engine

```typescript
async function recordDlqEvent(
  env: Env,
  jobId: string,
): Promise<void> {
  env.ANALYTICS.writeDataPoint({
    blobs: ["dlq_event", jobId],
    doubles: [1],
    indexes: ["dlq"],
  });
}
```

Query in Analytics Engine SQL API to alert when DLQ rate exceeds threshold
within a 5-minute window.

## Anti-patterns

- **No DLQ configured** — messages silently disappear after max retries with no
  audit trail.
- **Retrying indefinitely** (`max_retries = -1`) — a poison-pill message
  hammers the consumer until the Worker throws a CPU-time limit error.
- **Logging full payloads in the DLQ consumer** — PII ends up in Workers Logs
  indefinitely.
- **Sharing the queue secret with DLQ consumers in other services** — rotate
  independently per queue.

## Gotchas

- Cloudflare Queues does not expose a per-message TTL API; expiry must be
  enforced in-envelope by the consumer.
- `msg.ack()` in the DLQ consumer is mandatory — without it the DLQ itself
  retries, creating an infinite loop.
- `batch.messages` are delivered in insertion order but ack/retry calls are
  independent; acking one does not affect siblings.
- Workers CPU time limit (30 ms CPU for free, 30 s wall-clock) applies per
  batch; heavy scrubbing should be offloaded via another queue or DO alarm.

## Verification

```bash
# Send a test message and observe DLQ routing after forced consumer failure
wrangler queues send moderation-jobs '{"test":true}' --local
wrangler tail moderation-dlq --format=json | jq '.event.queue'
```

Assert in CI:
- DLQ consumer never logs `.payload` fields containing `userId` or `content`.
- HMAC verification rejects messages with a tampered `sig` field.
- Messages with `expiresAt` in the past are ack'd without retry.

## Related

- `cloudflare-queues-message-integrity.md`
- `workers-analytics-engine-security-telemetry.md`
- `workers-environment-variable-hygiene.md`
- `api-replay-prevention-nonce-d1-workers.md`

## Sources

- Cloudflare Queues documentation — Dead Letter Queues (2025)
- OWASP Secure Messaging Patterns
- Cloudflare Workers CPU limits reference
