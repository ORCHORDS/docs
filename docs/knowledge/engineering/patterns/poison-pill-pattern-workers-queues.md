# Poison Pill Pattern — Workers Queues

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers Queue consumer processes webhook payloads. One malformed message — bad JSON, an unexpected null field, a circular schema — throws on every delivery attempt. It consumes all retry slots, lands in the dead-letter queue (DLQ), and the team finds it hours later wondering why events went missing. Worse, if the consumer panics hard enough it delays processing of *healthy* messages in the same batch.

The poison pill pattern adds deliberate detection, quarantine, and metadata capture *before* retries are exhausted, keeping the happy path fast and making bad messages visible immediately.

---

## Context

Cloudflare Queues deliver messages in batches (`MessageBatch`). Each `Message` has `.body`, `.id`, `.timestamp`, and `.attempts`. The consumer must call `.ack()` or `.retry()` (or `batch.ackAll()` / `batch.retryAll()`) before the handler returns; unacknowledged messages are automatically retried. A configurable `dead_letter_queue` binding receives messages after `max_retries` is exhausted. The poison pill pattern intercepts *before* that limit to quarantine, alert, and ack the message cleanly.

---

## Schema Validation as the First Gate

```typescript
// src/schema.ts
import { z } from 'zod';

export const WebhookPayloadSchema = z.object({
  event:     z.enum(['order.created', 'order.updated', 'order.cancelled']),
  orderId:   z.string().uuid(),
  timestamp: z.string().datetime(),
  data:      z.record(z.unknown()),
});

export type WebhookPayload = z.infer<typeof WebhookPayloadSchema>;

export function parsePayload(raw: unknown):
  | { ok: true; value: WebhookPayload }
  | { ok: false; error: string } {
  const result = WebhookPayloadSchema.safeParse(raw);
  if (result.success) return { ok: true, value: result.data };
  return { ok: false, error: result.error.message };
}
```

---

## Consumer with Poison Pill Detection

```typescript
// src/consumer.ts
import type { MessageBatch, Message } from '@cloudflare/workers-types';
import { parsePayload, WebhookPayload } from './schema';

interface Env {
  QUARANTINE_KV: KVNamespace;
  ALERT_WEBHOOK: string;     // Slack / PagerDuty URL
}

const POISON_THRESHOLD = 2; // quarantine after this many attempts

export default {
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      await handleMessage(message, env);
    }
  },
};

async function handleMessage(message: Message<unknown>, env: Env): Promise<void> {
  // 1. Structural validation — catch poison early
  const parsed = parsePayload(message.body);
  if (!parsed.ok) {
    await quarantine(message, `Schema validation failed: ${parsed.error}`, env);
    return;
  }

  // 2. Attempt-based escalation
  if (message.attempts >= POISON_THRESHOLD) {
    await quarantine(
      message,
      `Message exceeded ${POISON_THRESHOLD} attempts without schema errors — likely logic poison`,
      env,
    );
    return;
  }

  // 3. Normal processing
  try {
    await processWebhook(parsed.value);
    message.ack();
  } catch (err) {
    // Transient failure — allow natural retry
    message.retry({ delaySeconds: 30 * message.attempts });
  }
}

async function processWebhook(payload: WebhookPayload): Promise<void> {
  // business logic
}
```

---

## Quarantine to KV + Alert

```typescript
// src/consumer.ts (continued)
async function quarantine(
  message: Message<unknown>,
  reason: string,
  env: Env,
): Promise<void> {
  const key = `poison:${message.id}`;
  const record = {
    messageId:   message.id,
    attempts:    message.attempts,
    timestamp:   message.timestamp.toISOString(),
    reason,
    body:        JSON.stringify(message.body),
    quarantinedAt: new Date().toISOString(),
  };

  await Promise.all([
    // Store quarantined message for 7 days
    env.QUARANTINE_KV.put(key, JSON.stringify(record), { expirationTtl: 604_800 }),
    // Alert on-call (fire-and-forget; failure should not block ack)
    sendAlert(env.ALERT_WEBHOOK, record).catch(console.error),
  ]);

  // ACK — do NOT retry; the message is permanently removed from the queue
  message.ack();
  console.error(`[poison-pill] quarantined ${message.id}: ${reason}`);
}

async function sendAlert(webhookUrl: string, record: object): Promise<void> {
  await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: `🐛 Poison pill quarantined: \`${(record as any).messageId}\`\nReason: ${(record as any).reason}`,
    }),
  });
}
```

---

## Quarantine Inspection Endpoint

```typescript
// src/index.ts  (admin handler)
interface Env {
  QUARANTINE_KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/admin/quarantine') {
      const list = await env.QUARANTINE_KV.list({ prefix: 'poison:' });
      const records = await Promise.all(
        list.keys.map(async k => {
          const v = await env.QUARANTINE_KV.get(k.name);
          return v ? JSON.parse(v) : null;
        }),
      );
      return Response.json(records.filter(Boolean));
    }

    if (url.pathname.startsWith('/admin/quarantine/')) {
      const id = url.pathname.split('/').pop()!;
      const value = await env.QUARANTINE_KV.get(`poison:${id}`);
      if (!value) return new Response('Not found', { status: 404 });
      return Response.json(JSON.parse(value));
    }

    return new Response('Not found', { status: 404 });
  },
};
```

---

## Replay from Quarantine

```typescript
// scripts/replay-poison.ts
// Run with: npx wrangler kv:get "poison:<id>" --binding QUARANTINE_KV | node scripts/replay-poison.ts

