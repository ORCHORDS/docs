# Cloudflare Workers Analytics Engine — Custom Metrics & Grafana Integration

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) emits per-request telemetry from Workers API routes and needs to query that data in Grafana dashboards. The team hits write errors when mixing too many blob/double fields, sees mobile vs desktop segments silently collapsed, and cannot connect Grafana to the SQL API endpoint without a special token type.

## Context

Analytics Engine (AE) is a Cloudflare time-series store backed by ClickHouse. Each Worker binding writes `DataPoint` objects that contain up to **20 blob fields** (strings) and **20 double fields** (numbers). Data is queryable via a SQL HTTP API at `https://api.cloudflare.com/client/v4/accounts/{accountId}/analytics_engine/sql`. AE is not a replacement for Logpush — it's optimised for aggregation, not raw-log retention. example project uses it to track API latency, audio-file-serve counts, and mobile-vs-desktop usage breakdowns.

## Analytics Engine Binding Setup

`wrangler.toml` — declare the dataset binding:

```toml
[[analytics_engine_datasets]]
binding = "AE"
dataset = "example project_api_metrics"
```

The `dataset` name is global to the account; writing from multiple Workers into the same name merges rows. Use distinct dataset names per environment (`example project_api_metrics_staging`, `example project_api_metrics_prod`).

Worker TypeScript — write a data point:

```typescript
export interface Env {
  AE: AnalyticsEngineDataset;
}

function recordMetric(
  ae: AnalyticsEngineDataset,
  route: string,
  deviceType: "mobile" | "desktop" | "unknown",
  statusCode: number,
  latencyMs: number,
  userId: string
) {
  ae.writeDataPoint({
    // blobs: string labels (max 20, max 1 KB each)
    blobs: [
      route,        // blob1
      deviceType,   // blob2
      userId,       // blob3
      "prod",       // blob4 — environment tag
    ],
    // doubles: numeric measurements (max 20)
    doubles: [
      latencyMs,    // double1
      statusCode,   // double2
      1,            // double3 — request count sentinel
    ],
    // indexes: high-cardinality shard key (max 1, max 96 bytes)
    indexes: [route],
  });
}
```

`writeDataPoint` is fire-and-forget; it never throws and never blocks the response path.

## Blobs vs Doubles — Field Type Rules

| Characteristic | Blobs | Doubles |
|---|---|---|
| Type | UTF-8 string | IEEE 754 float64 |
| Max per DataPoint | 20 | 20 |
| Max size per field | 1 024 bytes | — |
| Queryable in SQL WHERE | Yes (string ops) | Yes (numeric ops) |
| Aggregatable (SUM/AVG) | No | Yes |
| NULL handling | Empty string stored | 0 stored if omitted |
| Index candidate | No (use `indexes[]`) | No |

Rules of thumb:
- Route path, device type, region, user tier → blob
- Latency, byte count, status code, item count → double
- User ID / session ID → blob (but consider cardinality cost)

Never put a numeric value in a blob field if you intend to `SUM` or `AVG` it later; the SQL API has no implicit cast.

## Mobile vs Desktop Metric Segmentation

