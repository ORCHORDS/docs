# Tail Worker Structured Log Sampling Strategies

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project Workers emit thousands of log events per second during peak hours, but forwarding every event to Analytics Engine or Logpush R2 burns through write quotas and inflates storage costs. Naive head-based sampling drops interesting error events while retaining noisy health-check pings. A structured, multi-tier sampling strategy lets you capture 100% of errors, a statistical sample of normal traffic, and zero health-check noise.

## Context

Cloudflare Tail Workers receive a `TailEvent` containing one or more `TraceItem` objects for each completed Worker invocation. Each item carries the outcome (`ok`, `exception`, `canceled`, `exceededCpu`, `exceededMemory`), timing, logs emitted via `console.log`, and any unhandled exceptions. Tail Workers run in the same Cloudflare network, so they add no cross-region latency but are subject to their own CPU and subrequest limits. Analytics Engine accepts up to 25 `writeDataPoint` calls per request and 1,000 data points per second per account.

## Section 1 — Sampling Decision Tree

Route each `TraceItem` through a priority funnel before writing to any sink. Errors always pass; then apply deterministic hash-based sampling so the same request ID always lands in the same bucket (enabling trace reconstruction); finally apply a global rate gate to cap throughput.

```typescript
// tail-worker/sampling.ts
export type SamplingDecision = "keep-error" | "keep-sampled" | "drop";

export interface SamplingConfig {
  errorSampleRate: number;   // 1.0 = 100 % of errors
  normalSampleRate: number;  // e.g. 0.05 = 5 % of ok requests
  healthCheckPatterns: RegExp[];
}

const DEFAULT_CONFIG: SamplingConfig = {
  errorSampleRate: 1.0,
  normalSampleRate: 0.05,
  healthCheckPatterns: [/\/health/, /\/ping/, /\/__cf_\w+/],
};

function deterministicHash(value: string): number {
  // djb2 — fast, no crypto cost
  let h = 5381;
  for (let i = 0; i < value.length; i++) {
    h = (h * 33) ^ value.charCodeAt(i);
  }
  return (h >>> 0) / 0xffffffff; // 0..1
}

export function decideSample(
  item: TraceItem,
  config: SamplingConfig = DEFAULT_CONFIG
): SamplingDecision {
  const url = item.event && "request" in item.event
    ? (item.event as { request: { url: string } }).request.url
    : "";

  // Health-check suppression — check before anything else
  if (config.healthCheckPatterns.some((re) => re.test(url))) return "drop";

  // Always capture non-ok outcomes
  if (item.outcome !== "ok") return "keep-error";

  // Deterministic fraction using request URL (or fallback to walltime)
  const seed = url || String(item.wallTime);
  const bucket = deterministicHash(seed);
  if (bucket < config.normalSampleRate) return "keep-sampled";

  return "drop";
}
```

## Section 2 — Structured Envelope Construction

Attach a `sample_rate` field to every forwarded log so downstream consumers can apply inverse-probability weighting when computing aggregate rates. Without this annotation, a 5 % sample will under-report throughput by 20×.

```typescript
// tail-worker/envelope.ts
import { decideSample, SamplingDecision } from "./sampling";

export interface StructuredLogEnvelope {
  schemaVersion: "1";
  traceId: string;
  outcome: string;
  sampleRate: number;
  sampleReason: SamplingDecision;
  cpuMs: number;
  wallMs: number;
  exceptions: string[];
  logs: string[];
  url: string;
  method: string;
  statusCode: number;
  env: string;
  colo: string;
}

export function buildEnvelope(
  item: TraceItem,
  decision: SamplingDecision,
  sampleRate: number,
  env: string,
  colo: string
): StructuredLogEnvelope {
  const req = item.event && "request" in item.event
    ? (item.event as any).request
    : null;
  const resp = item.event && "response" in item.event
    ? (item.event as any).response
    : null;

  return {
    schemaVersion: "1",
    traceId: item.eventTimestamp?.toString(16) ?? crypto.randomUUID(),
    outcome: item.outcome,
    sampleRate,
    sampleReason: decision,
    cpuMs: item.cpuTime ?? 0,
    wallMs: item.wallTime ?? 0,
    exceptions: item.exceptions?.map((e) => `${e.name}: ${e.message}`) ?? [],
    logs: item.logs?.map((l) => l.message?.join(" ") ?? "") ?? [],
    url: req?.url ?? "",
    method: req?.method ?? "",
    statusCode: resp?.status ?? 0,
    env,
    colo,
  };
}
```

## Section 3 — Tail Worker Entry Point and Analytics Engine Write

