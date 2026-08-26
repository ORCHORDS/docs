# Fan-out Notification Delivery Pattern with Queues + Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A business event (order placed, password changed, subscription renewed) must trigger notifications across multiple channels — email, push, webhook — to one or more subscribers. Sending all notifications inline in the request path slows the API response and couples it to the reliability of external notification providers. A single slow or failing channel should not block or lose notifications for other channels.

## Context

Cloudflare Queues decouple producers from consumers. A single producer message can be fanned out by writing one message per delivery channel to separate queues, each consumed by a dedicated Worker. D1 stores subscriber preferences and delivery receipts. This gives per-channel retry logic, dead-letter queues, and independent scaling without a heavy message broker like Kafka or RabbitMQ.

## Solution

A Notification Router Worker receives the raw business event, looks up active subscribers in D1, then enqueues one message per subscriber-channel pair. Three channel consumers (email, push, webhook) process their queues independently, write delivery status back to D1, and handle retries.

```typescript
// wrangler.toml excerpt
// [[queues.producers]]
//   queue = "notifications-email"
//   binding = "EMAIL_QUEUE"
// [[queues.producers]]
//   queue = "notifications-push"
//   binding = "PUSH_QUEUE"
// [[queues.producers]]
//   queue = "notifications-webhook"
//   binding = "WEBHOOK_QUEUE"
//
// [[queues.consumers]]
//   queue = "notifications-email"
//   max_batch_size = 20
//   max_batch_timeout = 5
// [[queues.consumers]]
//   queue = "notifications-push"
//   max_batch_size = 100
//   max_batch_timeout = 2
// [[queues.consumers]]
//   queue = "notifications-webhook"
//   max_batch_size = 10
//   max_batch_timeout = 10

export interface Env {
  DB:             D1Database;
  EMAIL_QUEUE:    Queue;
  PUSH_QUEUE:     Queue;
  WEBHOOK_QUEUE:  Queue;
  EMAIL_API_KEY:  string;
  PUSH_API_KEY:   string;
}

// Shared types
interface NotificationEvent {
  eventType: string;   // e.g. "order.placed"
  entityId:  string;   // e.g. order ID
  payload:   Record<string, unknown>;
  occurredAt: string;  // ISO 8601
}

interface ChannelMessage {
  notificationId: string;
  userId:         string;
  channel:        'email' | 'push' | 'webhook';
  destination:    string;  // email address | push token | webhook URL
  templateId:     string;
  payload:        Record<string, unknown>;
  sentAt:         string;
}

// --- Notification Router Worker ---

async function lookupSubscribers(
  db: D1Database,
  eventType: string
): Promise<Array<{ userId: string; channel: string; destination: string; templateId: string }>> {
  const { results } = await db
    .prepare(
      `SELECT s.user_id, s.channel, s.destination, t.template_id
       FROM subscriptions s
       JOIN notification_templates t
         ON t.event_type = s.event_type AND t.channel = s.channel
       WHERE s.event_type = ?1
         AND s.active = 1`
    )
    .bind(eventType)
    .all();
  return results as any[];
}

async function recordNotification(
  db: D1Database,
  id: string,
  event: NotificationEvent,
  userId: string,
  channel: string
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO notification_log
         (id, event_type, entity_id, user_id, channel, status, created_at)
       VALUES (?1, ?2, ?3, ?4, ?5, 'queued', ?6)`
    )
    .bind(id, event.eventType, event.entityId, userId, channel, new Date().toISOString())
    .run();
}

export const notificationRouter = {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method not allowed', { status: 405 });

    const event = await request.json<NotificationEvent>();
    const subscribers = await lookupSubscribers(env.DB, event.eventType);

    if (subscribers.length === 0) {
      return Response.json({ queued: 0 });
    }

    const channelQueues: Record<string, Queue> = {
      email:   env.EMAIL_QUEUE,
      push:    env.PUSH_QUEUE,
      webhook: env.WEBHOOK_QUEUE,
    };

    const sends: Promise<void>[] = [];
    for (const sub of subscribers) {
      const notificationId = crypto.randomUUID();
      const msg: ChannelMessage = {
        notificationId,
        userId:      sub.userId,
        channel:     sub.channel as ChannelMessage['channel'],
        destination: sub.destination,
        templateId:  sub.templateId,
        payload:     event.payload,
        sentAt:      new Date().toISOString(),
      };

      const q = channelQueues[sub.channel];
      if (!q) continue;

      sends.push(
        recordNotification(env.DB, notificationId, event, sub.userId, sub.channel)
          .then(() => q.send(msg))
      );
    }

    await Promise.allSettled(sends);
    return Response.json({ queued: subscribers.length });
  },
};

// --- Email Channel Consumer ---

async function sendEmail(apiKey: string, to: string, templateId: string, data: unknown): Promise<void> {
  const resp = await fetch('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type':  'application/json',
    },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: to }], dynamic_template_data: data }],
      from: { email: 'noreply@example.com' },
      template_id: templateId,
    }),
  });
  if (!resp.ok) throw new Error(`Email send failed: ${resp.status}`);
}

async function markDelivered(db: D1Database, notificationId: string, channel: string, status: string): Promise<void> {
  await db
    .prepare(`UPDATE notification_log SET status = ?1, delivered_at = ?2 WHERE id = ?3 AND channel = ?4`)
    .bind(status, new Date().toISOString(), notificationId, channel)
    .run();
}

