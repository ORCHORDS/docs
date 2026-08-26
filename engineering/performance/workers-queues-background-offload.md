# Workers Queues — Background Job Offload for Response Latency

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A checkout endpoint spends 380 ms doing work the user does not need before the response: sending a confirmation email, writing to an analytics warehouse, resizing an uploaded image, and triggering a webhook to a warehouse management system.  The user's mobile response time is 520 ms instead of the 140 ms it would be if those tasks were deferred.  On a slow 4G connection with high base latency, every unnecessary millisecond of server-side work translates directly to a worse perceived experience.  You need a reliable mechanism to push work off the critical response path.

## Context

**Cloudflare Workers Queues** is a durable, at-least-once message queue with native Workers producer and consumer support.  A producer Worker enqueues a message (< 1 ms overhead) and returns a response immediately.  A consumer Worker processes the message asynchronously in a separate invocation.  The consumer runs outside the HTTP request lifecycle — it has its own CPU budget and is not visible to the user's browser.

Mobile vs desktop distinction:
- Mobile clients on 4G are more sensitive to response latency because the base RTT (40–120 ms) already consumes a large fraction of the user's latency budget.
- An extra 380 ms server-side processing on desktop broadband (20 ms RTT) is annoying; on mobile cellular (80 ms RTT) it feels like a stall.
- Offloading 380 ms of background work reduces p95 response time from 600 ms to 180 ms — the difference between a "good" and "needs improvement" TTFB.

Workers Queues guarantees:
- **At-least-once delivery**: messages are delivered at least once; your consumer must be idempotent for operations like email send (use a deduplication key).
- **Durable**: messages survive Worker restarts and CF edge incidents.
- **Max delivery delay**: configurable up to 12 hours (useful for scheduled work like sending a follow-up email 24 h later).
- **Batch delivery**: consumer receives up to 100 messages per invocation (configurable) — efficient for warehouse batch writes.

## Section 1 — Queue Setup

```toml
# wrangler.toml

[[queues.producers]]
binding  = "CHECKOUT_QUEUE"
queue    = "checkout-events"

[[queues.consumers]]
queue              = "checkout-events"
max_batch_size     = 10        # process up to 10 messages per consumer invocation
max_batch_timeout  = 5         # wait up to 5 s to fill a batch before invoking
max_retries        = 3         # retry failed messages up to 3 times
dead_letter_queue  = "checkout-events-dlq"
```

Create the queue:

```bash
wrangler queues create checkout-events
wrangler queues create checkout-events-dlq
```

## Section 2 — Producer: Offloading Checkout Work

```javascript
// src/checkout.js (Producer Worker)
export default {
  async fetch(request, env) {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const body = await request.json();
    const { orderId, userId, email, items, total } = body;

    // --- SYNCHRONOUS: only what the user needs now ---
    // 1. Write the order to D1 (user needs order ID immediately)
    const order = await env.DB.prepare(
      `INSERT INTO orders (id, user_id, status, total_p, created_at)
       VALUES (?, ?, 'pending', ?, ?)
       RETURNING id`
    ).bind(orderId, userId, total, Date.now()).first();

    // 2. Return immediately — don't wait for email, analytics, webhooks
    const response = Response.json(
      { ok: true, orderId: order.id },
      { status: 201 }
    );

    // --- ASYNCHRONOUS: enqueue background tasks ---
    // Each task is a separate message so they can be retried independently
    await env.CHECKOUT_QUEUE.sendBatch([
      {
        body: { type: 'send_confirmation_email', orderId, email, items, total },
        contentType: 'json',
      },
      {
        body: { type: 'analytics_event', orderId, userId, items, total },
        contentType: 'json',
      },
      {
        body: { type: 'wms_webhook', orderId, items },
        contentType: 'json',
        // Delay this 2 s to allow D1 write to replicate before WMS reads it
        delaySeconds: 2,
      },
    ]);

    return response;
    // Total time: D1 write (30–60 ms) + Queue sendBatch (< 5 ms) = ~65 ms
    // Without Queue: 65 ms + email (200 ms) + analytics (80 ms) + webhook (150 ms) = ~495 ms
  },
};
```

