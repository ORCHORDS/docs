# Observer Pattern with Cloudflare Queues: Event Fan-out

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

When an order is confirmed, you need to: send a confirmation email, update inventory, emit an analytics event, and trigger a fraud-check. Doing all four synchronously in the confirmation handler inflates latency, couples unrelated services, and means a flaky email provider can fail the entire confirmation. The Observer pattern via Cloudflare Queues decouples publishers from subscribers: the confirmation Worker emits one event; subscriber Workers react independently with retries and dead-letter handling.

## Context

- Runtime: Cloudflare Workers
- Messaging: Cloudflare Queues (push-based, at-least-once delivery)
- Language: TypeScript 5.x
- Each subscriber is a separate Worker with its own `queue` handler
- Fanout is achieved by routing a single published message to multiple queues, or by one consumer re-publishing to subscriber-specific queues

---

## 1. wrangler.toml — Publisher

```toml
name = "order-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[queues.producers]]
binding = "ORDER_EVENTS"
queue  = "order-events"
```

---

## 2. wrangler.toml — Fan-out Router Worker

```toml
name = "order-event-router"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[queues.consumers]]
queue = "order-events"
max_batch_size = 50
max_batch_timeout = 2
max_retries = 3
dead_letter_queue = "order-events-dlq"

[[queues.producers]]
binding = "EMAIL_QUEUE"
queue  = "email-notifications"

[[queues.producers]]
binding = "INVENTORY_QUEUE"
queue  = "inventory-updates"

[[queues.producers]]
binding = "ANALYTICS_QUEUE"
queue  = "analytics-events"

[[queues.producers]]
binding = "FRAUD_QUEUE"
queue  = "fraud-checks"
```

---

## 3. Event Schema

```typescript
// src/events.ts

export type EventType =
  | "order.confirmed"
  | "order.cancelled"
  | "order.shipped";

export interface OrderEvent {
  eventId: string;       // idempotency key (UUID)
  type: EventType;
  occurredAt: string;    // ISO-8601
  orderId: string;
  customerId: string;
  totalCents: number;
  lineCount: number;
}
```

---

## 4. Publisher Worker

```typescript
// order-worker/src/index.ts
import { OrderEvent } from "./events";
import { OrderRepository } from "./db/orderRepository";

interface Env {
  DB: D1Database;
  ORDER_EVENTS: Queue<OrderEvent>;
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (req.method !== "POST" || new URL(req.url).pathname !== "/orders/confirm") {
      return new Response("Not found", { status: 404 });
    }

    const { orderId } = await req.json<{ orderId: string }>();
    const repo = new OrderRepository(env.DB);
    const order = await repo.findById(orderId);
    if (!order) return Response.json({ error: "Not found" }, { status: 404 });

    order.confirm();
    await repo.save(order);

    // Publish — fire-and-forget; Queue handles retries
    const event: OrderEvent = {
      eventId: crypto.randomUUID(),
      type: "order.confirmed",
      occurredAt: new Date().toISOString(),
      orderId: order.id,
      customerId: order.customerId,
      totalCents: order.totalCents,
      lineCount: order.lines.length,
    };

    // ctx.waitUntil keeps the isolate alive after the response is sent
    ctx.waitUntil(env.ORDER_EVENTS.send(event));

    return Response.json({ status: order.status });
  },
} satisfies ExportedHandler<Env>;
```

---

## 5. Fan-out Router Worker

```typescript
// order-event-router/src/index.ts
import { OrderEvent } from "./events";

interface Env {
  EMAIL_QUEUE: Queue<OrderEvent>;
  INVENTORY_QUEUE: Queue<OrderEvent>;
  ANALYTICS_QUEUE: Queue<OrderEvent>;
  FRAUD_QUEUE: Queue<OrderEvent>;
}

export default {
  async queue(
    batch: MessageBatch<OrderEvent>,
    env: Env,
    _ctx: ExecutionContext
  ): Promise<void> {
    for (const msg of batch.messages) {
      const event = msg.body;

      try {
        // Fan out to all subscriber queues in parallel
        await Promise.all([
          env.EMAIL_QUEUE.send(event),
          env.INVENTORY_QUEUE.send(event),
          env.ANALYTICS_QUEUE.send(event),
          env.FRAUD_QUEUE.send(event),
        ]);
        msg.ack();
      } catch (err) {
        // Retry the entire message — at-least-once guarantees apply
        console.error("Fan-out error for event", event.eventId, err);
        msg.retry();
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## 6. Example Subscriber: Email Notification Worker

```typescript
// email-worker/src/index.ts
import { OrderEvent } from "./events";

