# Stripe Billing Meter Event Ingestion Pipeline with Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a usage-based SaaS product and need to send metered usage events to
Stripe Billing at high throughput (thousands of events per second) from
application code running inside Cloudflare Workers. You want the Workers edge
to be the single collection point for all meter events, with batching,
deduplication, and back-pressure so you never drop events or exhaust Stripe API
rate limits.

---

## Context

Stripe Billing Meters (GA in 2024, V2 events API in 2025) replace the older
Subscription Item Usage Records. The model:

- A **Meter** object defines an event name, value type (sum / max / count), and
  optional aggregation windows.
- Your code emits **Meter Events** (`stripe.v2.billing.meterEvents.create`) with
  a payload containing the customer's Stripe ID, event name, and a numeric value.
- Stripe aggregates events per billing period and synthesises usage on the
  Invoice automatically.

Key constraints:
- Stripe event API rate limit: 1,000 events / second per meter (higher on
  request).
- Events must be submitted with an `identifier` (idempotency key) to allow safe
  retries.
- Events are immutable once created; corrections require a MeterEventAdjustment.

---

## Architecture

```
Application Workers (edge)
  │  emit usage  ──►  Workers Queue (meter-events-raw)
  │
  ▼
Queue Consumer Worker (batch up to 500 items)
  │  deduplicate via KV ──►  Cloudflare KV (identifier seen?)
  │  POST /v2/billing/meter_events  ──►  Stripe API
  │  on failure ──►  DLQ (meter-events-dlq)
```

Using Cloudflare Queues as the buffer decouples the emitting Workers from the
Stripe API throughput window, absorbs bursts, and gives you durable retries.

---

## Step 1: Create a Stripe Meter

```typescript
// scripts/create-meter.ts  (run once, store meter.id in env)
import Stripe from 'stripe';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

const meter = await stripe.billing.meters.create({
  display_name: 'API Calls',
  event_name: 'api_call',
  default_aggregation: { formula: 'sum' },
  value_settings: { event_payload_key: 'value' },
  customer_mapping: {
    type: 'by_id',
    event_payload_key: 'stripe_customer_id',
  },
});

console.log('Meter ID:', meter.id);
// Store as STRIPE_METER_ID in wrangler.toml [vars] or Secrets
```

---

## Step 2: Enqueue Usage Events from Application Workers

```typescript
// src/usage-emitter.ts
interface Env {
  METER_EVENTS_QUEUE: Queue;
}

interface UsageEvent {
  stripe_customer_id: string;
  event_name: string;   // must match meter's event_name
  value: number;
  identifier: string;   // globally unique — use request ID or hash
  timestamp?: number;   // unix seconds; omit = now
}

export async function recordUsage(
  customerId: string,
  value: number,
  requestId: string,
  env: Env,
): Promise<void> {
  const event: UsageEvent = {
    stripe_customer_id: customerId,
    event_name: 'api_call',
    value,
    identifier: requestId,   // request ID is already globally unique
  };

  await env.METER_EVENTS_QUEUE.send(event);
}
```

---

## Step 3: Batch Consumer Worker

```typescript
// src/meter-event-consumer.ts
import Stripe from 'stripe';

interface Env {
  STRIPE_SECRET_KEY: string;
  STRIPE_METER_ID: string;
  SEEN_IDENTIFIERS: KVNamespace;  // TTL = 48 h; Stripe dedup window is 24 h
  METER_EVENTS_DLQ: Queue;
}

interface UsageEvent {
  stripe_customer_id: string;
  event_name: string;
  value: number;
  identifier: string;
  timestamp?: number;
}

export default {
  async queue(batch: MessageBatch<UsageEvent>, env: Env): Promise<void> {
    const stripe = new Stripe(env.STRIPE_SECRET_KEY);

    // Deduplicate within the batch by identifier
    const seen = new Set<string>();
    const unique: Array<{ msg: Message<UsageEvent>; event: UsageEvent }> = [];

    for (const msg of batch.messages) {
      const ev = msg.body;
      if (seen.has(ev.identifier)) {
        msg.ack();  // duplicate within this batch
        continue;
      }
      seen.add(ev.identifier);

      // Check KV for cross-batch deduplication
      const already = await env.SEEN_IDENTIFIERS.get(ev.identifier);
      if (already !== null) {
        msg.ack();
        continue;
      }

      unique.push({ msg, event: ev });
    }

    if (unique.length === 0) return;

    // Stripe V2 batch endpoint (up to 500 events per call)
    // Uses stripe-node SDK v16+ with v2 resource access
    const payload = unique.map(({ event: ev }) => ({
      event_name: ev.event_name,
      payload: {
        stripe_customer_id: ev.stripe_customer_id,
        value: String(ev.value),
      },
      identifier: ev.identifier,
      ...(ev.timestamp ? { timestamp: new Date(ev.timestamp * 1000).toISOString() } : {}),
    }));

    try {
      // stripe.v2.billing.meterEvents.createBatch is the batch endpoint
      await (stripe as any).v2.billing.meterEvents.createBatch(
        { meter: env.STRIPE_METER_ID },
        { events: payload },
      );

      // Mark identifiers as seen in KV (48 h TTL)
      const kvWrites = unique.map(({ event: ev }) =>
        env.SEEN_IDENTIFIERS.put(ev.identifier, '1', { expirationTtl: 172800 }),
      );
      await Promise.all(kvWrites);

      // Ack all successfully sent messages
      for (const { msg } of unique) msg.ack();
    } catch (err: any) {
      console.error('Stripe meter batch failed:', err.message);

      // On rate limit (429) or transient error: nack to retry via queue
      if (err.statusCode === 429 || err.statusCode >= 500) {
        for (const { msg } of unique) msg.retry();
      } else {
        // Non-retriable (e.g., 400 bad payload): send to DLQ
        for (const { msg, event } of unique) {
          await env.METER_EVENTS_DLQ.send({
            event,
            error: err.message,
            timestamp: Date.now(),
          });
          msg.ack();
        }
      }
    }
  },
};
```

