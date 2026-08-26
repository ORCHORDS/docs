# Poison Pill Message Handling in Cloudflare Queues

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Cloudflare Queue consumer crashes on a specific message, the batch is retried, it crashes again, and the entire pipeline stalls until `maxRetries` is exhausted — by which time every retry has burned against legitimate messages that happen to share the batch. On example project, malformed moderation events or corrupted reaction payloads can silently block the pipeline for the minutes Queues waits between retry attempts.

## Context

Cloudflare Queues delivers messages in batches. When a consumer throws, the **entire batch** is retried (with configurable backoff) up to `maxRetries` times. A single structurally invalid message — a "poison pill" — can repeatedly force good messages to be reprocessed, burning idempotency tokens and inflating D1 write costs. The correct fix is to detect the offending message early, route it to a dead-letter structure, and `ack()` everything else so the healthy messages proceed. This is distinct from the dead-letter queue (DLQ) pattern, which is a *destination*; poison pill handling is a *detection and isolation strategy*.

## 1. Structural Validation Before Processing

Parse and validate each message individually before doing any work. Return early with an `ack()` on structural failures so a bad message never poisons its batch-mates.

```typescript
import { z } from 'zod';

const ReactionEventSchema = z.object({
  userId: z.string().uuid(),
  postId: z.string().uuid(),
  emoji: z.string().max(32),
  ts: z.number().int().positive(),
});

export default {
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const parsed = ReactionEventSchema.safeParse(msg.body);
      if (!parsed.success) {
        await routeToDLQ(msg, parsed.error.flatten(), env);
        msg.ack(); // isolate; do not let it block the batch
        continue;
      }
      try {
        await processReaction(parsed.data, env);
        msg.ack();
      } catch (err) {
        msg.retry(); // legitimate transient failure — let Queues retry
      }
    }
  },
};
```

## 2. Per-Message Retry Counting with KV

Cloudflare Queues tracks retries at the batch level, not the message level. Use KV to maintain a per-message attempt counter keyed on a stable message ID so you can evict a message after N individual failures without blocking its siblings.

```typescript
const MAX_MSG_ATTEMPTS = 3;

async function processWithRetryGuard(
  msg: Message<ReactionEvent>,
  env: Env,
): Promise<void> {
  const counterKey = `pill:${msg.id}`;
  const raw = await env.KV.get(counterKey);
  const attempts = raw ? parseInt(raw, 10) : 0;

  if (attempts >= MAX_MSG_ATTEMPTS) {
    await routeToDLQ(msg, { reason: 'max_attempts_exceeded', attempts }, env);
    msg.ack();
    return;
  }

  try {
    await processReaction(msg.body, env);
    await env.KV.delete(counterKey);
    msg.ack();
  } catch (err) {
    await env.KV.put(counterKey, String(attempts + 1), { expirationTtl: 86400 });
    msg.retry();
  }
}
```

## 3. DLQ Routing via a Dedicated Queue Binding

Route isolated poison pills to a separate `DEAD_LETTER` queue binding rather than just logging them. This keeps them observable and replayable without manual intervention.

```typescript
interface DLQPayload {
  originalId: string;
  originalBody: unknown;
  reason: unknown;
  failedAt: string;
  queue: string;
}

async function routeToDLQ(
  msg: Message<unknown>,
  reason: unknown,
  env: Env,
): Promise<void> {
  const payload: DLQPayload = {
    originalId: msg.id,
    originalBody: msg.body,
    reason,
    failedAt: new Date().toISOString(),
    queue: 'reactions',
  };
  await env.DEAD_LETTER.send(payload);
  console.error('poison_pill_isolated', { id: msg.id, reason });
}
```

`wrangler.toml` bindings:

```toml
[[queues.consumers]]
queue = "reactions"
max_batch_size = 25
max_retries = 2

[[queues.producers]]
binding = "DEAD_LETTER"
queue = "reactions-dlq"
```

## 4. Replay Consumer for the DLQ

A DLQ is only useful if you can replay messages once the root cause is fixed. A replay consumer re-emits corrected messages back to the source queue after a human (or automated script) marks them as replayable in D1.

```typescript
export const dlqConsumer: ExportedHandler<Env> = {
  async queue(batch: MessageBatch<DLQPayload>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const row = await env.DB.prepare(
        'SELECT replayable FROM dlq_audit WHERE original_id = ?',
      )
        .bind(msg.body.originalId)
        .first<{ replayable: number }>();

      if (row?.replayable) {
        await env.REACTIONS.send(msg.body.originalBody);
      }
      msg.ack(); // always ack DLQ messages; do not re-poison
    }
  },
};
```

## Anti-patterns

- **Retrying the entire batch on structural errors** — if validation fails, `ack()` the bad message immediately; `retry()` is for transient runtime errors only.
- **Using only `console.error` for poison pills** — without routing to a DLQ queue or D1 audit table you lose the payload forever once the message is exhausted.
- **Keying the KV counter on message content hash** — identical legitimate messages (e.g., duplicate reactions) will share the counter and be incorrectly evicted. Always key on `msg.id`.
- **Setting `max_retries` to 0 globally** — this silences transient failures alongside structural ones; keep global retries non-zero and gate poisonous messages through explicit per-message logic.

## Gotchas

- `msg.id` is stable across retries within a single delivery attempt but is **not** guaranteed to be the same if the message is re-enqueued by the DLQ replay consumer; store the original ID in the DLQ payload explicitly.
- KV TTLs must be long enough to survive the full `max_retries × delay_seconds` window plus buffer, otherwise the attempt counter resets mid-retry and the pill loops forever.
- `batch.messages` order is not guaranteed; a validation error in message index 0 does not imply message index 1 was delivered before it.
- Cloudflare Queues does not expose a native `messageAttributes` for delivery count; the KV-counter approach is currently the only way to achieve per-message retry accounting.

## Verification

1. Publish a structurally invalid message to the reactions queue; assert the DLQ queue receives it within one delivery cycle and the source queue does not stall.
2. Publish a mix of 1 invalid + 4 valid messages in the same batch; assert all 4 valid messages are processed successfully in the same batch run.
3. Inspect the KV namespace after 3 failed attempts on a valid-but-runtime-failing message; assert the counter reads `3` and the next delivery routes to DLQ.
4. Mark a DLQ record as `replayable = 1` in D1; trigger the DLQ consumer and assert the original body appears in the source queue.

## Related

- `dead-letter-queue-architecture.md`
- `progressive-retry-topology-queues-dead-letter-requeue.md`
- `at-least-once-delivery.md`
- `message-deduplication.md`
- `reactive-streams-backpressure-workers-queues.md`

## Sources

- Cloudflare Queues documentation — message retries and batch processing: https://developers.cloudflare.com/queues/
- Enterprise Integration Patterns — "Invalid Message Channel" (Hohpe & Woolf)
- Cloudflare Workers KV — TTL semantics: https://developers.cloudflare.com/kv/
