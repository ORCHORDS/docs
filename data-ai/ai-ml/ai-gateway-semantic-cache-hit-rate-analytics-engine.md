# AI Gateway Semantic Cache Hit Rate Analytics Engine

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project enables AI Gateway's semantic cache for moderation inference, but the team has no visibility into whether it is actually working. Questions arise: what percentage of moderation calls are served from cache? Are similarity thresholds too tight, letting near-identical prompts miss the cache? How much money is the cache saving per day? The built-in AI Gateway analytics panel shows aggregate cache status but not time-series hit-rate trends correlated with threshold changes.

---

## Context

AI Gateway responds to each request with an `cf-aig-cache-status` header: `HIT`, `MISS`, or `BYPASS`. A log-drain Worker reads these headers from the gateway webhook events and writes data points to Cloudflare Analytics Engine — a time-series store optimized for high-cardinality metrics. Grafana or the Workers Analytics Engine SQL API then queries hit rates over rolling windows.

This pattern complements the cost-comparison D1 ledger: cache hits generate zero provider cost, so a rising hit rate appears as a falling spend line in the cost ledger. Both dashboards together confirm the semantic cache is functioning as intended.

Key constraints:
- Analytics Engine blobs have a maximum of 20 blob fields and 20 double fields.
- The drain Worker must be lightweight — one `writeDataPoint` call per gateway event, no D1 writes in the hot path.
- Threshold changes (from 0.85 to 0.90, for example) should be recorded as an annotation event so rate changes can be correlated to config changes.

---

## Analytics Engine Dataset Schema

```typescript
// src/lib/cache-analytics.ts
// Analytics Engine dataset name: example project_CACHE_METRICS
// Fields used:
//   blobs[0]  = provider    ('anthropic' | 'openai' | 'workers-ai')
//   blobs[1]  = model
//   blobs[2]  = task_type   ('moderation' | 'embedding' | 'classification')
//   blobs[3]  = cache_status ('HIT' | 'MISS' | 'BYPASS')
//   blobs[4]  = example project_env    ('prod' | 'staging')
//   doubles[0] = latency_ms
//   doubles[1] = cost_usd_micro  (0 for HIT, actual for MISS)
//   doubles[2] = similarity_score (0.0–1.0, from cf-aig-cache-score header, or 0 if absent)

export function writeCacheDataPoint(
  engine: AnalyticsEngineDataset,
  opts: {
    provider:       string;
    model:          string;
    taskType:       string;
    cacheStatus:    string;
    env:            string;
    latencyMs:      number;
    costUsdMicro:   number;
    similarityScore: number;
  }
): void {
  engine.writeDataPoint({
    blobs:   [opts.provider, opts.model, opts.taskType, opts.cacheStatus, opts.env],
    doubles: [opts.latencyMs, opts.costUsdMicro, opts.similarityScore],
    indexes: [opts.cacheStatus], // index on cache_status for fast HIT/MISS splits
  });
}
```

---

## Log-Drain Worker Integration

```typescript
// src/workers/cache-metrics-drain.ts
import { writeCacheDataPoint } from '../lib/cache-analytics';

export interface Env {
  example project_CACHE_METRICS: AnalyticsEngineDataset;
  DRAIN_SECRET: string;
}

interface GatewayEvent {
  provider:  string;
  model:     string;
  response:  {
    status:  number;
    latency: number;
    headers: Record<string, string>;
  };
  request: {
    metadata?: { task_type?: string; example project_env?: string };
  };
  cost_usd_micro?: number; // injected by pricing middleware upstream
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.headers.get('X-Gateway-Secret') !== env.DRAIN_SECRET) {
      return new Response('Unauthorized', { status: 401 });
    }

    const events: GatewayEvent[] = await req.json();

    for (const evt of events) {
      const headers = evt.response.headers ?? {};
      const cacheStatus    = (headers['cf-aig-cache-status'] ?? 'BYPASS').toUpperCase();
      const similarityRaw  = headers['cf-aig-cache-score'];
      const similarityScore = similarityRaw ? parseFloat(similarityRaw) : 0;

      writeCacheDataPoint(env.example project_CACHE_METRICS, {
        provider:        evt.provider,
        model:           evt.model,
        taskType:        evt.request.metadata?.task_type ?? 'unknown',
        cacheStatus,
        env:             evt.request.metadata?.example project_env ?? 'prod',
        latencyMs:       evt.response.latency,
        costUsdMicro:    cacheStatus === 'HIT' ? 0 : (evt.cost_usd_micro ?? 0),
        similarityScore,
      });
    }

    return new Response('OK');
  },
};
```

