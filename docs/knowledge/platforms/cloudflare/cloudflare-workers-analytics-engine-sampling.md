# Adaptive Sampling for Workers Analytics Engine

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
High-traffic Workers write far more data points to Analytics Engine than is cost-effective or query-useful; you need to reduce write volume while preserving statistical accuracy for rare events and tail latencies.

## Context
Cloudflare Analytics Engine charges per data point written and enforces a write throughput limit per Worker invocation. For endpoints serving millions of requests per day, naive 1:1 logging floods the dataset, inflates costs, and buries signal in noise. Adaptive sampling reduces write volume by dynamically adjusting the sample rate based on observed traffic volume — using either Workers KV for cross-invocation counters (eventual consistency is fine here) or a fixed head-sampling coin-flip for stateless scenarios. The `writeDataPoint` call is fire-and-forget and does not add latency to the request path.

## Architecture: Head Sampling (Stateless)

The simplest approach — decide at the start of each request whether to sample it:
```typescript
// src/sampling.ts
export function shouldSample(rate: number): boolean {
  // rate = 0.1 means sample 10% of requests
  return Math.random() < rate;
}

// src/index.ts
interface Env {
  AE: AnalyticsEngineDataset;
}

const SAMPLE_RATE = 0.05; // 5% — tune per endpoint traffic volume

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const start = Date.now();
    const url = new URL(request.url);

    const response = await handleRequest(request);

    if (shouldSample(SAMPLE_RATE)) {
      env.AE.writeDataPoint({
        blobs: [url.pathname, request.method, String(response.status)],
        doubles: [Date.now() - start],
        indexes: [url.pathname],
      });
    }

    return response;
  },
};

async function handleRequest(req: Request): Promise<Response> {
  return new Response("ok");
}
```

## Architecture: Rate-Based Adaptive Sampling with KV

Adjust sample rate dynamically based on recent request volume stored in KV:
```typescript
// src/adaptive-sampler.ts
interface Env {
  SAMPLE_COUNTERS: KVNamespace;
  AE: AnalyticsEngineDataset;
}

// Target: write at most MAX_WRITES_PER_MINUTE to AE per route
const MAX_WRITES_PER_MINUTE = 100;
const COUNTER_TTL_SECONDS = 60;

function bucketKey(pathname: string): string {
  const minute = Math.floor(Date.now() / 60_000);
  return `sample-count:${pathname}:${minute}`;
}

async function adaptiveSampleRate(
  env: Env,
  pathname: string
): Promise<number> {
  const key = bucketKey(pathname);
  const raw = await env.SAMPLE_COUNTERS.get(key);
  const currentCount = raw ? parseInt(raw, 10) : 0;

  if (currentCount >= MAX_WRITES_PER_MINUTE * 10) {
    // Observed very high traffic — sample 1%
    return 0.01;
  } else if (currentCount >= MAX_WRITES_PER_MINUTE * 2) {
    // Moderate elevated traffic — sample 10%
    return 0.1;
  }
  // Normal traffic — sample 50%
  return 0.5;
}

async function incrementCounter(env: Env, pathname: string): Promise<void> {
  const key = bucketKey(pathname);
  const raw = await env.SAMPLE_COUNTERS.get(key);
  const next = raw ? parseInt(raw, 10) + 1 : 1;
  // Fire-and-forget; don't await in the critical path
  env.SAMPLE_COUNTERS.put(key, String(next), {
    expirationTtl: COUNTER_TTL_SECONDS,
  });
}

export { adaptiveSampleRate, incrementCounter };
```

```typescript
// src/index.ts (adaptive version)
import { adaptiveSampleRate, incrementCounter } from "./adaptive-sampler";

interface Env {
  SAMPLE_COUNTERS: KVNamespace;
  AE: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    const url = new URL(request.url);
    const pathname = url.pathname;

    const [response, sampleRate] = await Promise.all([
      handleRequest(request),
      adaptiveSampleRate(env, pathname),
    ]);

    const latencyMs = Date.now() - start;
    const sampled = Math.random() < sampleRate;

    if (sampled) {
      // Write the sample; include the inverse rate so aggregations can be unbiased
      env.AE.writeDataPoint({
        blobs: [pathname, request.method, String(response.status)],
        doubles: [latencyMs, 1 / sampleRate], // weight for unbiased mean
        indexes: [pathname],
      });
      // Increment counter off the critical path
      ctx.waitUntil(incrementCounter(env, pathname));
    }

    return response;
  },
};

async function handleRequest(_req: Request): Promise<Response> {
  return new Response("ok");
}
```