`sendBatch` takes an array of messages and is atomic — either all enqueue or none do.  On failure, throw and let the client retry; the D1 insert is not yet committed if the Worker threw before returning (Workers are transactional at the JS level — if you throw, D1 prepared statements that were already executed have already committed).  Use `ON CONFLICT DO NOTHING` or a UUID-based `orderId` to make the D1 write idempotent.

## Section 3 — Consumer: Processing Background Tasks

```javascript
// src/checkout-consumer.js (Consumer Worker)
export default {
  async queue(batch, env) {
    for (const message of batch.messages) {
      const task = message.body;

      try {
        switch (task.type) {
          case 'send_confirmation_email':
            await sendEmail(env, task);
            break;
          case 'analytics_event':
            await writeAnalytics(env, task);
            break;
          case 'wms_webhook':
            await fireWmsWebhook(env, task);
            break;
          default:
            // Unknown type — ack so it doesn't retry forever
            message.ack();
            continue;
        }
        message.ack(); // explicit ack on success
      } catch (err) {
        // retry — message.retry() is implicit if neither ack nor retry is called,
        // but explicit is clearer
        message.retry({ delaySeconds: 10 });
        // Log to Analytics Engine for visibility
        env.AE?.writeDataPoint({
          blobs: [task.type, err.message?.slice(0, 200) ?? ''],
          doubles: [1],
        });
      }
    }
  },
};

async function sendEmail(env, { orderId, email, items, total }) {
  // Deduplication: use orderId as idempotency key so resent emails don't duplicate
  const already = await env.DB.prepare(
    `SELECT 1 FROM email_log WHERE order_id = ? AND type = 'confirmation'`
  ).bind(orderId).first();
  if (already) return; // already sent — safe to ack

  await fetch('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.SENDGRID_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      to: [{ email }],
      from: { email: 'orders@example.com' },
      subject: `Order ${orderId} confirmed`,
      content: [{ type: 'text/plain', value: `Your order total: £${total / 100}` }],
    }),
  });

  await env.DB.prepare(
    `INSERT INTO email_log (order_id, type, sent_at) VALUES (?, 'confirmation', ?)`
  ).bind(orderId, Date.now()).run();
}

async function writeAnalytics(env, { orderId, userId, items, total }) {
  env.AE.writeDataPoint({
    blobs: ['purchase', userId],
    doubles: [total, items.length],
    indexes: [userId],
  });
}

async function fireWmsWebhook(env, { orderId, items }) {
  const res = await fetch(env.WMS_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Secret': env.WMS_SECRET },
    body: JSON.stringify({ orderId, items }),
  });
  if (!res.ok) throw new Error(`WMS webhook failed: ${res.status}`);
}
```

Consumer Workers run on separate CPU budgets and can use up to 30 s CPU time per invocation (vs 10 ms for standard request Workers).  This makes them suitable for heavy tasks like image processing, PDF generation, or multi-step API chains.

## Section 4 — Monitoring and Dead Letter Queue

Messages that exceed `max_retries` are moved to the dead letter queue (`checkout-events-dlq`).  Monitor it to catch systemic failures:

```javascript
// src/dlq-consumer.js
export default {
  async queue(batch, env) {
    for (const msg of batch.messages) {
      // Alert via PagerDuty or write to Analytics Engine for visibility
      env.AE?.writeDataPoint({
        blobs: ['dlq', msg.body?.type ?? 'unknown'],
        doubles: [1],
      });
      console.error('DLQ message:', JSON.stringify(msg.body));
      msg.ack(); // ack so it doesn't loop forever in the DLQ
    }
  },
};
```