---

## Analytics Engine SQL Queries

```typescript
// src/lib/cache-hit-rate-queries.ts
// Analytics Engine SQL is accessed via the Workers REST API or bindings.
// These queries use the Workers Analytics Engine SQL API.

const AE_ENDPOINT =
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`;

async function queryAE(sql: string, apiToken: string): Promise<any> {
  const res = await fetch(AE_ENDPOINT, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query: sql }),
  });
  return res.json();
}

// Hourly hit rate for the last 24 hours
export async function hourlyHitRate(apiToken: string) {
  return queryAE(`
    SELECT
      toStartOfHour(timestamp)         AS hour,
      blob4                            AS cache_status,
      count()                          AS events,
      countIf(blob4 = 'HIT')           AS hits,
      countIf(blob4 = 'MISS')          AS misses,
      countIf(blob4 = 'HIT') * 100.0
        / count()                      AS hit_rate_pct,
      sum(double2)                     AS total_cost_micro,
      avg(double1)                     AS avg_latency_ms
    FROM example project_CACHE_METRICS
    WHERE
      timestamp > NOW() - INTERVAL '24' HOUR
      AND blob5 = 'prod'
    GROUP BY hour, cache_status
    ORDER BY hour DESC
  `, apiToken);
}

// Similarity score distribution for MISS events — reveals threshold headroom
export async function missScoreDistribution(apiToken: string, taskType: string) {
  return queryAE(`
    SELECT
      floor(double3 * 20) / 20.0       AS score_bucket, -- 0.05-wide buckets
      count()                          AS miss_count,
      avg(double1)                     AS avg_latency_ms
    FROM example project_CACHE_METRICS
    WHERE
      blob4 = 'MISS'
      AND blob3 = '${taskType}'
      AND blob5 = 'prod'
      AND timestamp > NOW() - INTERVAL '7' DAY
    GROUP BY score_bucket
    ORDER BY score_bucket DESC
  `, apiToken);
}

// Daily cost savings attributable to cache hits
export async function dailyCacheSavings(apiToken: string) {
  return queryAE(`
    SELECT
      toDate(timestamp)                AS day,
      sum(double2) / 1000000.0        AS cost_usd_incurred,
      countIf(blob4 = 'HIT')          AS cache_hits,
      countIf(blob4 = 'MISS')         AS cache_misses,
      countIf(blob4 = 'HIT') * 100.0
        / count()                     AS hit_rate_pct
    FROM example project_CACHE_METRICS
    WHERE
      timestamp > NOW() - INTERVAL '30' DAY
      AND blob5 = 'prod'
    GROUP BY day
    ORDER BY day DESC
  `, apiToken);
}
```

---

## Threshold Annotation Events

When changing the semantic cache similarity threshold, write a sentinel data point so the time-series chart shows a vertical annotation line.

```typescript
// src/lib/cache-analytics.ts (continued)
export function writeThresholdChangeAnnotation(
  engine: AnalyticsEngineDataset,
  opts: {
    oldThreshold: number;
    newThreshold: number;
    changedBy:    string;
    env:          string;
  }
): void {
  // Use special cache_status='CONFIG_CHANGE' as the annotation marker
  engine.writeDataPoint({
    blobs:   [
      'config',             // provider placeholder
      'semantic-cache',     // model placeholder
      'threshold-change',   // task_type
      'CONFIG_CHANGE',      // cache_status — sentinel
      opts.env,
    ],
    doubles: [
      0,                    // latency
      0,                    // cost
      opts.newThreshold,    // similarity_score = new threshold value
    ],
    indexes: ['CONFIG_CHANGE'],
  });
}

// Call this from an admin Worker endpoint whenever threshold is updated:
// PUT /admin/cache-threshold  { threshold: 0.92, env: 'prod' }
```

---

## Dashboard Worker Endpoint

```typescript
// src/workers/cache-dashboard.ts
import { hourlyHitRate, dailyCacheSavings } from '../lib/cache-hit-rate-queries';

