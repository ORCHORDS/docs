# Progressive Retry Topology with Queues and Dead-Letter Requeue

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A queue consumer fails on a subset of messages — transient 503s from a downstream API, D1 lock conflicts, or intermittent network timeouts. Cloudflare Queues' built-in retry with fixed backoff retries all failures identically, which floods healthy messages with unnecessary delays and does not distinguish recoverable from non-recoverable errors. You need tiered, progressive retry delays with a human-inspectable dead-letter queue that supports selective requeue.

## Context

Cloudflare Queues supports up to 3 retries with a `delaySeconds` hint per message, and a `dead_letter_queue` binding that receives messages after all retries are exhausted. The progressive retry topology exploits `delaySeconds` to implement exponential backoff at the message level and adds a separate "requeue worker" that allows operations teams to selectively move DLQ messages back to the main queue after investigation or remediation.

## Topology Overview

```
Producer → main-queue
               │
         Consumer Worker (max_retries=3)
           ├─ success → ack
           ├─ transient error → retry(delaySeconds = 2^attempt * 10)
           └─ permanent error → ack + publish to dlq-manual (bypass auto-DLQ)
               │
         Auto-DLQ (after 3 retries exhausted)
               │
         DLQ Inspector UI / Requeue Worker
           ├─ inspect message
           └─ requeue → main-queue (with reset attempt counter)
```

## Message Envelope with Retry Metadata

```typescript
// src/types.ts
export interface QueueMessage<T = unknown> {
  payload: T;
  // Retry metadata — incremented by the consumer before retry
  attempt: number;           // 0 = first delivery
  firstEnqueuedAt: string;   // ISO timestamp, set by producer
  lastError?: string;        // Description of last failure reason
  errorClass?: "transient" | "permanent" | "unknown";
}

// Maximum delay Queues accepts (currently 43200 s = 12 hours)
export const MAX_DELAY_SECONDS = 43200;

export function retryDelay(attempt: number, baseSeconds = 10): number {
  // Exponential: 10s, 20s, 40s (capped at 12h)
  return Math.min(baseSeconds * Math.pow(2, attempt), MAX_DELAY_SECONDS);
}
```

## Consumer Worker with Progressive Backoff

```typescript
// src/consumer-worker.ts
import { QueueMessage, retryDelay } from "./types";

interface Env {
  MAIN_QUEUE: Queue<QueueMessage>;
  MANUAL_DLQ: Queue<QueueMessage>;   // for permanent errors
  DB: D1Database;
}

interface OrderPayload {
  orderId: string;
  customerId: string;
  totalCents: number;
}

type OrderMessage = QueueMessage<OrderPayload>;

// Classify errors so the consumer can decide retry vs. dead-letter
function classifyError(err: unknown): "transient" | "permanent" {
  if (!(err instanceof Error)) return "unknown" as any;
  // HTTP 4xx from downstream = permanent (bad data)
  if (err.message.includes("400") || err.message.includes("422")) {
    return "permanent";
  }
  // HTTP 5xx, network timeouts = transient
  return "transient";
}

async function processOrder(env: Env, payload: OrderPayload): Promise<void> {
  // Example: insert into D1, call downstream fulfillment API
  const result = await env.DB.prepare(
    `INSERT OR IGNORE INTO orders (id, customer_id, total_cents, status)
     VALUES (?1, ?2, ?3, 'pending')`
  )
    .bind(payload.orderId, payload.customerId, payload.totalCents)
    .run();

  if (!result.success) {
    throw new Error(`D1 insert failed for order ${payload.orderId}`);
  }

  // Simulate fulfillment API call
  const res = await fetch("https://fulfillment.internal/orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw Object.assign(new Error(`Fulfillment API ${res.status}`), {
      status: res.status,
    });
  }
}

export default {
  async queue(
    batch: MessageBatch<OrderMessage>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      const envelope = msg.body;
      const { payload, attempt = 0, firstEnqueuedAt } = envelope;

      // Guard: if message is too old, dead-letter it regardless of error class
      const ageMs = Date.now() - new Date(firstEnqueuedAt).getTime();
      const MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

      if (ageMs > MAX_AGE_MS) {
        console.warn(`Message age ${ageMs}ms exceeds TTL — routing to manual DLQ`, {
          orderId: payload.orderId,
        });
        await env.MANUAL_DLQ.send({ ...envelope, lastError: "TTL exceeded", errorClass: "permanent" });
        msg.ack(); // ack so Queues doesn't auto-retry
        continue;
      }

      try {
        await processOrder(env, payload);
        msg.ack();
      } catch (err) {
        const errorClass = classifyError(err);
        const errorMessage = err instanceof Error ? err.message : String(err);

        console.error(`Order ${payload.orderId} failed (attempt ${attempt}):`, errorMessage);

        if (errorClass === "permanent") {
          // Non-recoverable: route directly to manual DLQ, don't consume retries
          await env.MANUAL_DLQ.send({
            ...envelope,
            attempt: attempt + 1,
            lastError: errorMessage,
            errorClass: "permanent",
          });
          msg.ack();
        } else {
          // Transient: let Queues retry with progressive delay
          const delay = retryDelay(attempt);
          console.info(`Scheduling retry attempt ${attempt + 1} in ${delay}s`);
          // Update attempt count in the envelope for the next delivery
          // Note: msg.retry() re-delivers msg.body as-is; we must re-enqueue with updated metadata
          await env.MAIN_QUEUE.send(
            { ...envelope, attempt: attempt + 1, lastError: errorMessage, errorClass: "transient" },
            { delaySeconds: delay }
          );
          msg.ack(); // ack original to avoid double-delivery
        }
      }
    }
  },
};
```

## Requeue Worker: DLQ Inspection and Selective Replay