import type { Queue } from '@cloudflare/workers-types';

async function replay(record: {
  body: string;
  messageId: string;
}, queue: Queue): Promise<void> {
  // Re-parse the stored body and send to a repair queue for manual processing
  const body = JSON.parse(record.body);
  await queue.send({ replayedFrom: record.messageId, ...body });
  console.log(`Replayed ${record.messageId}`);
}
```

---

## Anti-patterns

- **Retrying poison pills**: calling `message.retry()` on a structurally invalid message is wasteful — it will fail identically every time until it dead-letters. Detect and ack early.
- **Silently dropping poison pills** (acking without storing): losing the message body means you cannot replay or diagnose. Always quarantine before acking.
- **Using the DLQ as quarantine**: the DLQ has its own retry behaviour and can re-enter the main consumer if configured naively. An explicit KV quarantine store is inspectable and queryable.
- **Alerting synchronously in the hot path**: `await sendAlert(...)` inside the ack path means a slow webhook delays the queue consumer. Fire-and-forget with `.catch(console.error)`.
- **Quarantining all transient errors**: network timeouts and 503s are transient. Only quarantine messages that fail *structural validation* or exceed a per-attempt threshold; allow transient errors to retry naturally.

---

## Gotchas

- `message.timestamp` is a `Date` object in the Workers runtime, but `JSON.stringify` does not convert it automatically — call `.toISOString()` explicitly.
- KV `put` with `expirationTtl` requires the value to be a minimum of 60 seconds; `604_800` (7 days) is safe.
- `batch.ackAll()` or `batch.retryAll()` are all-or-nothing; if your loop mixes acks and retries, call per-message `.ack()` / `.retry()` rather than the batch methods.
- The `attempts` counter on `Message` resets to `1` after a `retryAll()` — it is the delivery count for the *current* batch invocation, not lifetime attempts.
- Zod's `safeParse` never throws; `parse` does. Prefer `safeParse` in consumers so schema errors are catchable without a try/catch.

---

## Verification

```bash
# Publish a structurally invalid message (missing required fields)
npx wrangler queues publish --queue webhook-queue \
  --body '{"event":"unknown","garbage":true}'

# Tail logs
npx wrangler tail --format pretty | grep poison-pill
# [poison-pill] quarantined msg_abc123: Schema validation failed: ...

# Inspect quarantine
curl https://my-worker.workers.dev/admin/quarantine | jq '.[0].reason'
# "Schema validation failed: ..."

# Confirm the bad message did NOT block subsequent healthy messages
npx wrangler queues publish --queue webhook-queue \
  --body '{"event":"order.created","orderId":"00000000-0000-0000-0000-000000000001","timestamp":"2026-08-23T00:00:00Z","data":{}}'
npx wrangler tail --format pretty | grep -v poison
# Normal processing log
```

---

## Related

- `dead-letter-queue-pattern.md`
- `retry-budget-pattern-workers-queues.md`
- `adaptive-backpressure-workers-queues.md`
- `inbox-pattern-idempotent-consumption.md`
- `competing-consumers-workers-queues.md`

---

## Sources

- Cloudflare Queues docs — `Message`, `MessageBatch`, `dead_letter_queue` (2026)
- Enterprise Integration Patterns, Hohpe & Woolf — "Dead Letter Channel", "Invalid Message Channel"
- Zod documentation — `safeParse` (2026)
