# k6 Workers Queues Consumer Throughput Benchmark

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare Workers Queue consumer processes batches of messages but the team does not know the maximum sustained message throughput before batches start arriving late, messages hit the retry limit, or the consumer Worker exceeds its CPU budget. The goal is a repeatable k6 benchmark that enqueues messages at a controlled rate, monitors consumer latency from enqueue to ack, and produces actionable p95/p99 metrics.

## Context

Cloudflare Queues decouple a producer Worker from a consumer Worker. The producer sends messages via `env.MY_QUEUE.send()` or `sendBatch()`. The platform delivers batches to the consumer's `queue()` handler, retrying failed messages according to the queue's retry configuration. k6 drives the producer endpoint at a parameterised rate; a secondary instrumentation layer (Analytics Engine or a Durable Object counter) captures end-to-end latency from produce to acknowledge, since k6 only observes the HTTP response from the producer, not the async consumer execution.

---

## Strategy 1 — Ramping producer throughput benchmark

Gradually increase the message enqueue rate to find the saturation point where consumer lag starts growing.

```javascript
// k6/workers-queues-throughput.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';

export const options = {
  scenarios: {
    ramp_producer: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 20,
      maxVUs: 100,
      stages: [
        { target: 10, duration: '1m' },   // warm up at 10 msg/s
        { target: 50, duration: '2m' },   // ramp to 50 msg/s
        { target: 100, duration: '2m' },  // ramp to 100 msg/s
        { target: 200, duration: '2m' },  // stress at 200 msg/s
        { target: 0, duration: '30s' },   // cool down
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<150'],
    http_req_failed: ['rate<0.005'],
  },
};

const messagesSent = new Counter('messages_sent');
const enqueueLatency = new Trend('enqueue_latency_ms', true);

export default function () {
  const payload = JSON.stringify({
    event: 'order.created',
    orderId: `ord-${Date.now()}-${__VU}`,
    items: [{ sku: 'ITEM-42', qty: Math.ceil(Math.random() * 5) }],
    enqueuedAt: Date.now(),
  });

  const res = http.post(
    'https://producer.example.workers.dev/enqueue',
    payload,
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(res, {
    'accepted 202': (r) => r.status === 202,
    'has message_id': (r) => {
      try {
        return Boolean(JSON.parse(r.body).message_id);
      } catch {
        return false;
      }
    },
  });

  enqueueLatency.add(res.timings.duration);
  messagesSent.add(1);
}
```

---

## Strategy 2 — Batch send benchmark

Compare per-message vs `sendBatch()` throughput. The producer endpoint wraps `sendBatch()` and k6 sends fewer HTTP requests but larger payloads.

```javascript
// k6/workers-queues-batch.js
import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

export const options = {
  scenarios: {
    batch_producer: {
      executor: 'constant-arrival-rate',
      rate: 20,            // 20 batch requests/s = up to 2000 messages/s with batch size 100
      timeUnit: '1s',
      duration: '3m',
      preAllocatedVUs: 10,
    },
  },
  thresholds: {
    'http_req_duration{endpoint:batch}': ['p(95)<250'],
    http_req_failed: ['rate<0.01'],
  },
};

const BATCH_SIZE = 50;
const batchMessagesSent = new Counter('batch_messages_sent');

function buildBatch(size) {
  return Array.from({ length: size }, (_, i) => ({
    body: JSON.stringify({
      event: 'inventory.updated',
      sku: `SKU-${i % 200}`,
      delta: Math.floor(Math.random() * 10) - 5,
      ts: Date.now(),
    }),
    contentType: 'json',
  }));
}

export default function () {
  const res = http.post(
    'https://producer.example.workers.dev/enqueue-batch',
    JSON.stringify({ messages: buildBatch(BATCH_SIZE) }),
    {
      headers: { 'Content-Type': 'application/json' },
      tags: { endpoint: 'batch' },
    }
  );

  check(res, {
    'batch accepted': (r) => r.status === 202,
    'all messages queued': (r) => {
      try {
        return JSON.parse(r.body).queued === BATCH_SIZE;
      } catch {
        return false;
      }
    },
  });

  batchMessagesSent.add(BATCH_SIZE);
}
```

---

## Strategy 3 — End-to-end latency measurement via a probe endpoint

Because the consumer runs asynchronously, k6 cannot directly measure consume latency. A probe endpoint reads latency samples stored by the consumer into a Durable Object, letting k6 pull metrics via polling.

```typescript
// workers/src/consumer.ts
export default {
  async queue(batch: MessageBatch<OrderEvent>, env: Env): Promise<void> {
    const latencies: number[] = [];

    for (const message of batch.messages) {
      const body = message.body as OrderEvent;
      const latencyMs = Date.now() - body.enqueuedAt;
      latencies.push(latencyMs);
      // process message...
      message.ack();
    }

    // Write p50/p95 of this batch to a Durable Object for k6 to poll
    const stub = env.LATENCY_TRACKER.get(env.LATENCY_TRACKER.idFromName('global'));
    await stub.recordBatch(latencies);
  },
};
```