export const emailConsumer = {
  async queue(batch: MessageBatch<ChannelMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const msg = message.body;
      try {
        await sendEmail(env.EMAIL_API_KEY, msg.destination, msg.templateId, msg.payload);
        await markDelivered(env.DB, msg.notificationId, 'email', 'delivered');
        message.ack();
      } catch (err) {
        // Queues will retry based on retry policy; do not ack
        await markDelivered(env.DB, msg.notificationId, 'email', 'failed');
        message.retry({ delaySeconds: 30 });
      }
    }
  },
};

// --- Webhook Channel Consumer ---

export const webhookConsumer = {
  async queue(batch: MessageBatch<ChannelMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const msg = message.body;
      try {
        const resp = await fetch(msg.destination, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Notification-Id': msg.notificationId },
          body: JSON.stringify({ event: msg.templateId, data: msg.payload, sentAt: msg.sentAt }),
          signal: AbortSignal.timeout(10_000),
        });
        if (!resp.ok && resp.status < 500) {
          // 4xx — permanent failure, ack to avoid retrying bad webhooks
          await markDelivered(env.DB, msg.notificationId, 'webhook', 'rejected');
          message.ack();
        } else if (!resp.ok) {
          throw new Error(`Webhook returned ${resp.status}`);
        } else {
          await markDelivered(env.DB, msg.notificationId, 'webhook', 'delivered');
          message.ack();
        }
      } catch (err) {
        message.retry({ delaySeconds: 60 });
      }
    }
  },
};

// --- Unsubscribe propagation ---
// When a user unsubscribes, mark their subscription inactive in D1.
// In-flight messages already on the queue will be delivered once; the consumer
// can check active status before sending and ack early to suppress delivery.

async function isSubscriptionActive(db: D1Database, userId: string, channel: string): Promise<boolean> {
  const row = await db
    .prepare(`SELECT active FROM subscriptions WHERE user_id = ?1 AND channel = ?2`)
    .bind(userId, channel)
    .first<{ active: number }>();
  return row?.active === 1;
}
```

## Implementation Details

**Fan-out ratio.** One business event fans out to N subscriber-channel pairs. Each pair becomes one Queue message. Queues batch messages for consumers, so a sudden spike of 10,000 events fans out to up to 30,000 queue messages across three queues but each consumer sees manageable batches.

**D1 as subscriber registry.** A `subscriptions` table maps `(user_id, event_type, channel)` to a destination and template ID. Queries are lightweight — add an index on `(event_type, active)` to keep the router lookup fast.

**Per-channel retry policy.** Each queue has its own retry settings. Email may retry 3 times with exponential back-off; webhooks may try 5 times; push tokens that return 410 Gone are acked immediately and the token deleted.

**Delivery tracking.** Every notification gets a UUID logged to `notification_log` before the Queue send. Consumers update the status on success or failure. This enables an admin UI to show delivery state without querying the Queue (which has no read API for in-flight messages).

**Unsubscribe propagation.** In-flight messages will still arrive at the consumer after an unsubscribe. The consumer performs a cheap `SELECT active` before sending and acks without sending if the subscription is now inactive.

## Anti-patterns

- **Sending all channels in the router Worker inline.** Any one slow channel (e.g., a flaky webhook) blocks the entire response and loses other notifications on timeout.
- **One queue for all channels.** Mixed messages force every consumer to inspect the channel field and skip irrelevant messages, wasting compute and complicating retry policies.
- **Not recording intent before enqueuing.** If the Worker crashes after enqueuing but before recording, you have no audit trail. Record first, then enqueue.
- **Retrying 4xx webhook responses.** A 400 or 404 from an endpoint will never succeed. Detect client errors and ack immediately; only retry 5xx and network errors.

## Gotchas

- Queues guarantee at-least-once delivery. Consumers must be idempotent — check `notification_log` for an existing `delivered` record and skip if present.
- `batch.messages` length may be less than `max_batch_size` when the timeout fires. Never assume a full batch.
- `message.retry({ delaySeconds })` only works if your queue has a retry policy with `max_retries > 0` configured in wrangler.toml.
- D1's free tier has a 100,000 row-writes/day limit. High-volume notifications should batch `notification_log` inserts or use an R2-backed log.
- Cloudflare Queues do not support message priority. If email is more important than webhooks, give the email queue a higher `max_batch_size` or dedicate more consumer instances.

## Verification

```bash
# Trigger a test event
curl -X POST https://api.example.com/internal/notify \
  -H 'Content-Type: application/json' \
  -d '{"eventType":"order.placed","entityId":"ord_123","payload":{"amount":99.99},"occurredAt":"2026-08-24T10:00:00Z"}'

# Check delivery log in D1
wrangler d1 execute notifications-db \
  --command "SELECT id, channel, status, delivered_at FROM notification_log WHERE entity_id = 'ord_123'"
```

## Related

- `saga-pattern-queues` — multi-step workflows with Queues
- `workers-outbox-pattern-d1-queues` — reliable event publishing from D1
- `workers-write-behind-cache-kv-d1` — async D1 flush via Queue

## Sources

- Cloudflare Queues docs: https://developers.cloudflare.com/queues/
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
- Fan-out pattern: https://aws.amazon.com/pub-sub-messaging/