export interface Env {
  AE_API_TOKEN: string; // stored as a Secret
  ADMIN_KEY: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.headers.get('X-Admin-Key') !== env.ADMIN_KEY) {
      return new Response('Unauthorized', { status: 401 });
    }

    const url = new URL(req.url);
    const route = url.pathname;

    if (route === '/cache/hourly') {
      const data = await hourlyHitRate(env.AE_API_TOKEN);
      return Response.json(data);
    }

    if (route === '/cache/savings') {
      const data = await dailyCacheSavings(env.AE_API_TOKEN);
      return Response.json(data);
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

---

## Anti-patterns

- **Using D1 for raw hit/miss events**: D1 is a relational store suited for structured queries with JOINs. Writing one row per gateway event (which can be thousands per second for example project) will exhaust D1 row write limits. Analytics Engine handles time-series at scale; use D1 only for aggregated summaries.
- **Treating BYPASS the same as MISS**: BYPASS means the cache was intentionally skipped (e.g., `no-cache` header), not that the cache missed. Conflating them inflates the apparent miss rate and leads to incorrect threshold tuning.
- **Querying Analytics Engine in the drain hot path**: The drain Worker should only call `writeDataPoint` (fire-and-forget). Querying AE from the drain Worker adds latency and can timeout.
- **Ignoring similarity scores on MISSes**: The `cf-aig-cache-score` header on MISS events reveals how close the prompt came to a cached entry. If many MISSes score 0.82–0.88 and the threshold is 0.90, lowering the threshold slightly could dramatically improve hit rates.
- **Single global hit-rate metric**: example project has multiple task types. Embedding requests are deterministic (same text = same embedding) and should approach 100% hit rate. Moderation prompts vary. Track hit rates per `task_type`.

---

## Gotchas

- Analytics Engine has an eventual-consistency delay of ~1 minute. Real-time dashboards polling at sub-minute intervals will see stale data and should display a freshness warning.
- The `cf-aig-cache-score` header is only present on MISS and near-HIT responses; it is absent on exact-match HITs (similarity = 1.0). Set the default `similarityScore` to `1.0` for HIT events, not `0`.
- Analytics Engine SQL uses ClickHouse-like syntax, not standard SQL. `toStartOfHour`, `countIf`, and `NOW() - INTERVAL '24' HOUR` are ClickHouse functions. Do not attempt to use SQLite syntax.
- Analytics Engine datasets are write-once. You cannot update or delete data points; incorrect data accumulates until the retention period expires (default 90 days).
- The `indexes` field in `writeDataPoint` accepts a single string, not an array. It is used for fast partition scans; choose the highest-cardinality field you filter on most often.

---

## Verification

```typescript
// Integration test: verify a data point flows end-to-end
// 1. POST a synthetic gateway event to the drain endpoint
const testEvent = [{
  provider: 'anthropic',
  model: 'claude-3-5-haiku-20241022',
  response: {
    status: 200,
    latency: 12, // 12ms cache hit
    headers: {
      'cf-aig-cache-status': 'HIT',
      'cf-aig-cache-score': '0.97',
    },
  },
  request: { metadata: { task_type: 'moderation', example project_env: 'staging' } },
  cost_usd_micro: 0,
}];

// 2. Wait 90 seconds for AE ingestion
// 3. Query hourly hit rate for staging
// SELECT countIf(blob4='HIT'), blob5 FROM example project_CACHE_METRICS
// WHERE blob5='staging' AND timestamp > NOW() - INTERVAL '5' MINUTE
// Expected: countIf(...) >= 1
```

```bash
# Quick sanity-check via wrangler tail on the drain Worker
npx wrangler tail cache-metrics-drain --format=pretty

# Confirm AE write appears in the tail output as a "writeDataPoint" call
```

---

## Related

- `ai-gateway-semantic-cache-threshold-tuning.md` — how to choose the right similarity threshold
- `ai-gateway-caching.md` — AI Gateway caching fundamentals
- `ai-gateway-latency-slo-analytics-engine.md` — Analytics Engine for latency SLOs (same dataset pattern)
- `ai-gateway-provider-cost-comparison-analytics-d1.md` — cost ledger that shows savings from cache hits
- `cloudflare-ai-gateway-observability.md` — general AI Gateway observability setup

---

## Sources

- Cloudflare Analytics Engine docs: https://developers.cloudflare.com/analytics/analytics-engine/
- AI Gateway semantic caching: https://developers.cloudflare.com/ai-gateway/configuration/caching/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- `cf-aig-cache-status` header reference: https://developers.cloudflare.com/ai-gateway/observability/