```typescript
// src/requeue-worker.ts
interface Env {
  MANUAL_DLQ: Queue<unknown>;
  MAIN_QUEUE: Queue<unknown>;
  DLQ_STORE: KVNamespace; // stores DLQ snapshots for UI inspection
}

// Called by an operator via POST /requeue/:messageKey
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/dlq") {
      // List recent DLQ entries (stored via DLQ consumer)
      const list = await env.DLQ_STORE.list({ prefix: "dlq:", limit: 100 });
      const items = await Promise.all(
        list.keys.map(async (k) => {
          const val = await env.DLQ_STORE.get(k.name, "json");
          return { key: k.name, ...((val as object) ?? {}) };
        })
      );
      return Response.json({ items });
    }

    const match = url.pathname.match(/^\/requeue\/(.+)$/);
    if (request.method === "POST" && match) {
      const key = decodeURIComponent(match[1]);
      const stored = await env.DLQ_STORE.get<unknown>(key, "json");
      if (!stored) {
        return Response.json({ error: "Message not found" }, { status: 404 });
      }

      // Reset attempt counter so it gets full retry budget again
      const requeuedMsg = { ...(stored as any), attempt: 0, lastError: undefined, errorClass: undefined };
      await env.MAIN_QUEUE.send(requeuedMsg);
      await env.DLQ_STORE.delete(key);

      return Response.json({ ok: true, requeued: key });
    }

    return new Response("Not Found", { status: 404 });
  },

  // DLQ consumer: snapshot messages to KV for inspection
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const key = `dlq:${Date.now()}-${crypto.randomUUID()}`;
      await env.DLQ_STORE.put(key, JSON.stringify(msg.body), {
        expirationTtl: 7 * 24 * 60 * 60, // 7 days
      });
      msg.ack();
    }
  },
};
```

## wrangler.toml

```toml
name = "order-processor"
main = "src/consumer-worker.ts"
compatibility_date = "2024-09-23"

[[queues.consumers]]
queue = "main-orders"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 0          # We manage retries manually via re-enqueue
dead_letter_queue = "orders-auto-dlq"

[[queues.producers]]
binding = "MAIN_QUEUE"
queue = "main-orders"

[[queues.producers]]
binding = "MANUAL_DLQ"
queue = "orders-manual-dlq"

[[d1_databases]]
binding = "DB"
database_name = "orders-db"
database_id = "YOUR_D1_ID"
```

## Retry Delay Table

| Attempt | Delay (base=10 s) | Cumulative wait |
|---------|-------------------|-----------------|
| 0 (first) | immediate | 0 s |
| 1 | 10 s | 10 s |
| 2 | 20 s | 30 s |
| 3 | 40 s | 70 s |
| DLQ | — | manual |

For third-party API rate limits (429), use a longer base (e.g. 60 s) and read the `Retry-After` header to set `delaySeconds` precisely.

## Anti-patterns

- **Using `msg.retry()` without updating the attempt counter in the envelope** — Queues re-delivers `msg.body` unchanged; if attempt is not incremented in the body, progressive delay logic always sees attempt=0.
- **Setting `max_retries > 0` while also manually re-enqueueing** — leads to double-delivery: the manual re-enqueue fires and Queues also retries the original; set `max_retries=0` when self-managing retries.
- **Dead-lettering all errors including transient ones immediately** — a DLQ that fills with transient errors requires constant operator intervention; classify errors before routing.
- **Not capping `delaySeconds`** — Queues accepts up to 43200 s (12 h); exceeding this causes the SDK to throw at enqueue time, losing the message.
- **Storing full message payloads in the DLQ Queue binding** — Queues messages are not browsable; always mirror DLQ messages to KV or D1 for operator inspection.

## Gotchas

- `msg.retry({ delaySeconds })` adds delay on top of the queue's own minimum retry delay; for manual re-enqueue via `MAIN_QUEUE.send(..., { delaySeconds })`, the delay is exact.
- Cloudflare Queues guarantees at-least-once delivery; consumers must be idempotent (use `INSERT OR IGNORE` or check-then-skip patterns).
- KV writes in the requeue worker are eventually consistent; an operator viewing the DLQ list immediately after a failure may not see the newest entries for up to ~60 s.
- The `dead_letter_queue` in `wrangler.toml` only fires after `max_retries` is exhausted; with `max_retries=0`, no message ever reaches the auto-DLQ — your `MANUAL_DLQ` binding takes that role entirely.
- DLQ KV expiration (`expirationTtl`) must be set; otherwise unprocessed DLQ entries accumulate and eventually hit KV storage limits.

## Verification

1. Publish a message with a payload that will cause a transient error (e.g. `{"orderId": "simulate-503", ...}`).
2. Watch `wrangler tail` — confirm successive re-enqueues with increasing `delaySeconds` (10, 20, 40).
3. After 3 attempts, confirm the message appears in KV under `dlq:*` via `wrangler kv key list`.
4. POST to `/requeue/:key` and verify the message reappears in `main-orders` with `attempt=0`.
5. Publish a message with a permanent-error payload — confirm it routes to `MANUAL_DLQ` after exactly one attempt (no retries).

## Related

- `dead-letter-queue-architecture.md`
- `at-least-once-delivery.md`
- `competing-consumers-queues.md`
- `temporal-decoupling-cloudflare-queues.md`
- `retry-storm-prevention-workers-jitter-backoff.md`

## Sources

- https://developers.cloudflare.com/queues/configuration/configure-queues/#dead-letter-queues
- https://developers.cloudflare.com/queues/reference/how-queues-works/#message-retries
- https://aws.amazon.com/blogs/compute/designing-durable-serverless-apps-with-dlqs-for-amazon-sqs-lambda/
