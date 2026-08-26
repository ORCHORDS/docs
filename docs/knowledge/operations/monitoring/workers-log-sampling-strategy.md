# Log Sampling Strategies for High-Traffic Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

At 50 k req/s your Worker emits ~4.3 billion log lines per day. Analytics Engine pricing is per write (each `writeDataPoint` call has a cost), `console.log` output adds CPU time, and Tail Workers downstream struggle to process everything in real-time. You need a principled sampling strategy that captures 100 % of errors, representative samples of successful requests, and adapts automatically when traffic spikes — all without any external coordination service.

## Context

Three complementary sampling strategies:

| Strategy | When to use | Trade-off |
|---|---|---|
| **Head-based** | Uniform baseline coverage | May miss rare slow requests |
| **Tail-based** | Error / slow request capture | Requires buffering |
| **Deterministic** | Consistent trace stitching | Hash cost per request |

Adaptive sampling adds a fourth layer: when the KV-stored rate is lowered by an operator (or automatically under load), the Worker reads it once per 30-second window and adjusts in-memory.

Stack:
- **KV** — live sampling rate config (`sampling:rate:api`, updated by ops or auto-scaler)
- **Analytics Engine** — structured log sink (replaces `console.log` for dashboards)
- **Tail Worker** — secondary sampling pass on Worker logs

## Solution

