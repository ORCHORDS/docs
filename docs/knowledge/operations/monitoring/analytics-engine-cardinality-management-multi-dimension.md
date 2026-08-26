# Analytics Engine Cardinality Management for Multi-Dimension Workloads

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

An Analytics Engine dataset that tracks request metrics across region, route, status code, user tier, and A/B variant blobs produces millions of unique dimension combinations after a few days of traffic, causing SQL API queries to time out and `GROUP BY` aggregations to return incomplete result sets. You need a cardinality strategy that preserves analytical value while keeping dimension counts within practical query limits.

## Context

Cloudflare Analytics Engine stores each `writeDataPoint` call as a timestamped row. The `blobs` array provides up to 20 string labels and the `indexes` array provides a single indexed key. There is no native cardinality cap enforced at write time, but query performance degrades sharply when a `GROUP BY` over multiple blobs crosses tens of thousands of unique value combinations. Cardinality must be controlled at write time through value normalisation, bucketing, and selective dimension inclusion — not at query time.

## 1. Identify Cardinality Contributors

Before restructuring a dataset, measure the distinct value count per blob column.

```typescript
// src/cardinality-audit.ts
const ACCOUNT_ID = "<ACCOUNT_ID>";
const API_TOKEN = "<CF_API_TOKEN>";

export interface CardinalityRow {
  blob_col: string;
  distinct_values: number;
  top_value: string;
}

export async function auditDatasetCardinality(
  dataset: string,
  intervalHours = 24
): Promise<CardinalityRow[]> {
  // Query distinct counts for each blob column individually.
  // Analytics Engine SQL does not support INFORMATION_SCHEMA,
  // so each column must be queried separately.
  const blobColumns = ["blob1", "blob2", "blob3", "blob4", "blob5"];
  const results: CardinalityRow[] = [];

  for (const col of blobColumns) {
    const sql = `
      SELECT
        '${col}' AS blob_col,
        count(DISTINCT ${col}) AS distinct_values,
        topK(1)(${col})[1] AS top_value
      FROM ${dataset}
      WHERE timestamp > now() - INTERVAL '${intervalHours}' HOUR
    `;

    const resp = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${API_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: sql }),
      }
    );

    if (!resp.ok) continue;
    const json = (await resp.json()) as { data: CardinalityRow[] };
    results.push(...(json.data ?? []));
  }

  return results.sort((a, b) => b.distinct_values - a.distinct_values);
}
```

## 2. Dimension Value Normalisation at Write Time

Apply bucketing and allowlisting before calling `writeDataPoint` to prevent high-cardinality raw values from entering the dataset.

```typescript
// src/dimension-normaliser.ts
export interface RequestDimensions {
  route: string;
  statusCode: number;
  region: string;
  userTier: string;
  abVariant: string;
  responseTimeMs: number;
  requestSizeBytes: number;
}

// Only track the top routes; collapse everything else to "_other"
const KNOWN_ROUTES = new Set([
  "/api/users",
  "/api/products",
  "/api/search",
  "/api/checkout",
  "/api/health",
]);

// Collapse status codes to families
function statusFamily(code: number): string {
  if (code < 200) return "1xx";
  if (code < 300) return "2xx";
  if (code < 400) return "3xx";
  if (code < 500) return "4xx";
  return "5xx";
}

// Collapse numeric response time to latency tier
function latencyTier(ms: number): string {
  if (ms < 50) return "fast";
  if (ms < 200) return "medium";
  if (ms < 1000) return "slow";
  return "very_slow";
}

// Bucket request size to avoid unbounded cardinality from size values
function sizeBucket(bytes: number): string {
  if (bytes < 1_024) return "tiny";
  if (bytes < 10_240) return "small";
  if (bytes < 102_400) return "medium";
  return "large";
}

export function normaliseDimensions(raw: RequestDimensions): {
  blobs: string[];
  doubles: number[];
  index: string;
} {
  const route = KNOWN_ROUTES.has(raw.route) ? raw.route : "_other";
  const status = statusFamily(raw.statusCode);
  const tier = latencyTier(raw.responseTimeMs);
  const size = sizeBucket(raw.requestSizeBytes);

  return {
    // 5 blobs: route, status family, region, user tier, latency tier
    // NOTE: A/B variant intentionally omitted here — stored in a separate
    // low-cardinality dataset to avoid cross-product explosion with route × region.
    blobs: [route, status, raw.region, raw.userTier, tier],
    doubles: [raw.responseTimeMs, raw.requestSizeBytes, 1],
    // Index on route — the most common grouping key in queries
    index: route,
  };
}
```

## 3. Separate High-Cardinality Dimensions into Sibling Datasets

Store A/B variant and user-tier cross-dimensional data in a dedicated dataset to avoid cartesian cardinality with the request metrics dataset.

```typescript
// src/request-metrics-writer.ts
import { normaliseDimensions, type RequestDimensions } from "./dimension-normaliser";

export interface Env {
  REQUEST_METRICS: AnalyticsEngineDataset;
  AB_METRICS: AnalyticsEngineDataset;       // separate dataset for A/B
}

export function writeRequestMetrics(env: Env, dims: RequestDimensions): void {
  const { blobs, doubles, index } = normaliseDimensions(dims);

  // Primary dataset: route × status × region × userTier × latencyTier
  env.REQUEST_METRICS.writeDataPoint({
    blobs,
    doubles,
    indexes: [index],
  });

  // Secondary dataset: A/B variant × route × status only
  // Keeping this dataset narrow prevents cross-product explosion.
  if (dims.abVariant) {
    env.AB_METRICS.writeDataPoint({
      blobs: [dims.abVariant, blobs[0], blobs[1]], // variant, route, status
      doubles: [dims.responseTimeMs, 1],
      indexes: [dims.abVariant],
    });
  }
}
```

