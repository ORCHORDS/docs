# Adaptive Backpressure and Load Shedding on Workers and Queues

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A surge of inbound traffic causes Queue consumers to fall behind, D1 write latency to
spike, and Durable Object storage operations to time out. Retries compound the problem
because the same message re-enters the queue while new messages are still arriving.
Eventually the backlog grows faster than consumers can drain it. You need a mechanism
to *slow the producer* (backpressure) or *discard low-priority work* (load shedding)
before the system saturates.

## Context

Cloudflare Workers cannot directly observe Queue depth or D1 saturation metrics at
runtime — there is no blocking `await queue.waitForCapacity()` API. Backpressure must
therefore be implemented *collaboratively*: consumers publish health signals (to KV or
a Durable Object), and producers read those signals before enqueueing new work. This
is the *reactive pull* model adapted to an event-driven, serverless environment.

Two complementary techniques:

1. **Backpressure signalling** — a consumer writes a `high_load` flag to KV when it
   detects latency or failure-rate thresholds; producers check the flag before sending.
2. **Load shedding** — the producer (or an edge Worker acting as a gateway) actively
   drops or delays low-priority requests when under pressure, returning `HTTP 429` or
   `503` to callers instead of enqueueing work that cannot be processed in time.

Both techniques require:
- A shared, fast-readable signal store (KV for read-heavy, Durable Objects for
  precise atomic counters).
- A clear prioritisation of work (shed lowest-value traffic first).
- Graceful degradation that preserves correctness for committed work (idempotency keys,
  Saga compensation).

## Consumer Health Beacon

```typescript
// consumer/health-beacon.ts
// Called at the end of each Queue batch to report consumer health into KV.

export interface ConsumerHealth {
  status: 'ok' | 'degraded' | 'overloaded';
  p99LatencyMs: number;
  failureRate: number;    // fraction 0–1
  queueDepthEstimate: number;
  reportedAt: string;
}

export async function reportHealth(
  health: ConsumerHealth,
  kv: KVNamespace,
  namespace: string,
): Promise<void> {
  await kv.put(
    `backpressure:${namespace}`,
    JSON.stringify(health),
    { expirationTtl: 120 }, // auto-expire so stale signals do not block indefinitely
  );
}

// Measure health inside a Queue consumer batch
export async function processBatchWithHealthTracking(
  batch: MessageBatch,
  kv: KVNamespace,
  processOne: (msg: Message) => Promise<void>,
): Promise<void> {
  const latencies: number[] = [];
  let failures = 0;

  for (const msg of batch.messages) {
    const t0 = performance.now();
    try {
      await processOne(msg);
      msg.ack();
    } catch (err) {
      failures++;
      msg.retry({ delaySeconds: 30 });
    } finally {
      latencies.push(performance.now() - t0);
    }
  }

  const sorted = latencies.slice().sort((a, b) => a - b);
  const p99 = sorted[Math.floor(sorted.length * 0.99)] ?? 0;
  const failureRate = failures / batch.messages.length;

  const status: ConsumerHealth['status'] =
    failureRate > 0.1 || p99 > 5000 ? 'overloaded'
    : failureRate > 0.05 || p99 > 2000 ? 'degraded'
    : 'ok';

  await reportHealth(
    { status, p99LatencyMs: p99, failureRate, queueDepthEstimate: 0, reportedAt: new Date().toISOString() },
    kv,
    batch.queue,
  );
}
```

## Producer-Side Backpressure Gate

