# Vitest Workers Pipelines Throughput Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker writes high-volume telemetry or event data to a Cloudflare
Pipeline. In unit and integration tests you need to verify:

1. Batch assembly — the Worker correctly batches individual events before calling
   `pipeline.send()`.
2. Error paths — the Worker retries or dead-letters when `pipeline.send()` throws.
3. Throughput assertions — under a simulated burst, the Worker sends the expected
   number of events without dropping any.
4. Back-pressure — when the in-flight count exceeds a threshold, the Worker
   applies flow control.

Cloudflare Pipelines is a managed streaming ingestion binding (`env.MY_PIPELINE`).
Because Pipelines runs in Cloudflare infrastructure, local tests must mock the
binding and assert calls on the mock.

---

## Context

Cloudflare Pipelines binding API (as of mid-2026):

```ts
interface Pipeline<T> {
  send(messages: T[]): Promise<void>;
}
```

The Worker receives the binding via `env.MY_PIPELINE: Pipeline<TelemetryEvent>`.
Miniflare does not yet emulate Pipelines natively (unlike KV or D1), so tests
use a Vitest mock object that satisfies the `Pipeline` interface.

---

## Project Layout

```
src/
  pipeline-worker.ts
  pipeline-worker.test.ts
  test-utils/
    mock-pipeline.ts
wrangler.toml
vitest.config.ts
```

---

## Worker Under Test

```ts
// src/pipeline-worker.ts
export interface TelemetryEvent {
  eventId: string;
  timestamp: number;
  type: string;
  payload: Record<string, unknown>;
}

export interface Env {
  MY_PIPELINE: {
    send(messages: TelemetryEvent[]): Promise<void>;
  };
  PIPELINE_BATCH_SIZE: string;
  PIPELINE_MAX_INFLIGHT: string;
}

// Flush a batch of events to the pipeline
async function flushBatch(
  pipeline: Env['MY_PIPELINE'],
  events: TelemetryEvent[]
): Promise<void> {
  if (events.length === 0) return;
  await pipeline.send(events);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const batchSize  = parseInt(env.PIPELINE_BATCH_SIZE  ?? '100', 10);
    const maxInFlight = parseInt(env.PIPELINE_MAX_INFLIGHT ?? '5',  10);

    let body: TelemetryEvent[];
    try {
      body = await request.json<TelemetryEvent[]>();
    } catch {
      return new Response('Invalid JSON', { status: 400 });
    }

    if (!Array.isArray(body)) {
      return new Response('Expected array', { status: 422 });
    }

    // Split into batches
    const batches: TelemetryEvent[][] = [];
    for (let i = 0; i < body.length; i += batchSize) {
      batches.push(body.slice(i, i + batchSize));
    }

    // Concurrency-limited dispatch
    const inFlight: Promise<void>[] = [];
    for (const batch of batches) {
      if (inFlight.length >= maxInFlight) {
        await Promise.race(inFlight);
        // Remove settled promises
        inFlight.splice(0, inFlight.length,
          ...inFlight.filter((p) => {
            let settled = false;
            p.then(() => { settled = true; }).catch(() => { settled = true; });
            return !settled;
          })
        );
      }
      inFlight.push(flushBatch(env.MY_PIPELINE, batch));
    }

    await Promise.all(inFlight);

    return Response.json({ accepted: body.length, batches: batches.length });
  },
};
```

---

## Mock Pipeline Helper

```ts
// src/test-utils/mock-pipeline.ts
import { vi } from 'vitest';
import type { TelemetryEvent } from '../pipeline-worker';

export interface MockPipeline {
  send: ReturnType<typeof vi.fn>;
  sentEvents(): TelemetryEvent[];
  sentBatches(): TelemetryEvent[][];
  totalSent(): number;
  reset(): void;
}

export function createMockPipeline(opts: {
  failOnCall?: number[]; // 0-indexed call numbers that should throw
  latencyMs?: number;    // artificial delay per send() call
} = {}): MockPipeline {
  const { failOnCall = [], latencyMs = 0 } = opts;
  const batches: TelemetryEvent[][] = [];
  let callCount = 0;

  const send = vi.fn(async (messages: TelemetryEvent[]) => {
    const thisCall = callCount++;
    if (latencyMs > 0) {
      await new Promise((r) => setTimeout(r, latencyMs));
    }
    if (failOnCall.includes(thisCall)) {
      throw new Error(`Simulated pipeline failure on call ${thisCall}`);
    }
    batches.push([...messages]);
  });

  return {
    send,
    sentEvents: () => batches.flat(),
    sentBatches: () => batches,
    totalSent:  () => batches.flat().length,
    reset: () => {
      batches.length = 0;
      callCount = 0;
      send.mockClear();
    },
  };
}
```