```typescript
// log-sampling.ts
import type { KVNamespace, AnalyticsEngineDataset } from '@cloudflare/workers-types';

export interface Env {
  LOG_KV: KVNamespace;
  AE: AnalyticsEngineDataset;
  DEFAULT_SAMPLE_RATE: string;   // 0–1, default "0.1" (10 %)
  TAIL_SAMPLE_ON_ERROR: string;  // default "true"
  SLOW_THRESHOLD_MS: string;     // default "1000"
}

// ── rate cache ────────────────────────────────────────────────────────────────
// Refreshed from KV at most once every 30 seconds per isolate instance.

let cachedRate: number | null = null;
let cachedRateAt = 0;
const RATE_TTL_MS = 30_000;

async function getSampleRate(kv: KVNamespace, workerName: string, defaultRate: number): Promise<number> {
  const now = Date.now();
  if (cachedRate !== null && now - cachedRateAt < RATE_TTL_MS) return cachedRate;

  const raw = await kv.get(`sampling:rate:${workerName}`);
  const rate = raw !== null ? parseFloat(raw) : defaultRate;
  cachedRate = Math.max(0, Math.min(1, rate));
  cachedRateAt = now;
  return cachedRate;
}

// ── head-based sampling ───────────────────────────────────────────────────────
// Decision made at the start of the request from a Math.random() coin flip.
// Fast — no hashing, no I/O.

function headSample(rate: number): boolean {
  return Math.random() < rate;
}

// ── deterministic sampling ────────────────────────────────────────────────────
// Hash a stable identifier (request ID, user ID) so that the same entity is
// either always sampled or always dropped within a rolling window.
// Useful for distributed trace stitching across Service Bindings.

async function deterministicSample(id: string, rate: number): Promise<boolean> {
  const encoder = new TextEncoder();
  const data = encoder.encode(id);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const view = new DataView(hashBuffer);
  // Take the first 4 bytes as a uint32 and normalise to [0, 1).
  const norm = view.getUint32(0, false) / 0xffffffff;
  return norm < rate;
}

// ── tail-based sampling ───────────────────────────────────────────────────────
// Samples are buffered in-memory; the sampling decision is deferred until the
// response is complete so errors and slow paths are always included.

interface LogEntry {
  level: 'info' | 'warn' | 'error';
  message: string;
  durationMs?: number;

}

class TailSampler {
  private buffer: LogEntry[] = [];
  private sampled = false;
  private readonly threshold: number;
  private readonly sampleOnError: boolean;

  constructor(threshold: number, sampleOnError: boolean) {
    this.threshold = threshold;
    this.sampleOnError = sampleOnError;
  }

  log(entry: LogEntry): void {
    this.buffer.push(entry);
    // Eagerly promote if we see an error or a warning.
    if (this.sampleOnError && (entry.level === 'error' || entry.level === 'warn')) {
      this.sampled = true;
    }
  }

  flush(
    durationMs: number,
    headSampled: boolean,
    ae: AnalyticsEngineDataset
  ): void {
    // Tail decision: include slow requests regardless of head decision.
    if (durationMs > this.threshold) this.sampled = true;
    if (!this.sampled && !headSampled) return;

    for (const entry of this.buffer) {
      ae.writeDataPoint({
        blobs: [entry.level, entry.message, JSON.stringify(entry)],
        doubles: [durationMs],
        indexes: ['log'],
      });
    }
  }
}

// ── adaptive sampling under load ──────────────────────────────────────────────
// Operators or an auto-scaler write a new rate to KV when CPU headroom shrinks.
// This function is exposed as an API route for the auto-scaler sidecar.

async function updateSampleRate(
  kv: KVNamespace,
  workerName: string,
  newRate: number
): Promise<void> {
  const clamped = Math.max(0.001, Math.min(1, newRate));
  await kv.put(`sampling:rate:${workerName}`, String(clamped), {
    expirationTtl: 86400, // auto-expire daily so stale overrides don't persist
  });
  // Bust the in-process cache so the next request picks up the new rate.
  cachedRate = null;
}

// ── Analytics Engine cost measurement ────────────────────────────────────────
// Track writes-per-minute so you can correlate AE cost against the sample rate.

let aeWriteCount = 0;
let aeWindowStart = Date.now();

function trackAeWrite(ae: AnalyticsEngineDataset): void {
  aeWriteCount++;
  const now = Date.now();
  if (now - aeWindowStart > 60_000) {
    // Emit a meta-metric: AE writes in the last minute.
    ae.writeDataPoint({
      blobs: ['meta', 'ae_write_rate'],
      doubles: [aeWriteCount],
      indexes: ['sampling_meta'],
    });
    aeWriteCount = 0;
    aeWindowStart = now;
  }
}

// ── Tail Worker handler ───────────────────────────────────────────────────────
// Deployed separately as a tail consumer. Applies a second-pass sample to the
// already-sampled events delivered by the runtime.

export const tailHandler = {
  async tail(
    events: TraceItem[],
    env: Env,
    _ctx: ExecutionContext
  ): Promise<void> {
    const rate = await getSampleRate(env.LOG_KV, 'tail', parseFloat(env.DEFAULT_SAMPLE_RATE ?? '0.1'));

    for (const event of events) {
      // Always forward events that contain exceptions.
      const hasError = event.exceptions.length > 0;
      if (!hasError && !headSample(rate)) continue;

      for (const log of event.logs) {
        env.AE.writeDataPoint({
          blobs: [log.level, log.message.join(' ')],
          doubles: [event.cpuTime ?? 0],
          indexes: ['tail_log'],
        });
      }
    }
  },
};

// ── main fetch handler ────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    const workerName = 'api';
    const defaultRate = parseFloat(env.DEFAULT_SAMPLE_RATE ?? '0.1');
    const slowThresholdMs = parseInt(env.SLOW_THRESHOLD_MS ?? '1000', 10);
    const sampleOnError = env.TAIL_SAMPLE_ON_ERROR !== 'false';

    // Admin: update sample rate.
    const url = new URL(request.url);
    if (url.pathname === '/__sampling/rate' && request.method === 'POST') {
      const { rate } = await request.json<{ rate: number }>();
      await updateSampleRate(env.LOG_KV, workerName, rate);
      return Response.json({ ok: true, rate });
    }

    // Determine head sample decision (once per request, cheap).
    const rate = await getSampleRate(env.LOG_KV, workerName, defaultRate);
    const sampled = headSample(rate);

    // For tracing, use deterministic sampling keyed by trace-id header.
    const traceId = request.headers.get('x-trace-id') ?? crypto.randomUUID();
    const traceSampled = await deterministicSample(traceId, rate);

    const tail = new TailSampler(slowThresholdMs, sampleOnError);
    tail.log({ level: 'info', message: `${request.method} ${url.pathname}`, traceId, sampled: traceSampled });

    let response: Response;
    try {
      // Simulate your actual request handling here.
      response = new Response('OK', { status: 200 });
    } catch (err) {
      tail.log({ level: 'error', message: String(err), traceId });
      response = new Response('Internal Server Error', { status: 500 });
    }

    const durationMs = Date.now() - start;
    tail.log({ level: 'info', message: 'request complete', durationMs, status: response.status });

    ctx.waitUntil(
      Promise.resolve().then(() => {
        tail.flush(durationMs, sampled || traceSampled, env.AE);
        trackAeWrite(env.AE);
      })
    );

    return response;
  },
};
```