```typescript
// producer/backpressure-gate.ts
import { ConsumerHealth } from '../consumer/health-beacon';

export type BackpressureDecision = 'accept' | 'delay' | 'shed';

export interface GateConfig {
  lowPriorityShedThreshold: 'degraded' | 'overloaded';
  highPriorityShedThreshold: 'overloaded';
}

const DEFAULT_CONFIG: GateConfig = {
  lowPriorityShedThreshold: 'degraded',
  highPriorityShedThreshold: 'overloaded',
};

export async function checkBackpressure(
  queueName: string,
  priority: 'high' | 'low',
  kv: KVNamespace,
  config = DEFAULT_CONFIG,
): Promise<BackpressureDecision> {
  const raw = await kv.get(`backpressure:${queueName}`, 'json') as ConsumerHealth | null;

  // No signal → assume healthy (fail open for availability)
  if (!raw) return 'accept';

  const { status } = raw;

  if (priority === 'low') {
    if (status === config.lowPriorityShedThreshold || status === 'overloaded') {
      return 'shed';
    }
    if (status === 'degraded') return 'delay';
  }

  if (priority === 'high' && status === config.highPriorityShedThreshold) {
    return 'shed';
  }

  return 'accept';
}

// Gateway Worker that enforces the decision
export async function gatewayEnqueue<T>(
  payload: T,
  priority: 'high' | 'low',
  queueName: string,
  queue: Queue<T>,
  kv: KVNamespace,
): Promise<Response> {
  const decision = await checkBackpressure(queueName, priority, kv);

  if (decision === 'shed') {
    return new Response(
      JSON.stringify({ error: 'server_busy', retryAfter: 60 }),
      {
        status: 429,
        headers: {
          'Content-Type': 'application/json',
          'Retry-After': '60',
          'X-Backpressure': 'shed',
        },
      },
    );
  }

  if (decision === 'delay') {
    // Enqueue with a delay to spread load
    await queue.send(payload, { contentType: 'json', delaySeconds: 30 });
    return new Response(JSON.stringify({ status: 'queued', delayed: true }), {
      status: 202,
      headers: { 'Content-Type': 'application/json', 'X-Backpressure': 'delay' },
    });
  }

  await queue.send(payload, { contentType: 'json' });
  return new Response(JSON.stringify({ status: 'queued' }), {
    status: 202,
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## Durable Object Precision Counter (High-Accuracy Signalling)

```typescript
// do/load-signal.ts — Durable Object for precise atomic load tracking
export class LoadSignal implements DurableObject {
  private state: DurableObjectState;
  private concurrency = 0;
  private readonly maxConcurrency = 50;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/acquire') {
      return this.state.blockConcurrencyWhile(async () => {
        const current = (await this.state.storage.get<number>('concurrency')) ?? 0;
        if (current >= this.maxConcurrency) {
          return new Response(JSON.stringify({ granted: false, concurrency: current }), {
            status: 429,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        await this.state.storage.put('concurrency', current + 1);
        return new Response(JSON.stringify({ granted: true, concurrency: current + 1 }), {
          headers: { 'Content-Type': 'application/json' },
        });
      });
    }

    if (url.pathname === '/release') {
      return this.state.blockConcurrencyWhile(async () => {
        const current = (await this.state.storage.get<number>('concurrency')) ?? 0;
        const next = Math.max(0, current - 1);
        await this.state.storage.put('concurrency', next);
        return new Response(JSON.stringify({ concurrency: next }), {
          headers: { 'Content-Type': 'application/json' },
        });
      });
    }

    if (url.pathname === '/status') {
      const concurrency = (await this.state.storage.get<number>('concurrency')) ?? 0;
      return new Response(
        JSON.stringify({
          concurrency,
          maxConcurrency: this.maxConcurrency,
          saturated: concurrency >= this.maxConcurrency,
        }),
        { headers: { 'Content-Type': 'application/json' } },
      );
    }

    return new Response('Not Found', { status: 404 });
  }
}
```

## Adaptive Retry Delay in Consumers

```typescript
// consumer/adaptive-retry.ts
// Increase retry delay when the batch failure rate is high
// to give downstream systems time to recover.

function adaptiveDelay(failureRate: number): number {
  // Exponential back-off based on failure rate: 0% → 5s, 50% → 60s, 100% → 300s
  const base = 5;
  const max = 300;
  const delay = Math.min(max, base * Math.pow(2, failureRate * 5));
  // Add jitter (±20%) to avoid thundering herd
  return Math.round(delay * (0.8 + Math.random() * 0.4));
}

export async function retryWithAdaptiveDelay(
  msg: Message,
  failureRate: number,
): Promise<void> {
  const delaySeconds = adaptiveDelay(failureRate);
  msg.retry({ delaySeconds });
  console.log({ event: 'adaptive_retry', delaySeconds, failureRate });
}
```

## Circuit Integration: Wiring Gateway + Consumer

```typescript
// worker.ts — full wiring example
import { gatewayEnqueue } from './producer/backpressure-gate';

export interface Env {
  JOB_QUEUE: Queue<{ jobId: string; payload: unknown }>;
  BACKPRESSURE_KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const body = await request.json<{ priority?: string; data: unknown }>();
    const priority = body.priority === 'high' ? 'high' : 'low';

