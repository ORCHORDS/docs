# Temporal Decoupling via Cloudflare Queues

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A user-facing API must send a confirmation email, charge a payment processor, update a CRM, and
write audit records — all triggered by a single form submission. Doing each synchronously increases
end-user latency by hundreds of milliseconds per step and couples the HTTP response to the
availability of three external services. A single slow email provider delays checkout for every
user. The solution is temporal decoupling: accept the user action immediately, return a 202
Accepted, and perform downstream work asynchronously, with automatic retries and backpressure.

## Context

Temporal decoupling separates the *time of cause* (user submits order) from the *time of effect*
(email sent, payment charged). Cloudflare Queues provides:

- **At-least-once delivery** — messages are retried until acknowledged or a dead-letter policy
  fires.
- **Batch consumption** — consumer Workers receive up to 100 messages per invocation, enabling
  efficient downstream batching.
- **Delay semantics** — messages can be delivered after a configurable delay for scheduled work.
- **Dead-letter queues (DLQ)** — exhausted messages are routed to a DLQ for human inspection or
  reprocessing.

This pattern differs from the Outbox pattern (transactional write + event in one DB transaction)
and from simple fire-and-forget `waitUntil()` calls, which have no retry guarantee.

## Publishing Side — Producer Worker

```typescript
// producer.ts
interface OrderEvent {
  type: "order.created";
  orderId: string;
  userId: string;
  items: { sku: string; qty: number }[];
  totalCents: number;
  createdAt: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/orders") {
      return new Response("Not Found", { status: 404 });
    }

    const body = await request.json<Omit<OrderEvent, "type" | "orderId" | "createdAt">>();

    // 1. Persist the order synchronously (fast, local DB).
    const orderId = crypto.randomUUID();
    await env.DB.prepare(
      "INSERT INTO orders (id, user_id, total_cents, status) VALUES (?, ?, ?, 'pending')"
    ).bind(orderId, body.userId, body.totalCents).run();

    // 2. Enqueue the event — fire and forget from the user's perspective.
    const event: OrderEvent = {
      type: "order.created",
      orderId,
      userId: body.userId,
      items: body.items,
      totalCents: body.totalCents,
      createdAt: new Date().toISOString(),
    };
    await env.ORDER_QUEUE.send(event, { contentType: "json" });

    // 3. Return immediately — downstream work happens independently.
    return Response.json({ orderId, status: "accepted" }, { status: 202 });
  },
} satisfies ExportedHandler<Env>;
```

## Consumer Worker — Fan-Out to Downstream Services

```typescript
// consumer.ts
interface OrderEvent {
  type: "order.created";
  orderId: string;
  userId: string;
  items: { sku: string; qty: number }[];
  totalCents: number;
  createdAt: string;
}

export default {
  async queue(batch: MessageBatch<OrderEvent>, env: Env): Promise<void> {
    // Process messages in parallel within the batch.
    await Promise.allSettled(
      batch.messages.map((msg) => processOrderEvent(msg, env))
    );
  },
} satisfies ExportedHandler<Env>;

async function processOrderEvent(
  msg: Message<OrderEvent>,
  env: Env
): Promise<void> {
  const event = msg.body;

  try {
    // Fan-out to three downstream services — each independently retriable.
    await Promise.all([
      sendConfirmationEmail(event, env),
      chargePayment(event, env),
      updateCrm(event, env),
    ]);

    // All succeeded — acknowledge so the message is not redelivered.
    msg.ack();
  } catch (err) {
    // Explicit retry: message will be redelivered after the retry delay.
    // Do NOT call msg.ack() — let the batch handler throw or call msg.retry().
    msg.retry({ delaySeconds: exponentialBackoff(msg.attempts) });
  }
}

function exponentialBackoff(attempt: number): number {
  // 10s, 20s, 40s, 80s, 160s … capped at 300s
  return Math.min(10 * Math.pow(2, attempt - 1), 300);
}

async function sendConfirmationEmail(event: OrderEvent, env: Env): Promise<void> {
  const res = await fetch("https://email.internal/send", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.EMAIL_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      to: event.userId + "@customers.example.com",
      subject: `Order ${event.orderId} confirmed`,
      orderId: event.orderId,
    }),
  });
  if (!res.ok) throw new Error(`Email API ${res.status}`);
}

async function chargePayment(event: OrderEvent, env: Env): Promise<void> {
  const res = await fetch("https://payments.internal/charge", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.PAYMENT_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ orderId: event.orderId, amountCents: event.totalCents }),
  });
  if (!res.ok) throw new Error(`Payment API ${res.status}`);
}

async function updateCrm(event: OrderEvent, env: Env): Promise<void> {
  const res = await fetch(`https://crm.internal/customers/${event.userId}/events`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.CRM_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ eventType: "purchase", orderId: event.orderId }),
  });
  if (!res.ok) throw new Error(`CRM API ${res.status}`);
}
```

## Dead-Letter Queue — Handling Exhausted Messages

```typescript
// dlq-consumer.ts
interface DeadLetter {
  originalMessage: unknown;
  failedAt: string;
  attempts: number;
}