```javascript
// k6/workers-queues-e2e-latency.js — polling scenario
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

export const options = {
  scenarios: {
    producer: {
      executor: 'constant-arrival-rate',
      rate: 50,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 10,
      exec: 'produce',
    },
    latency_poller: {
      executor: 'constant-vus',
      vus: 1,
      duration: '5m',
      exec: 'pollLatency',
    },
  },
};

const e2eLatency = new Trend('queue_e2e_latency_ms', true);

export function produce() {
  http.post(
    'https://producer.example.workers.dev/enqueue',
    JSON.stringify({ event: 'test', enqueuedAt: Date.now() }),
    { headers: { 'Content-Type': 'application/json' } }
  );
}

export function pollLatency() {
  const res = http.get('https://producer.example.workers.dev/latency-stats');
  if (res.status === 200) {
    const stats = JSON.parse(res.body);
    if (typeof stats.latest_p95_ms === 'number') {
      e2eLatency.add(stats.latest_p95_ms);
    }
    check(res, {
      'consumer p95 latency < 5s': () => stats.latest_p95_ms < 5000,
    });
  }
  sleep(5);
}
```

---

## Strategy 4 — DLQ saturation test

Deliberately enqueue malformed messages to verify the DLQ fills correctly and does not block valid message processing.

```javascript
// k6/workers-queues-dlq-saturation.js
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 5,
  iterations: 100,
};

export default function (data) {
  // Mix of valid and invalid messages (1 in 5 invalid)
  const isPoison = __ITER % 5 === 0;

  const payload = isPoison
    ? JSON.stringify({ broken: true, noRequiredFields: true })
    : JSON.stringify({ event: 'order.created', orderId: `ord-${__ITER}`, enqueuedAt: Date.now() });

  const res = http.post(
    'https://producer.example.workers.dev/enqueue',
    payload,
    { headers: { 'Content-Type': 'application/json' }, tags: { type: isPoison ? 'poison' : 'valid' } }
  );

  // Producer always accepts — consumer routing to DLQ is async
  check(res, { 'producer accepted': (r) => r.status === 202 });
}

export function handleSummary(data) {
  console.log('Poison messages sent:', data.metrics['http_reqs{type:poison}']?.values?.count ?? 0);
  console.log('Valid messages sent:', data.metrics['http_reqs{type:valid}']?.values?.count ?? 0);
  return {};
}
```

---

## Strategy 5 — Consumer Worker source (reference)

The producer Worker that k6 targets, using `sendBatch()` for efficiency.

```typescript
// workers/src/producer.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const url = new URL(request.url);

    if (url.pathname === '/enqueue') {
      const body = await request.json<Record<string, unknown>>();
      await env.ORDER_QUEUE.send(body, { contentType: 'json' });
      return Response.json({ message_id: crypto.randomUUID() }, { status: 202 });
    }

    if (url.pathname === '/enqueue-batch') {
      const { messages } = await request.json<{
        messages: Array<{ body: string; contentType: 'json' | 'text' }>;
      }>();
      const batch = messages.map((m) => ({
        body: m.contentType === 'json' ? JSON.parse(m.body) : m.body,
        contentType: m.contentType,
      }));
      await env.ORDER_QUEUE.sendBatch(batch);
      return Response.json({ queued: batch.length }, { status: 202 });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

---

## Anti-patterns

- Using `executor: constant-vus` for a throughput test — VU count does not translate linearly to message rate when request latency varies. Use `ramping-arrival-rate` instead.
- Asserting consumer processing happened inside the same k6 request check — the consumer is async and will not have run by the time the HTTP response returns.
- Treating HTTP 202 from the producer as proof of successful consumption — it only means the message was accepted by the queue. Consumer errors still need separate monitoring.
- Setting `maxRetries` on the queue to 0 during benchmarks — this causes poison messages to drop silently without populating the DLQ, masking consumer bugs.
- Running the benchmark against production queues — message volume from load tests consumes real Queue message quotas and pollutes production data.

---

## Gotchas

- Cloudflare Queues deliver messages in batches on their own schedule (up to 250 messages per batch, or after a few seconds of wait). The batch interval is not under the load test's control.
- Consumer Workers have a separate CPU budget per invocation. A consumer that processes 250 messages per batch may use significantly more CPU than one processing 10, even if the per-message logic is constant.
- The `ramping-arrival-rate` executor requires `preAllocatedVUs`. If the rate ramp is steep and VUs are exhausted, k6 emits `dropped_iterations` — monitor this counter to detect saturation at the k6 level rather than the Worker level.
- k6 metrics tags must be set at the HTTP call site. Tags cannot be added to an existing metric value after the fact.
- Queue consumer retries count against the Worker's request budget. High retry rates from malformed messages can exhaust daily request limits on free plans.

---

## Verification

```bash
# Baseline: 10 msg/s for 2 minutes, confirm < 1% failure
k6 run --vus 5 --duration 2m \
  --env WORKER_HOST=https://producer.example.workers.dev \
  k6/workers-queues-throughput.js

# Stress: ramp to 200 msg/s, watch for dropped_iterations in summary
k6 run k6/workers-queues-throughput.js \
  --summary-trend-stats='avg,p(50),p(95),p(99),max'

# Verify DLQ receives poison messages (check Cloudflare dashboard > Queues > DLQ)
k6 run --vus 5 --iterations 100 k6/workers-queues-dlq-saturation.js
```

---

## Related

- `cloudflare-queues-miniflare-batch-testing.md` — unit-level batch testing with Miniflare
- `workers-queues-retry-dlq-testing.md` — DLQ and retry configuration testing
- `k6-load-testing-cloudflare-workers-api.md` — general Workers API load testing
- `k6-performance-regression-testing.md` — CI integration for k6
- `performance-testing-k6.md` — k6 fundamentals

---

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/reference/limits/
- https://k6.io/docs/using-k6/scenarios/executors/ramping-arrival-rate/
- https://k6.io/docs/javascript-api/k6-metrics/
- https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