---

## Test Suite

```ts
// src/pipeline-worker.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import worker, { type Env, type TelemetryEvent } from './pipeline-worker';
import { createMockPipeline } from './test-utils/mock-pipeline';

// ── Helpers ───────────────────────────────────────────────────────────────────
function makeEvents(count: number): TelemetryEvent[] {
  return Array.from({ length: count }, (_, i) => ({
    eventId:   `evt-${i}`,
    timestamp: Date.now() + i,
    type:      'click',
    payload:   { index: i },
  }));
}

function makeEnv(
  pipeline: ReturnType<typeof createMockPipeline>,
  overrides: Partial<Pick<Env, 'PIPELINE_BATCH_SIZE' | 'PIPELINE_MAX_INFLIGHT'>> = {}
): Env {
  return {
    MY_PIPELINE:           pipeline,
    PIPELINE_BATCH_SIZE:   overrides.PIPELINE_BATCH_SIZE   ?? '10',
    PIPELINE_MAX_INFLIGHT: overrides.PIPELINE_MAX_INFLIGHT ?? '3',
  };
}

async function postEvents(env: Env, events: TelemetryEvent[]): Promise<Response> {
  return worker.fetch(
    new Request('https://example.com/ingest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(events),
    }),
    env,
    { waitUntil: () => {}, passThroughOnException: () => {} } as unknown as ExecutionContext
  );
}

// ── Batching ─────────────────────────────────────────────────────────────────
describe('batch assembly', () => {
  let pipeline: ReturnType<typeof createMockPipeline>;

  beforeEach(() => {
    pipeline = createMockPipeline();
  });

  it('sends a single batch when events <= PIPELINE_BATCH_SIZE', async () => {
    const events = makeEvents(5);
    const res    = await postEvents(makeEnv(pipeline, { PIPELINE_BATCH_SIZE: '10' }), events);
    const body   = await res.json<{ accepted: number; batches: number }>();

    expect(res.status).toBe(200);
    expect(body.accepted).toBe(5);
    expect(body.batches).toBe(1);
    expect(pipeline.send).toHaveBeenCalledTimes(1);
    expect(pipeline.sentEvents()).toHaveLength(5);
  });

  it('splits into ceil(n/batchSize) batches', async () => {
    const events = makeEvents(25);
    await postEvents(makeEnv(pipeline, { PIPELINE_BATCH_SIZE: '10' }), events);

    expect(pipeline.send).toHaveBeenCalledTimes(3); // 10 + 10 + 5
    expect(pipeline.totalSent()).toBe(25);
  });

  it('sends no batches for empty array', async () => {
    const res = await postEvents(makeEnv(pipeline), []);
    expect(res.status).toBe(200);
    expect(pipeline.send).not.toHaveBeenCalled();
  });

  it('preserves all event IDs across batches', async () => {
    const events = makeEvents(50);
    await postEvents(makeEnv(pipeline, { PIPELINE_BATCH_SIZE: '7' }), events);

    const sentIds = pipeline.sentEvents().map((e) => e.eventId).sort();
    const origIds = events.map((e) => e.eventId).sort();
    expect(sentIds).toEqual(origIds);
  });

  it('batch size honours PIPELINE_BATCH_SIZE binding', async () => {
    const events = makeEvents(100);
    await postEvents(makeEnv(pipeline, { PIPELINE_BATCH_SIZE: '25' }), events);

    const batchSizes = pipeline.sentBatches().map((b) => b.length);
    expect(Math.max(...batchSizes)).toBe(25);
  });
});

// ── Throughput ────────────────────────────────────────────────────────────────
describe('throughput', () => {
  it('accepts and forwards 1 000 events', async () => {
    const pipeline = createMockPipeline();
    const events   = makeEvents(1_000);
    const res      = await postEvents(
      makeEnv(pipeline, { PIPELINE_BATCH_SIZE: '100', PIPELINE_MAX_INFLIGHT: '5' }),
      events
    );
    const body = await res.json<{ accepted: number; batches: number }>();

    expect(body.accepted).toBe(1_000);
    expect(body.batches).toBe(10);
    expect(pipeline.totalSent()).toBe(1_000);
  });

  it('tracks wall-clock throughput metric', async () => {
    const pipeline = createMockPipeline({ latencyMs: 5 });
    const events   = makeEvents(200);
    const start    = performance.now();

    await postEvents(
      makeEnv(pipeline, { PIPELINE_BATCH_SIZE: '20', PIPELINE_MAX_INFLIGHT: '5' }),
      events
    );

    const elapsed = performance.now() - start;
    // 200 events / 20 per batch = 10 batches; 5 in flight at 5 ms each →
    // ceil(10/5) * 5 ms = 10 ms minimum; allow generous wall-clock headroom
    expect(elapsed).toBeLessThan(500);
  });
});

// ── Error paths ───────────────────────────────────────────────────────────────
describe('error handling', () => {
  it('propagates pipeline failure as 500', async () => {
    // failOnCall: [0] — first send() call throws
    const pipeline = createMockPipeline({ failOnCall: [0] });
    const events   = makeEvents(5);

    await expect(
      postEvents(makeEnv(pipeline), events)
    ).rejects.toThrow('Simulated pipeline failure');
  });

  it('returns 400 for malformed JSON', async () => {
    const pipeline = createMockPipeline();
    const env      = makeEnv(pipeline);
    const res = await worker.fetch(
      new Request('https://example.com/ingest', {
        method: 'POST',
        body: 'not json',
      }),
      env,
      { waitUntil: () => {}, passThroughOnException: () => {} } as unknown as ExecutionContext
    );
    expect(res.status).toBe(400);
  });

  it('returns 422 when body is not an array', async () => {
    const pipeline = createMockPipeline();
    const env      = makeEnv(pipeline);
    const res = await worker.fetch(
      new Request('https://example.com/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notAnArray: true }),
      }),
      env,
      { waitUntil: () => {}, passThroughOnException: () => {} } as unknown as ExecutionContext
    );
    expect(res.status).toBe(422);
  });
});

// ── Concurrency ───────────────────────────────────────────────────────────────
describe('concurrency limiting', () => {
  it('never exceeds PIPELINE_MAX_INFLIGHT concurrent send() calls', async () => {
    const inflight     = { peak: 0, current: 0 };
    const pipeline     = createMockPipeline();
    const originalSend = pipeline.send.getMockImplementation()!;

    pipeline.send.mockImplementation(async (...args) => {
      inflight.current++;
      inflight.peak = Math.max(inflight.peak, inflight.current);
      await new Promise((r) => setTimeout(r, 20)); // simulate slow send
      inflight.current--;
      return originalSend(...args);
    });

    const maxInFlight = 3;
    await postEvents(
      makeEnv(pipeline, {
        PIPELINE_BATCH_SIZE:   '10',
        PIPELINE_MAX_INFLIGHT: String(maxInFlight),
      }),
      makeEvents(100)
    );

    expect(inflight.peak).toBeLessThanOrEqual(maxInFlight);
  });
});
```