## 4. Cardinality Guard: Detect Rogue Values at Write Time

```typescript
// src/cardinality-guard.ts
// Track distinct blob values seen within the current Worker invocation.
// For cross-invocation tracking, use KV or a Durable Object counter.
const invocationSeen = new Map<string, Set<string>>();

const BLOB_CARD_LIMITS: Record<string, number> = {
  blob1: 50,   // routes
  blob2: 6,    // status families
  blob3: 100,  // regions (Cloudflare has ~300 PoPs, but group by continent first)
  blob4: 5,    // user tiers
  blob5: 4,    // latency tiers
};

export function checkCardinality(
  blobIndex: string,
  value: string
): string {
  let seen = invocationSeen.get(blobIndex);
  if (!seen) {
    seen = new Set();
    invocationSeen.set(blobIndex, seen);
  }

  const limit = BLOB_CARD_LIMITS[blobIndex] ?? 100;
  if (!seen.has(value) && seen.size >= limit) {
    // Value exceeds per-invocation cardinality budget; collapse to sentinel
    return `_overflow_${blobIndex}`;
  }
  seen.add(value);
  return value;
}
```

## 5. Low-Cardinality Query Patterns

Always filter on the indexed column first and group by one dimension at a time for fastest query execution.

```typescript
// src/metrics-query.ts
const ACCOUNT_ID = "<ACCOUNT_ID>";
const API_TOKEN = "<CF_API_TOKEN>";

/** Efficient: filter by index (route), group by one blob at a time. */
export async function fetchStatusByRoute(
  route: string,
  intervalHours = 1
): Promise<Array<{ status: string; count: number; p99_ms: number }>> {
  const sql = `
    SELECT
      blob2 AS status,
      sum(double3) AS count,
      quantileWeighted(0.99)(double1, 1) AS p99_ms
    FROM request_metrics
    WHERE
      timestamp > now() - INTERVAL '${intervalHours}' HOUR
      AND blob1 = '${route}'
    GROUP BY status
    ORDER BY count DESC
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  const json = (await resp.json()) as {
    data: Array<{ status: string; count: number; p99_ms: number }>;
  };
  return json.data ?? [];
}

/** Avoid: multi-dimension GROUP BY without a selective WHERE clause. */
// SELECT blob1, blob2, blob3, blob4, blob5, count() FROM request_metrics
// GROUP BY blob1, blob2, blob3, blob4, blob5
// -- This can produce 50 × 6 × 100 × 5 × 4 = 600,000 groups and times out.
```

## 6. wrangler.toml Dataset Bindings

```toml
name = "request-metrics-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[analytics_engine_datasets]]
binding = "REQUEST_METRICS"
dataset = "request_metrics"

[[analytics_engine_datasets]]
binding = "AB_METRICS"
dataset = "ab_test_metrics"
```

## Anti-patterns

- **Storing raw user IDs, session tokens, or trace IDs as blob values**: these are effectively infinite-cardinality strings; they make every query that touches the column a full table scan and prevent any useful aggregation.
- **Using all 20 available blob slots**: more blobs means a higher potential cross-product; use only the blobs you actively query in `GROUP BY` clauses.
- **Combining high-cardinality and low-cardinality dimensions in the same dataset**: a single URL path blob with 10 000 distinct paths combined with a region blob creates 10 000 × 300 = 3 000 000 potential groups, making any multi-dimension query impractical.
- **Using `_overflow_` sentinel values without alerting on them**: silent overflow means dimension data is being discarded; monitor the count of `_overflow_*` values and alert when they represent > 1% of data points.
- **Not separating the A/B experiment dataset from the main metrics dataset**: experiment variants multiply cardinality of every other dimension they are joined with; keep them isolated.

## Gotchas

- Analytics Engine has no schema enforcement; a typo in a blob value (e.g. `"4xx "` with a trailing space) creates a distinct dimension value that silently skews aggregations.
- The `indexes` field accepts only one value per data point; choose the dimension with the highest query selectivity (typically route or tenant ID) as the index.
- Cloudflare's Analytics Engine SQL API has a default row limit of 10 000 on `GROUP BY` results; a cardinality-heavy query silently truncates results rather than returning an error.
- The `topK(n)(column)` function in the SQL API is approximate; use it for cardinality auditing but not for exact top-N reporting in production dashboards.
- Renaming a blob column's semantic meaning (e.g. changing `blob3` from "region" to "continent") without updating all downstream queries causes silent dimension mismatch in historical analysis.

## Verification

1. Write 1 000 data points with intentionally varied blob values (10 routes, 6 status families, 5 regions, 3 tiers).
2. Run the cardinality audit query on each blob column; confirm distinct counts match expected ranges.
3. Attempt a 5-dimension `GROUP BY` without a `WHERE` filter; confirm it either returns within 5 seconds or that you have reduced cardinality sufficiently for it to do so.
4. Inject a raw UUID as `blob1` in 10 data points; confirm the cardinality guard collapses it to `_overflow_blob1` in the dataset.
5. Run `fetchStatusByRoute` with an indexed route; confirm the query completes in < 1 second.

## Related

- `analytics-engine-write-limits-and-backpressure.md`
- `analytics-engine-sql-api-programmatic-querying.md`
- `metrics-cardinality-budget-governance.md`
- `cloudflare-analytics-engine-custom-metrics.md`
- `workers-geolocation-analytics-engine.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/analytics/analytics-engine/get-started/