```typescript
// tail-worker/index.ts
import { decideSample } from "./sampling";
import { buildEnvelope } from "./envelope";

interface Env {
  ANALYTICS_ENGINE: AnalyticsEngineDataset;
  ENVIRONMENT: string;
}

export default {
  async tail(events: TraceItem[], env: Env, ctx: ExecutionContext): Promise<void> {
    const colo = (globalThis as any).__CF?.colo ?? "unknown";
    const normalRate = 0.05;

    for (const item of events) {
      const decision = decideSample(item, {
        errorSampleRate: 1.0,
        normalSampleRate: normalRate,
        healthCheckPatterns: [/\/health/, /\/ping/],
      });

      if (decision === "drop") continue;

      const sampleRate = decision === "keep-error" ? 1.0 : normalRate;
      const envelope = buildEnvelope(item, decision, sampleRate, env.ENVIRONMENT, colo);

      // Write to Analytics Engine — one data point per sampled event
      env.ANALYTICS_ENGINE.writeDataPoint({
        blobs: [
          envelope.url,
          envelope.method,
          envelope.outcome,
          envelope.sampleReason,
          envelope.colo,
          envelope.env,
          envelope.exceptions.join("|").slice(0, 1024),
        ],
        doubles: [
          envelope.statusCode,
          envelope.cpuMs,
          envelope.wallMs,
          envelope.sampleRate,
        ],
        indexes: [envelope.traceId.slice(0, 32)],
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

## Section 4 — Querying with Inverse-Probability Weighting

Because sampled events carry `sampleRate`, divide counts by it to reconstruct true totals. Analytics Engine SQL API supports weighted aggregations via division.

```sql
-- Estimated true request count over the last hour
SELECT
  outcome,
  SUM(1.0 / double4) AS estimated_requests,
  AVG(double2)        AS avg_cpu_ms,
  COUNT(*)            AS sampled_count
FROM analytics_engine_dataset
WHERE
  timestamp > NOW() - INTERVAL '1' HOUR
  AND blob3 NOT IN ('keep-error')   -- separate error view
GROUP BY 1
ORDER BY 2 DESC;

-- Error rate (errors are 100 % sampled so no weighting needed)
SELECT
  blob1 AS url_prefix,
  COUNT(*) AS error_count,
  DATE_TRUNC('minute', timestamp) AS bucket
FROM analytics_engine_dataset
WHERE
  timestamp > NOW() - INTERVAL '1' HOUR
  AND blob3 = 'keep-error'
  AND double1 >= 500
GROUP BY 1, 3
ORDER BY 3 DESC, 2 DESC;
```

## Anti-patterns

- Emitting raw `console.log` strings without structured fields — makes SQL queries impossible and blobs opaque.
- Sampling on wall-clock modulo without a stable key — the same request gets different decisions on retries, poisoning rate estimates.
- Writing one Analytics Engine data point per `console.log` line — blows through the 25-per-request write limit immediately.
- Dropping errors to save write quota — you lose the signal you most need; errors must always be kept.
- Forgetting `sampleRate` on the envelope — downstream SUM queries under-count traffic by 1/rate.

## Gotchas

- `TraceItem.cpuTime` is in milliseconds; compare against the 50 ms soft limit (30 ms for Unbound).
- Tail Workers cannot use KV, D1, or outbound fetch in the free tier — bind Analytics Engine directly.
- `TailEvent` can batch up to 50 `TraceItem` objects; loop over all of them, not just `events[0]`.
- Analytics Engine blobs are limited to 1 024 bytes; truncate exception messages before writing.
- The `indexes` field is the high-cardinality dimension (e.g. traceId); use only one per data point.

## Verification

1. Deploy the Tail Worker and bind `ANALYTICS_ENGINE` in `wrangler.toml` under `[tail_consumers]`.
2. Send synthetic traffic: 100 requests to `/health` (should all drop), 100 to `/api/feed` (expect ~5 written), 10 requests that throw (expect all 10 written).
3. Query Analytics Engine: `SELECT COUNT(*) FROM ae WHERE blob4 = 'drop'` — should return 0 (drops are never written).
4. Verify weighted estimate: `SUM(1.0/double4)` for `/api/feed` should converge to ~100 within ±40 % with 5 samples.
5. Confirm no `exceededCpu` outcomes on the Tail Worker itself in the Cloudflare dashboard.

## Related

- `/documentation/categories/monitoring/workers-tail-worker-sampling-high-traffic.md`
- `/documentation/categories/monitoring/cloudflare-analytics-engine.md`
- `/documentation/categories/monitoring/analytics-engine-write-limits-and-backpressure.md`
- `/documentation/categories/monitoring/tail-worker-exception-deduplication-fingerprinting-d1.md`
- `/documentation/categories/monitoring/log-sampling-strategies.md`

## Sources

- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/analytics-engine/