interface Env {
  EMAIL_QUEUE: Queue<OrderEvent>;
  MAILGUN_API_KEY: string;
}

async function sendConfirmationEmail(
  event: OrderEvent,
  apiKey: string
): Promise<void> {
  const res = await fetch("https://api.mailgun.net/v3/mg.example.com/messages", {
    method: "POST",
    headers: {
      Authorization: `Basic ${btoa(`api:${apiKey}`)}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({
      from: "orders@example.com",
      to: `customer+${event.customerId}@example.com`,
      subject: `Order ${event.orderId} confirmed`,
      text: `Your order (${event.lineCount} items, ${
        (event.totalCents / 100).toFixed(2)
      } USD) is confirmed.`,
    }),
  });
  if (!res.ok) throw new Error(`Mailgun error: ${res.status}`);
}

export default {
  async queue(
    batch: MessageBatch<OrderEvent>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await sendConfirmationEmail(msg.body, env.MAILGUN_API_KEY);
        msg.ack();
      } catch (err) {
        console.error("Email send failed", msg.body.eventId, err);
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## 7. Dead Letter Queue Monitor

```typescript
// dlq-monitor/src/index.ts
import { OrderEvent } from "./events";

interface Env {
  ALERTING_WEBHOOK: string;
}

export default {
  async queue(
    batch: MessageBatch<OrderEvent>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      console.error("DLQ message", JSON.stringify({
        eventId: msg.body.eventId,
        type: msg.body.type,
        orderId: msg.body.orderId,
        attempts: msg.attempts,
      }));

      // Alert on-call via webhook
      await fetch(env.ALERTING_WEBHOOK, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          text: `DLQ: event ${msg.body.eventId} (${msg.body.type}) exhausted retries`,
        }),
      });

      msg.ack(); // Acknowledge to clear from DLQ
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- **Synchronous side effects in the confirmation handler**: sending email inside the HTTP handler makes the endpoint's latency hostage to the email provider.
- **A single monolithic subscriber Worker**: one Worker handling email + inventory + analytics is tightly coupled — a deploy of one concern requires redeploying all.
- **Ignoring `msg.ack()` / `msg.retry()`**: unacknowledged messages are retried up to `max_retries` times then moved to the DLQ — always explicitly ack or retry.
- **Using event data as a command**: subscribers should react to facts (`order.confirmed`) not instructions (`send-email`) — keep events in past-tense domain language.

## Gotchas

- `Queue.send()` is async — always `await` it or pass it to `ctx.waitUntil()` to prevent the isolate from terminating before the message is enqueued.
- At-least-once delivery means subscribers **must be idempotent** — use `eventId` as an idempotency key in D1 or KV before processing.
- Cloudflare Queues batches messages: `batch.messages` may contain up to `max_batch_size` items; loop and ack/retry each individually to avoid losing progress on partial failures.
- Fan-out via a router Worker doubles queue hops and adds latency (~50–200 ms); for latency-sensitive paths, publish directly to per-subscriber queues from the origin Worker.
- Queue consumers have a 15-minute CPU time limit per invocation — long-running work should be offloaded to Durable Objects or external services.

## Verification

```bash
# Create queues
wrangler queues create order-events
wrangler queues create email-notifications
wrangler queues create inventory-updates
wrangler queues create analytics-events
wrangler queues create fraud-checks
wrangler queues create order-events-dlq

# Deploy all workers
wrangler deploy --config wrangler.order.toml
wrangler deploy --config wrangler.router.toml
wrangler deploy --config wrangler.email.toml

# Trigger an order confirmation
curl -s -X POST https://order-worker.example.workers.dev/orders/confirm \
  -H 'content-type: application/json' \
  -H 'authorization: Bearer <token>' \
  -d '{"orderId":"ord_001"}' | jq .

# Tail subscriber logs to verify fan-out
wrangler tail email-worker --format pretty
wrangler tail inventory-worker --format pretty
```

## Related

- `documentation/docs/policies/architecture/workers-decorator-pattern-middleware-chain.md`
- `documentation/docs/policies/architecture/workers-api-gateway-aggregator-service-bindings.md`
- `documentation/docs/policies/architecture/workers-data-mapper-pattern-d1-domain.md`

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/reference/javascript-apis/
- https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