export default {
  async queue(batch: MessageBatch<DeadLetter>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      // Persist to D1 for manual review / replay tooling.
      await env.DB.prepare(
        "INSERT INTO dead_letters (id, payload, failed_at, attempts) VALUES (?, ?, ?, ?)"
      ).bind(
        crypto.randomUUID(),
        JSON.stringify(msg.body),
        new Date().toISOString(),
        msg.attempts
      ).run();

      // Alert on-call if attempts suggest a systemic failure.
      if (msg.attempts >= 5) {
        await env.ALERT_QUEUE.send({ severity: "high", message: `DLQ: ${JSON.stringify(msg.body).slice(0, 200)}` });
      }

      msg.ack();
    }
  },
} satisfies ExportedHandler<Env>;
```

`wrangler.toml`:

```toml
[[queues.producers]]
binding = "ORDER_QUEUE"
queue = "order-events"

[[queues.producers]]
binding = "ALERT_QUEUE"
queue = "alert-events"

[[queues.consumers]]
queue = "order-events"
max_batch_size = 50
max_batch_timeout = 5
max_retries = 5
dead_letter_queue = "order-events-dlq"

[[queues.consumers]]
queue = "order-events-dlq"
max_batch_size = 10
max_batch_timeout = 10
max_retries = 0
```

## Anti-patterns

- **Acking before all work completes**: If you call `msg.ack()` at the start of processing and
  then a downstream call fails, the message is permanently lost with no retry.
- **Treating Queues like a synchronous RPC bus**: Queues introduce latency of 100ms–30s depending
  on batch fill time. Never use Queues when the producer needs an immediate result.
- **Using `waitUntil()` as a substitute**: `event.waitUntil()` has no retry guarantee. If the
  Worker isolate crashes after the response is sent, the promise never completes.
- **Mixing concerns in one Queue**: Put payment events and email events on separate queues so
  a slow email provider's retry storms do not delay payment processing.
- **Ignoring DLQ accumulation**: A growing DLQ is a leading indicator of a broken downstream
  service. Set up monitoring on DLQ message count as a key SLO signal.

## Gotchas

- Cloudflare Queues delivers messages **at-least-once** — your consumer must be idempotent. Use
  an idempotency key (e.g. `orderId + ":"+ actionType`) stored in KV or D1 to deduplicate.
- `max_batch_timeout` defaults to 0 (immediate delivery). Setting it to 5–10 seconds increases
  batch fill rates significantly, reducing consumer invocations and cost.
- Consumer Workers run in the same account but are **separate Workers** from producer Workers.
  They do not share environment variable values unless both are configured identically.
- Messages larger than 128 KB cannot be enqueued directly. Store large payloads in R2 and enqueue
  only the R2 object key (claim-check pattern).

## Verification

```bash
# Enqueue a test message and verify consumer processes it:
wrangler queues consumer create order-events --batch-size 1

curl -X POST https://api.example.com/orders \
  -H "Content-Type: application/json" \
  -d '{"userId":"u1","items":[{"sku":"W1","qty":1}],"totalCents":1999}'
# Expect: {"orderId":"...","status":"accepted"}

# Check DLQ is empty (or view accumulated failures):
wrangler queues message list order-events-dlq

# Monitor consumer invocations in dashboard:
# Workers & Pages → your-consumer-worker → Metrics
```

## Related

- `async-job-queue-cloudflare-queues-do.md`
- `at-least-once-delivery.md`
- `dead-letter-queue-architecture.md`
- `backpressure-patterns.md`
- `outbox-pattern.md`
- `claim-check-pattern-large-messages.md`

## Sources

- Cloudflare Queues documentation — https://developers.cloudflare.com/queues/
- Queues message batching guide — https://developers.cloudflare.com/queues/reference/batching-retries/
- Enterprise Integration Patterns, Hohpe & Woolf — "Message Channel" and "Dead Letter Channel"