example project reads `CF-Device-Type` (set by Cloudflare's device detection when enabled in the zone) and falls back to UA sniffing:

```typescript
function detectDevice(request: Request): "mobile" | "desktop" | "unknown" {
  const cfDevice = request.headers.get("CF-Device-Type");
  if (cfDevice === "mobile" || cfDevice === "tablet") return "mobile";
  if (cfDevice === "desktop") return "desktop";
  // Fallback: coarse UA check for Workers that run without CF device detection
  const ua = request.headers.get("User-Agent") ?? "";
  if (/Mobi|Android|iPhone|iPad/i.test(ua)) return "mobile";
  if (ua.length > 0) return "desktop";
  return "unknown";
}
```

Segment queries — mobile p95 latency vs desktop p95 latency:

```sql
SELECT
  blob2                           AS device_type,
  quantileWeighted(0.95)(double1, double3) AS p95_latency_ms,
  SUM(double3)                    AS total_requests,
  AVG(double2)                    AS avg_status_code
FROM example project_api_metrics
WHERE timestamp >= NOW() - INTERVAL '1' HOUR
  AND blob4 = 'prod'
GROUP BY blob2
ORDER BY total_requests DESC
```

Important: `quantileWeighted` is available in ClickHouse SQL; the AE SQL API is a subset — use `quantile()` with a weight column or approximate with `avg` when exact percentiles aren't critical.

## SQL API Query Reference

```
POST https://api.cloudflare.com/client/v4/accounts/{accountId}/analytics_engine/sql
Authorization: Bearer {token}
Content-Type: application/x-www-form-urlencoded

query=SELECT blob1, SUM(double3) as reqs FROM example project_api_metrics WHERE timestamp > NOW() - INTERVAL '6' HOUR GROUP BY blob1 ORDER BY reqs DESC LIMIT 20
```

Common aggregations:

```sql
-- Requests per route, last 24 h
SELECT blob1 AS route, SUM(double3) AS reqs
FROM example project_api_metrics
WHERE timestamp >= NOW() - INTERVAL '24' HOUR
GROUP BY route ORDER BY reqs DESC;

-- Avg latency by device type and route
SELECT blob2 AS device, blob1 AS route, AVG(double1) AS avg_ms
FROM example project_api_metrics
WHERE timestamp >= NOW() - INTERVAL '1' HOUR
GROUP BY device, route;

-- Error rate (status >= 500)
SELECT
  blob2 AS device,
  SUM(CASE WHEN double2 >= 500 THEN 1 ELSE 0 END) AS errors,
  SUM(double3) AS total,
  SUM(CASE WHEN double2 >= 500 THEN 1 ELSE 0 END) / SUM(double3) AS error_rate
FROM example project_api_metrics
WHERE timestamp >= NOW() - INTERVAL '1' HOUR
GROUP BY device;
```

## Grafana Integration

AE has no native Grafana datasource plugin as of mid-2026. Wire it up via the **Infinity** datasource (URL type: `API`, method: `POST`):

1. Install the Infinity plugin in Grafana.
2. Create a datasource:
   - URL: `https://api.cloudflare.com/client/v4/accounts/<accountId>/analytics_engine/sql`
   - Auth: Custom header `Authorization: Bearer <token>`
   - Body type: `Form Data` — key `query`, value is the SQL string.
3. Set Parser to `JSON` — AE returns `{"data": [...], "meta": [...]}`.
4. Map columns: use JSONPath `$.data[*]` with column names matching `blob1`, `double1`, etc.

Token requirements — the token needs:

| Permission | Level |
|---|---|
| Account Analytics | Read |
| (optional) Account Settings | Read (for dataset listing) |

Do **not** use your Global API Key or a zone-scoped token; account-scoped tokens only.

Grafana variable for dataset/time range:

```
query=SELECT DISTINCT blob1 FROM example project_api_metrics WHERE timestamp >= NOW() - INTERVAL '1' HOUR
```

Bind it to a `$route` variable, then parameterise your panel queries as `WHERE blob1 = '${route}'`.

## Sampling and Data Retention

| Tier | Retention | Write limit |
|---|---|---|
| Workers Free | 3 days | 100 K DataPoints/day |
| Workers Paid | 90 days | 25 M DataPoints/day |
| Enterprise | Configurable | Custom |

example project's paid plan allows ~25 M writes/day. For high-throughput routes (audio delivery), consider sampling: write 1-in-N data points using a deterministic hash so aggregate math remains correct with a multiplier:

```typescript
const SAMPLE_RATE = 10; // write 1 in 10 requests
if (Math.abs(hash(requestId)) % SAMPLE_RATE === 0) {
  ae.writeDataPoint({
    doubles: [latencyMs, statusCode, SAMPLE_RATE], // weight = sample rate
    blobs: [route, deviceType],
  });
}
```

## Anti-patterns

- Storing numeric values in blob fields to do `WHERE blob1 > 500` — blobs are strings; comparison is lexicographic, not numeric.
- Writing a new DataPoint inside `waitUntil` after the response has already returned latency data — write before `return response` so the latency captures real time.
- Using the same dataset name across staging and prod — metrics contaminate each other; prefix by environment.
- Treating `writeDataPoint` as synchronous — there is no acknowledgement; failures (e.g. hitting the 20-field limit) are silent from the Worker's perspective.
- Querying the SQL API from a client-side app — the token is account-level; always proxy through a Worker or server route.

## Gotchas

- **Field position is permanent**: blob1 always means the same thing across your codebase. Document the schema in a shared constant file; refactoring field order silently breaks all historical queries.
- **indexes[] cardinality**: the index is used for sharding; keep it to route-level granularity (not user ID) or query performance degrades.
- **`NOW()` timezone**: AE SQL uses UTC. Grafana's time zone offsets must be applied in the query or in Grafana's panel settings — never add a raw offset string to the SQL.
- **CF-Device-Type requires "Device Type" rule in the zone**: if the Cloudflare zone doesn't have a firewall/transform rule or the legacy "Use Device Type" caching option enabled, the header is absent and all writes fall through to "unknown".
- **Double precision**: doubles are float64 — integer status codes survive without rounding, but currency amounts may drift; store cents as integers.
- **Dataset creation is implicit**: the first `writeDataPoint` creates the dataset. There is no schema definition step.

## Verification

```bash
# Check dataset exists and recent writes landed
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_AE_TOKEN" \
  --data-urlencode "query=SELECT COUNT() as n, MAX(timestamp) as latest FROM example project_api_metrics"

# Expected: {"data":[{"n":12345,"latest":"2026-08-22T..."}],"meta":[...]}

# Verify mobile/desktop split
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_AE_TOKEN" \
  --data-urlencode "query=SELECT blob2 as device, SUM(double3) as reqs FROM example project_api_metrics WHERE timestamp >= NOW() - INTERVAL '1' HOUR GROUP BY device"
```

Local dev: AE bindings are a no-op in `wrangler dev` by default (no local AE store). Use a conditional:

```typescript
if (env.AE) {
  env.AE.writeDataPoint({ ... });
}
```

Or pass `--remote` to `wrangler dev` to write against the real account (use a staging dataset).

## Related

- `workers-analytics-engine.md` — foundational AE setup and binding patterns
- `edge-analytics-device-type-segmentation.md` — CF-Device-Type header details
- `cache-device-type-segmentation-mobile-desktop.md` — device segmentation in cache
- `workers-observability-logs-metrics-2026.md` — overall observability strategy
- `workers-tail-workers.md` — alternative log-shipping path

## Sources

- Cloudflare Analytics Engine docs: https://developers.cloudflare.com/analytics/analytics-engine/
- AE SQL API reference: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Grafana Infinity plugin: https://grafana.com/docs/plugins/yesoreyeram-infinity-datasource/
- CF-Device-Type: https://developers.cloudflare.com/rules/transform/managed-transforms/reference/