    return gatewayEnqueue(
      { jobId: crypto.randomUUID(), payload: body.data },
      priority,
      'job-queue',
      env.JOB_QUEUE,
      env.BACKPRESSURE_KV,
    );
  },

  async queue(batch: MessageBatch, env: Env): Promise<void> {
    const { processBatchWithHealthTracking } = await import('./consumer/health-beacon');
    await processBatchWithHealthTracking(batch, env.BACKPRESSURE_KV, async (msg) => {
      const job = msg.body as { jobId: string; payload: unknown };
      // domain processing ...
      console.log({ event: 'job_processed', jobId: job.jobId });
    });
  },
};
```

## Anti-patterns

- **Failing closed on missing health signal** — if the KV health key expires and the
  producer rejects all traffic, the system self-DDoses on recovery. Fail open (assume
  healthy) and rely on the circuit breaker pattern for hard failures.
- **Shedding high-priority work first** — always prioritise by value: shed
  background/analytics jobs before user-facing transactions.
- **Using Wall clock sleep (`setTimeout`) in the producer** — Workers should not sleep;
  use Queue `delaySeconds` instead to reschedule work without blocking CPU.
- **Setting `expirationTtl` too short on health signals** — if the consumer batch takes
  longer than the TTL to complete, the signal expires before the next producer check.
  Set TTL to at least 2–3× the expected consumer batch duration.
- **Not exposing backpressure state in observability** — the `X-Backpressure` header
  and structured logs are your only window into whether shedding is actually firing.

## Gotchas

- KV reads are eventually consistent. A producer may read a stale `ok` signal for up
  to ~60 seconds after a consumer writes `overloaded`. For tighter coupling, use a
  Durable Object (see `LoadSignal` above).
- `queue.send()` with `delaySeconds` requires Queues with delay support enabled in
  `wrangler.toml` (`[[queues.consumers]]` `max_retries`, `dead_letter_queue`).
- `batch.messages.length` is bounded by `max_batch_size` in your consumer config;
  a very small batch may give a misleading low failure rate. Smooth the metric with a
  rolling window stored in the Durable Object or KV.
- Returning `429` from the gateway does not automatically retry at the client.
  Document the `Retry-After` header contract with API consumers.

## Verification

```bash
# Trigger overload by seeding a degraded health signal manually
wrangler kv:key put --namespace-id=<ID> "backpressure:job-queue" \
  '{"status":"overloaded","p99LatencyMs":9000,"failureRate":0.3,"reportedAt":"2026-08-23T00:00:00Z"}'

# Send low-priority request — expect 429
curl -s -o /dev/null -w "%{http_code}" \
  -X POST https://api.example.com/jobs \
  -H "Content-Type: application/json" \
  -d '{"priority":"low","data":{"task":"ingest"}}'
# Expected: 429

# Send high-priority request — expect 202 (not yet overloaded for high priority)
curl -s -o /dev/null -w "%{http_code}" \
  -X POST https://api.example.com/jobs \
  -H "Content-Type: application/json" \
  -d '{"priority":"high","data":{"task":"payment"}}'
# Expected: 202
```

## Related

- `circuit-breaker-workers-d1-fetch.md`
- `token-bucket-durable-objects.md`
- `exponential-backoff-jitter-workers.md`
- `competing-consumers-workers-queues.md`
- `dead-letter-queue-pattern.md`
- `bulkhead-pattern-workers-subrequests.md`

## Sources

- Release It! — Michael Nygard (Backpressure, Load Shedding chapters)
- Cloudflare Queues — https://developers.cloudflare.com/queues/
- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Google SRE Book — https://sre.google/sre-book/handling-overload/