## Implementation Details

**Module-level KV cache** — `cachedRate` and `cachedRateAt` are module-level variables. Within a single isolate instance they persist across requests for 30 seconds, eliminating a KV read on every hot request. When the isolate is recycled (new deploy, cold start), the first request re-reads from KV.

**Deterministic vs head-based** — head-based sampling with `Math.random()` is stateless and O(1) but produces different decisions for the same entity on different Workers. Deterministic sampling with SHA-256 ensures that a given `x-trace-id` is consistently sampled or dropped across all Worker instances, which is necessary for reconstructing complete distributed traces.

**TailSampler buffer** — logs accumulate in an in-process array and are flushed after the response is sent (via `ctx.waitUntil`). This means the CPU cost of Analytics Engine writes does not add to TTFB. The buffer promotes to "sampled" as soon as it sees an error log, guaranteeing 100 % error capture.

**AE write cost measurement** — `trackAeWrite` emits a meta-datapoint once per minute showing AE write throughput. Plot this in AE SQL against your `sampling:rate` KV value to empirically measure the cost/coverage trade-off and tune your target rate.

## Anti-patterns

- **Logging in the hot path before awaiting the response**: `console.log` synchronously formats strings and adds to CPU time. Defer all Analytics Engine writes to `ctx.waitUntil` so they never block the response.
- **Setting the sample rate to 0**: this silences all logs, including errors. Always floor the rate at `0.001` (0.1 %) so error-triggered tail promotion can still fire.
- **Re-reading KV on every request**: at 50 k req/s a raw KV read per request would consume your KV read quota in minutes. The 30-second module-level cache amortises the cost to ~2 reads/minute per isolate.
- **Head-only sampling for tracing**: two Worker instances independently coin-flipping for the same trace ID produce partial traces. Use deterministic sampling for any data that needs to be joined across Workers.

## Gotchas

- **Module-level state is per-isolate, not per-Worker**: at high traffic Workers runs many isolates simultaneously. Each isolate has its own `cachedRate`. The KV value is the source of truth; the cache is just a local optimisation.
- **`crypto.subtle.digest` is async**: deterministic sampling adds one microtask. Avoid it on paths where sub-millisecond latency matters — use head sampling there instead.
- **Tail Worker delivery is best-effort**: the runtime may not deliver all events to a Tail Worker under extreme load. Do not rely on it as your sole error capture mechanism.

## Verification

```bash
# Set sample rate to 50 % for testing.
curl -X POST https://api.example.com/__sampling/rate \
  -H 'Content-Type: application/json' -d '{"rate": 0.5}'

# Confirm KV value.
npx wrangler kv key get --namespace-id=<ID> "sampling:rate:api"

# Query AE for log volume over last hour.
curl -s "https://api.cloudflare.com/client/v4/accounts/<ACCT>/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_TOKEN" \
  --data "SELECT blob1 as level, COUNT(*) FROM <DATASET> WHERE index1='log' AND timestamp > NOW() - INTERVAL '1' HOUR GROUP BY blob1"

# Check AE write rate meta-metric.
  --data "SELECT double1 as writes_per_min FROM <DATASET> WHERE index1='sampling_meta' ORDER BY timestamp DESC LIMIT 5"
```

## Related

- `documentation/docs/policies/monitoring/workers-distributed-tracing-otel.md` — trace propagation
- `documentation/docs/policies/monitoring/workers-anomaly-detection-zscore.md` — anomaly detection
- `documentation/docs/policies/monitoring/cost-per-request-tracking.md` — cost tracking

## Sources

- Cloudflare Tail Workers — https://developers.cloudflare.com/workers/observability/tail-workers/
- Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- OpenTelemetry Sampling Specification — https://opentelemetry.io/docs/concepts/sampling/
- Google Dapper paper — Sigelman et al., 2010