---

## wrangler.toml Configuration

```toml
[[queues.producers]]
queue = "meter-events-raw"
binding = "METER_EVENTS_QUEUE"

[[queues.producers]]
queue = "meter-events-dlq"
binding = "METER_EVENTS_DLQ"

[[queues.consumers]]
queue = "meter-events-raw"
max_batch_size = 500
max_batch_timeout = 5       # seconds — balance latency vs batch efficiency
max_retries = 3
dead_letter_queue = "meter-events-dlq"

[[kv_namespaces]]
binding = "SEEN_IDENTIFIERS"
id = "YOUR_KV_NAMESPACE_ID"
```

---

## Handling MeterEventAdjustments

If you need to correct a previously submitted event (overcounting, wrong value):

```typescript
async function cancelMeterEvent(identifier: string, stripe: Stripe): Promise<void> {
  await (stripe as any).v2.billing.meterEventAdjustments.create({
    event_name: 'api_call',
    cancel: { identifier },
    type: 'cancel',
  });
  // Note: adjustments apply within the same billing period only
}
```

---

## Anti-patterns

- **Calling Stripe directly from the hot path** — synchronous `fetch` to Stripe
  in the request handler adds 50–200 ms latency and breaks under burst load.
  Always go through the Queue.
- **Using wall-clock time as identifier** — concurrent Workers produce identical
  millisecond timestamps. Use a UUID or ULID derived from the request ID.
- **Omitting identifier entirely** — without it, Stripe cannot deduplicate retries
  and you double-count usage.
- **Setting `max_batch_size` > 500** — Stripe's batch endpoint cap is 500; a
  larger batch errors with HTTP 400.
- **Storing identifiers in D1 instead of KV** — KV has sub-millisecond read
  latency for the dedup check; D1 read latency is higher and D1 has per-row
  write limits that don't suit high-volume append workloads.

---

## Gotchas

- **`timestamp` must be within the billing period** — Stripe rejects events with
  a `timestamp` older than the current open billing period start. Backfill
  requires the `create_billing_period_simulation` flag (Stripe support only).
- **The V2 API uses a different base URL** (`https://api.stripe.com/v2/`) and
  stripe-node v16+ switches automatically when you use `stripe.v2.*`.
- **Meter event counts lag invoices by ~1 minute** — do not poll
  `stripe.billing.meterEventSummaries.list()` immediately after submission and
  expect current values.
- **DLQ events need human review** — a 400 from Stripe often indicates a missing
  `stripe_customer_id` mapping or a deleted customer. Build a DLQ dashboard.
- **KV TTL must exceed Stripe's dedup window** — Stripe deduplicates on
  `identifier` for 24 hours. Set KV TTL to at least 172800 seconds (48 h) for
  safety margin.

---

## Verification

```bash
# 1. Send a test usage event
curl -X POST https://your-worker.example.com/usage \
  -H 'Authorization: Bearer $API_TOKEN' \
  -d '{"customerId":"cus_test123","value":42,"requestId":"req_abc123"}'

# 2. Check Stripe meter summaries
stripe billing meter_event_summaries list \
  --meter=mtr_XXXX --customer=cus_test123

# 3. Inspect the queue consumer logs
wrangler tail --format=json | jq 'select(.message | test("meter"))'

# 4. Check KV for stored identifier
wrangler kv key get --namespace-id=XXXX req_abc123
```

---

## Related

- `stripe-metered-billing.md`
- `stripe-meter-event-v2-idempotency-and-lag.md`
- `stripe-meter-event-adjustment-window-and-reconciliation.md`
- `stripe-usage-based-billing.md`
- `payment-retry-exponential-backoff-cloudflare-queues.md`
- `idempotency-keys-payment-apis.md`

---

## Sources

- Stripe Billing Meters: https://docs.stripe.com/billing/subscriptions/usage-based/recording-usage
- Stripe V2 Meter Events API: https://docs.stripe.com/api/v2/billing/meter-events
- Cloudflare Queues batching: https://developers.cloudflare.com/queues/platform/configuration/
- stripe-node v16 V2 support: https://github.com/stripe/stripe-node/blob/master/CHANGELOG.md