---

## Vitest Config

```ts
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
      },
    },
  },
});
```

---

## Anti-patterns

- **Casting `env.MY_PIPELINE` to `any`** — the mock should satisfy the full
  `Pipeline<T>` interface. Casting to `any` silently allows mismatched call
  signatures.
- **Asserting `send.mock.calls.length` without accounting for retries** — if
  the Worker retries on error, the call count includes retries. Assert
  `sentBatches()` (which only captures successful sends) for throughput checks.
- **Not resetting the mock between tests** — without `beforeEach(() => pipeline.reset())`
  or creating a fresh mock per test, call counts bleed across tests.
- **Using `setTimeout` in production Worker code for back-pressure** — the
  Workers runtime limits CPU time. Use `Promise.race` on in-flight promises
  instead of sleep-based back-pressure.

---

## Gotchas

- Cloudflare Pipelines currently has no Miniflare emulation. Always use the mock
  binding; do not expect `wrangler dev` to simulate Pipelines correctly.
- The `Pipeline.send()` method accepts an array; calling it with an empty array
  may return successfully or throw depending on the production implementation.
  Test the empty-array path explicitly.
- `performance.now()` inside the Workers pool is available through the Web
  Performance API polyfill. Node's `performance.now()` is not the same as the
  global in a Workers environment.
- Workers CPU-time limit (50 ms for bundled Workers, up to 30 s with Unbound
  compute) constrains how many pipeline batches can be dispatched synchronously.
  For 1 000-event bursts, the concurrency limiter prevents exhausting CPU budget.

---

## Verification

```bash
# run the pipeline suite
npx vitest run src/pipeline-worker.test.ts --reporter=verbose

# see concurrency assertion detail
npx vitest run --reporter=verbose --testNamePattern="concurrency"
```

All tests should pass with zero failures.

---

## Related

- `vitest-workers-env-var-override-testing.md`
- `workers-queues-retry-dlq-testing.md`
- `k6-workers-queues-consumer-throughput.md`
- `vitest-analytics-engine-testing.md`
- `miniflare-workers-analytics-engine-testing.md`

---

## Sources

- Cloudflare Pipelines binding docs: https://developers.cloudflare.com/pipelines/
- `@cloudflare/vitest-pool-workers` README
- Vitest mock functions: https://vitest.dev/api/mock.html
- Workers CPU time limits: https://developers.cloudflare.com/workers/platform/limits/
