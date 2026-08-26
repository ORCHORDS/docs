# Vectorize Query Recall Rate Monitoring with Analytics Engine

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare Vectorize powers semantic search and RAG pipelines in example project A degraded
index — after a bulk upsert, a namespace schema change, or a model swap — returns
fewer neighbours than requested (`topK`) or returns vectors from the wrong namespace.
Without recall rate monitoring you discover the regression only through user complaints
("search returned nothing relevant") rather than through automated alerts.

This article defines a recall rate SLO for Vectorize, instruments the query path, and
tracks the metric in Analytics Engine with an alert when the rate drops below 0.80.

---

## Context

Vectorize `query()` returns up to `topK` matches. A practical recall proxy is the
**fill rate**: `actual_matches / topK`. A fill rate of 1.0 means Vectorize found as
many neighbours as requested; 0.0 means the index returned nothing. True recall
requires ground-truth labels; fill rate is a cheap online proxy available on every
production query.

example project uses Vectorize for:
- Semantic document search (namespace: `example project-docs`, model: `bge-small-en-v1.5`)
- Product recommendation (namespace: `example project-products`, model: `bge-base-en-v1.5`)
- User preference matching (namespace: `example project-prefs`, model: `bge-small-en-v1.5`)

Each namespace gets its own Analytics Engine index dimension so regressions can be
isolated per namespace.

---

## Instrumented Vectorize Query Wrapper

```typescript
// src/vectorize/monitored-query.ts

export interface VectorizeQueryOptions {
  namespace: string;
  topK: number;
  returnMetadata?: 'all' | 'indexed' | 'none';
  filter?: VectorizeVectorMetadataFilter;
}

export interface RecallMetrics {
  fillRate: number;          // actualMatches / topK
  latencyMs: number;
  topK: number;
  actualMatches: number;
}

export async function monitoredVectorizeQuery(
  index: VectorizeIndex,
  ae: AnalyticsEngineDataset,
  queryVector: number[],
  opts: VectorizeQueryOptions,
): Promise<{ matches: VectorizeMatch[]; metrics: RecallMetrics }> {
  const { namespace, topK, returnMetadata = 'none', filter } = opts;
  const start = Date.now();
  let outcome: 'ok' | 'error' = 'ok';

  try {
    const result = await index.query(queryVector, {
      topK,
      returnMetadata,
      ...(filter ? { filter } : {}),
    });

    const actualMatches = result.matches?.length ?? 0;
    const fillRate = topK > 0 ? actualMatches / topK : 0;
    const latencyMs = Date.now() - start;

    // Write to Analytics Engine
    ae.writeDataPoint({
      blobs: [
        namespace,              // blob1: namespace
        outcome,                // blob2: outcome
        fillRate >= 0.8 ? 'pass' : 'fail', // blob3: slo_status
      ],
      doubles: [
        fillRate,               // double1
        latencyMs,              // double2: ms
        actualMatches,          // double3
        topK,                   // double4
      ],
      indexes: [namespace],
    });

    return {
      matches: result.matches ?? [],
      metrics: { fillRate, latencyMs, topK, actualMatches },
    };
  } catch (err) {
    outcome = 'error';
    const latencyMs = Date.now() - start;

    ae.writeDataPoint({
      blobs: [namespace, 'error', 'fail'],
      doubles: [0, latencyMs, 0, topK],
      indexes: [namespace],
    });

    throw err;
  }
}
```

---

## Usage in RAG Pipeline

```typescript
// src/workers/semantic-search.ts
import { monitoredVectorizeQuery } from '../vectorize/monitored-query';

interface Env {
  VECTORIZE_INDEX: VectorizeIndex;
  WORKERS_AI: Ai;
  AE: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { query, topK = 10, namespace = 'example project-docs' } =
      await request.json<{ query: string; topK?: number; namespace?: string }>();

    // 1. Embed the query
    const embedResult = await env.WORKERS_AI.run('@cf/baai/bge-small-en-v1.5', {
      text: [query],
    });
    const queryVector = embedResult.data[0];

    // 2. Query Vectorize with monitoring
    const { matches, metrics } = await monitoredVectorizeQuery(
      env.VECTORIZE_INDEX,
      env.AE,
      queryVector,
      { namespace, topK },
    );

    return new Response(
      JSON.stringify({ matches, metrics }),
      { headers: { 'Content-Type': 'application/json' } },
    );
  },
} satisfies ExportedHandler<Env>;
```

---

## Analytics Engine Recall Rate Queries

```sql
-- Recall fill rate by namespace (last 1 hour, 5-minute buckets)
SELECT
  toStartOfFiveMinutes(timestamp)       AS bucket,
  blob1                                 AS namespace,
  AVG(_sample_interval * double1)       AS avg_fill_rate,
  MIN(_sample_interval * double1)       AS min_fill_rate,
  COUNT(*)                              AS queries
FROM example project_VECTORIZE_METRICS
WHERE timestamp >= NOW() - INTERVAL '1' HOUR
  AND blob2 = 'ok'
GROUP BY bucket, namespace
ORDER BY bucket DESC, namespace;

-- SLO compliance: % of queries with fill_rate >= 0.8
SELECT
  blob1                                  AS namespace,
  COUNTIF(blob3 = 'pass')                AS passing_queries,
  COUNT(*)                               AS total_queries,
  ROUND(100.0 * COUNTIF(blob3 = 'pass') / COUNT(*), 2)  AS slo_pct
FROM example project_VECTORIZE_METRICS
WHERE timestamp >= NOW() - INTERVAL '24' HOUR
  AND blob2 != 'error'
GROUP BY namespace
ORDER BY slo_pct ASC;

-- Error rate by namespace
SELECT
  blob1                                  AS namespace,
  COUNTIF(blob2 = 'error')               AS errors,
  COUNT(*)                               AS total,
  ROUND(100.0 * COUNTIF(blob2 = 'error') / COUNT(*), 2) AS error_pct
FROM example project_VECTORIZE_METRICS
WHERE timestamp >= NOW() - INTERVAL '1' HOUR
GROUP BY namespace
ORDER BY error_pct DESC;
```