```toml
[[queues.consumers]]
queue          = "checkout-events-dlq"
max_batch_size = 50
```

**Key metrics to monitor** (via Workers Analytics in CF dashboard):
- `queue_messages_acknowledged`: healthy consumer throughput
- `queue_messages_retried`: elevated = external dependency failures
- `queue_messages_dead_lettered`: zero should be the norm; spikes indicate systemic failure

## Anti-patterns

- **Using Queues for synchronous work the user is waiting for** — if the user needs the result before you respond, Queues are the wrong tool.  Use a regular `await fetch()` or D1 query in the request handler.
- **Not making consumers idempotent** — at-least-once delivery means a consumer may process the same message twice (transient ack failure).  Always guard on a deduplication key (orderId, messageId) before side-effecting operations.
- **Sending unbounded message bodies** — Queues has a 128 KB per-message limit.  Do not enqueue large payloads (order line-item arrays with 500 items, base64 images).  Store large data in R2 and enqueue only the R2 key.
- **Unlimited retry without delay** — `max_retries: 3` with no `delaySeconds` on retry hammers a failing external API (SendGrid outage) in rapid succession.  Always add exponential backoff via `message.retry({ delaySeconds: n })`.
- **Single message type per queue** — mixing high-priority tasks (fraud alerts) with low-priority ones (analytics events) in one queue means a slow analytics write holds up fraud detection.  Use separate queues for different priority tiers.

## Gotchas

- `sendBatch` is a single atomic operation; a network error means none of the messages were enqueued.  The Producer Worker should retry on transient errors or use Cloudflare Workflows for orchestration that requires guaranteed delivery of the enqueue itself.
- Queue consumers are invoked by the CF runtime — they do not run inside the response path.  You cannot use `waitUntil` to run them; they are entirely separate Worker invocations triggered by the queue.
- The `delaySeconds` option delays the initial delivery, but does not reset between retries.  If you want growing backoff, use `message.retry({ delaySeconds: attempt * 10 })` — but `attempt` is not exposed natively; you must pass it in the message body.
- Workers Queues does not support message ordering within a batch (FIFO is per-queue, not per-batch).  If operation ordering matters (e.g., create user then send welcome email), use Cloudflare Workflows or encode explicit ordering in the consumer.
- Consumer Workers for `checkout-events` must be deployed with the same `wrangler.toml` that declares the `[[queues.consumers]]` binding.  A consumer deployed without the binding will not receive messages even if the queue exists.

## Verification

1. Submit a test checkout via `curl -X POST /checkout`.  Response should arrive in < 150 ms.  Confirm the confirmation email arrives within 10 s (consumer processing time + SendGrid delivery).
2. Simulate a SendGrid outage by temporarily setting `SENDGRID_API_KEY` to an invalid value.  Confirm the message retries 3 times (visible in CF Queue dashboard) then moves to DLQ.
3. Check the CF Workers analytics dashboard → Queues tab.  Verify `queue_messages_acknowledged` increments and `queue_messages_dead_lettered` stays at 0.
4. With Analytics Engine collecting queue DLQ alerts, query: `SELECT count() FROM worker_metrics WHERE blob1 = 'dlq' AND timestamp >= NOW() - INTERVAL '1' HOUR` — should return 0.

## Related

- `workers-cpu-time-optimization.md` — keeping consumer Worker CPU within budget
- `cloudflare-workers-performance.md` — general Worker performance model
- `analytics-engine-rum-web-vitals.md` — using AE for queue monitoring
- `ttfb-optimization.md` — TTFB gains from response-path offloading
- `durable-objects-low-latency-stateful.md` — when stateful coordination is needed alongside queuing

## Sources

- Cloudflare Workers Queues documentation: https://developers.cloudflare.com/queues/
- Queues producer API: https://developers.cloudflare.com/queues/reference/javascript-apis/
- Dead letter queues: https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- Cloudflare Workflows (orchestration): https://developers.cloudflare.com/workflows/