## Always-Sample Slow Requests

Regardless of sample rate, always record outlier latencies (tail-latency preservation):
```typescript
const SLOW_THRESHOLD_MS = 500;

function shouldWrite(sampled: boolean, latencyMs: number): boolean {
  return sampled || latencyMs >= SLOW_THRESHOLD_MS;
}

// In the fetch handler:
const latencyMs = Date.now() - start;
const sampled = Math.random() < sampleRate;

if (shouldWrite(sampled, latencyMs)) {
  const isForcedSample = !sampled; // latency-triggered, not rate-sampled
  env.AE.writeDataPoint({
    blobs: [pathname, request.method, String(response.status), isForcedSample ? "forced" : "sampled"],
    doubles: [latencyMs, isForcedSample ? 1.0 : 1 / sampleRate],
    indexes: [pathname],
  });
}
```

## Querying with Sample Weight Correction

SQL API query that corrects for variable sample rates using the stored weight:
```sql
-- Unbiased p95 latency estimate from sampled data
-- blob1 = pathname, double1 = latency_ms, double2 = sample_weight
SELECT
  blob1 AS pathname,
  COUNT() AS raw_samples,
  SUM(double2) AS estimated_total_requests,
  quantileWeighted(0.95)(double1, double2) AS p95_latency_ms
FROM ae_dataset
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY pathname
ORDER BY estimated_total_requests DESC
LIMIT 50;
```

## Anti-patterns
- **Sampling error responses at a lower rate than success responses** — errors are rare and critical; always sample 4xx/5xx at 100%.
- **Using a global sample rate across all routes** — high-traffic API endpoints need lower rates than low-traffic admin routes; make rate per-route or per-endpoint.
- **KV round-trips on every request for counter reads** — use `ctx.waitUntil` for writes; batch reads or cache the rate in-memory per isolate lifecycle using a module-scope variable.
- **Forgetting to store the weight** — without `1/sampleRate` stored per point, aggregated counts and means will be systematically biased.
- **Trusting sample counts as absolute counts** — always label sampled metrics as estimates in dashboards.

## Gotchas
- KV writes in `waitUntil` are eventually consistent — two concurrent invocations can both read `0` and both write `1`. The counter is for order-of-magnitude traffic estimation, not exact counting; this is acceptable.
- `writeDataPoint` is silently dropped if the Worker exceeds the dataset's per-invocation write limit (default: 25 data points). Structure writes so the most important events happen first.
- Analytics Engine `doubles` array is limited to 20 elements; don't over-engineer the schema.
- The `indexes` field (max 1 element, max 32 bytes) is critical for query performance — always set it to the primary dimension you filter on.
- Module-scope caching of `sampleRate` survives for the isolate's lifetime but resets on cold start; warm isolates may briefly use a stale rate until the next KV read.

## Verification
```bash
# Check recent write volume via the SQL API
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d "SELECT COUNT() as writes, SUM(double2) as est_total FROM ae_dataset WHERE timestamp > NOW() - INTERVAL '5' MINUTE"

# Confirm sample weight column is populated (non-null)
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d "SELECT min(double2), max(double2) FROM ae_dataset LIMIT 1"
```

## Related
- [cloudflare-workers-analytics-engine-custom-metrics.md](cloudflare-workers-analytics-engine-custom-metrics.md)
- [workers-analytics-engine.md](workers-analytics-engine.md)
- [workers-analytics-engine-sql-api-querying.md](workers-analytics-engine-sql-api-querying.md)
- [kv-best-practices.md](kv-best-practices.md)
- [workers-waituntil-shared-post-response-budget.md](workers-waituntil-shared-post-response-budget.md)

## Sources
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