---

## Alerting Worker (Cron, every 5 min)

```typescript
// src/workers/vectorize-recall-alert.ts
interface Env {
  AE_ACCOUNT_ID: string;
  AE_API_TOKEN: string;
  SLACK_WEBHOOK_URL: string;
}

const SLO_TARGET = 0.80;

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const sql = `
      SELECT
        blob1                                    AS namespace,
        AVG(_sample_interval * double1)          AS avg_fill_rate,
        COUNT(*)                                 AS queries
      FROM example project_VECTORIZE_METRICS
      WHERE timestamp >= NOW() - INTERVAL '5' MINUTE
        AND blob2 = 'ok'
      GROUP BY namespace
      HAVING avg_fill_rate < ${SLO_TARGET}
    `;

    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.AE_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${env.AE_API_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query: sql }),
      },
    );
    const { data } = (await res.json()) as {
      data: Array<{ namespace: string; avg_fill_rate: number; queries: number }>;
    };

    if (!data || data.length === 0) return;

    const text = data
      .map(
        (r) =>
          `*Vectorize recall alert* namespace=${r.namespace} fill_rate=${(r.avg_fill_rate * 100).toFixed(1)}% (SLO=${SLO_TARGET * 100}%) over ${r.queries} queries`,
      )
      .join('\n');

    await fetch(env.SLACK_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
  },
} satisfies ExportedHandler<Env>;
```

---

## Namespace Drift Detection

When a new embedding model is deployed, vector distances shift and the fill rate may
drop even if the index is healthy. Detect model-switch regressions by comparing
fill rates before and after a deployment event.

```sql
-- Compare average fill rate in 1-hour windows before and after a deployment time
WITH before AS (
  SELECT blob1 AS ns, AVG(double1) AS fill_rate
  FROM example project_VECTORIZE_METRICS
  WHERE timestamp BETWEEN '2026-08-22T14:00:00Z' AND '2026-08-22T15:00:00Z'
    AND blob2 = 'ok'
  GROUP BY ns
),
after AS (
  SELECT blob1 AS ns, AVG(double1) AS fill_rate
  FROM example project_VECTORIZE_METRICS
  WHERE timestamp BETWEEN '2026-08-22T16:00:00Z' AND '2026-08-22T17:00:00Z'
    AND blob2 = 'ok'
  GROUP BY ns
)
SELECT
  b.ns,
  b.fill_rate                                 AS before_fill_rate,
  a.fill_rate                                 AS after_fill_rate,
  ROUND((a.fill_rate - b.fill_rate) * 100, 2) AS delta_pct
FROM before b JOIN after a ON b.ns = a.ns
ORDER BY delta_pct ASC;
```

---

## Anti-patterns

- **Using cosine similarity score as a recall proxy** — a score of 0.9 does not mean
  topK results were returned; always use `matches.length / topK`.
- **Skipping monitoring on cached query results** — cache hits should still emit a data
  point with `fillRate = 1.0` and `latencyMs = 0` to avoid biasing averages downward.
- **Alerting on a single low-fill query** — apply a minimum query volume threshold
  (`HAVING queries > 10`) to avoid false alerts during low-traffic periods.
- **Using the same AE dataset for all AI features** — mixing Vectorize and Workers AI
  metrics in one dataset makes namespace-scoped queries expensive; keep dedicated
  datasets per feature class.

---

## Gotchas

- Vectorize `topK` has a maximum of **20** per query. Requests for more must be
  client-side merged from multiple calls; the fill rate calculation must use the
  effective topK per call, not the logical topK.
- After a `deleteByIds()` operation the index may temporarily return fewer results
  while segments are compacted; expect fill rate dips of up to 60 seconds.
- Namespace filters are applied post-ANN retrieval; with a very restrictive filter the
  fill rate can legitimately be low without an index regression.
- The Vectorize REST API (used in tests) returns a `VectorizeQueryResult` object
  identical to the binding — use the same wrapper in integration tests to populate
  the staging Analytics Engine dataset.

---

## Verification

```bash
# Confirm data points arriving in Analytics Engine
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT blob1 AS ns, COUNT(*) AS n, AVG(double1) AS avg_fill FROM example project_VECTORIZE_METRICS WHERE timestamp >= NOW() - INTERVAL '"'"'10'"'"' MINUTE GROUP BY ns"}' \
  | jq '.data'

# Manual smoke test via wrangler
npx wrangler vectorize query example project-docs \
  --vector="[0.1,0.2,0.3]" \
  --top-k=10 \
  | jq '.matches | length'
```

---

## Related

- `workers-ai-inference-latency-analytics-engine.md`
- `workers-ai-model-fallback-error-rate-monitoring.md`
- `analytics-engine-funnel-conversion-tracking.md`
- `cloudflare-analytics-engine-custom-metrics.md`
- `sli-slo-sla-definitions.md`

---

## Sources

- Cloudflare Vectorize docs: https://developers.cloudflare.com/vectorize/
- Vectorize query API: https://developers.cloudflare.com/vectorize/reference/client-api/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Workers AI embedding models: https://developers.cloudflare.com/workers-ai/models/
