# Analytics Engine Custom Metrics: Mobile vs Desktop Segmentation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

The Cloudflare dashboard reports aggregate request counts and error rates
across all clients. However, example project serves two meaningfully different
populations — mobile app users on variable LTE/5G connections and desktop
browser users on broadband — with very different latency tolerances,
feature sets, and failure patterns. An aggregate p99 of 600 ms can mask a
mobile p99 of 1 200 ms if desktop traffic dominates the sample.

The team needs:
- Separate latency histograms per device segment (mobile / desktop /
  tablet / bot).
- Per-segment error rates, cache hit rates, and Worker CPU times written
  at edge without an external HTTP call.
- The ability to query "mobile p99 latency this hour" in a single SQL
  statement against the Analytics Engine SQL API.

---

## Context

Cloudflare Workers Analytics Engine (WAE) stores data points with up to
20 numeric `double` fields, 20 string `blob` fields, and an `indexes`
array used for high-cardinality filtering. The `indexes` field is the
queryable group key: always place the device segment in `indexes[0]` so
WAE can push-down `WHERE index1 = 'mobile'` without scanning all rows.

Device type is detected from the `CF-Device-Type` request header
(injected by the Cloudflare edge when "Device Detection" is enabled in
zone settings) or from a User-Agent parser as a fallback. The CF header
is more reliable than UA parsing for ambiguous clients (tablets, TVs,
old Android browsers).

---

## Section 1: Device Type Resolution

```typescript
// src/lib/device.ts
export type DeviceType = "mobile" | "desktop" | "tablet" | "bot" | "unknown";

// UA patterns for fallback when CF-Device-Type is absent (local dev, non-CF origin)
const MOBILE_UA_RE = /Mobile|Android(?!.*OPR\/)|iPhone|iPod|BlackBerry|IEMobile|Opera Mini/i;
const BOT_UA_RE    = /bot|crawler|spider|scraper|facebookexternalhit|Twitterbot/i;

export function resolveDeviceType(request: Request): DeviceType {
  // CF edge header is authoritative when present
  const cfDeviceType = request.headers.get("CF-Device-Type");
  if (cfDeviceType) {
    // CF returns: desktop | mobile | tablet | bot
    const t = cfDeviceType.toLowerCase();
    if (t === "mobile" || t === "desktop" || t === "tablet" || t === "bot") {
      return t as DeviceType;
    }
  }

  // UA fallback for non-CF traffic
  const ua = request.headers.get("User-Agent") ?? "";
  if (BOT_UA_RE.test(ua))    return "bot";
  if (MOBILE_UA_RE.test(ua)) return "mobile";
  return "desktop";
}
```

---

## Section 2: Analytics Engine Instrumentation Wrapper

Every Worker invocation writes one data point. The data point schema is
fixed across all requests so WAE can efficiently aggregate:

| Field     | Value                      | Type   |
|-----------|----------------------------|--------|
| index1    | device_type                | index  |
| blob1     | route (e.g. /api/v1/songs) | string |
| blob2     | method (GET, POST, …)      | string |
| blob3     | status bucket (2xx, 4xx…)  | string |
| blob4     | country code               | string |
| double1   | wall time (ms)             | number |
| double2   | Worker CPU time (ms)       | number |
| double3   | response bytes             | number |
| double4   | cache hit (1.0 / 0.0)      | number |
| double5   | error (1.0 / 0.0)          | number |

```typescript
// src/lib/metrics.ts
import { resolveDeviceType, type DeviceType } from "./device";

export interface RequestMetrics {
  route: string;
  method: string;
  statusCode: number;
  wallTimeMs: number;
  cpuTimeMs: number;
  responseBytes: number;
  cacheHit: boolean;
  country: string;
}

function statusBucket(code: number): string {
  if (code < 200) return "1xx";
  if (code < 300) return "2xx";
  if (code < 400) return "3xx";
  if (code < 500) return "4xx";
  return "5xx";
}

export function emitRequestMetrics(
  dataset: AnalyticsEngineDataset,
  request: Request,
  m: RequestMetrics,
): void {
  const deviceType: DeviceType = resolveDeviceType(request);

  dataset.writeDataPoint({
    indexes: [deviceType],
    blobs:   [m.route, m.method, statusBucket(m.statusCode), m.country],
    doubles: [
      m.wallTimeMs,
      m.cpuTimeMs,
      m.responseBytes,
      m.cacheHit ? 1 : 0,
      m.statusCode >= 500 ? 1 : 0,
    ],
  });
}
```

---

## Section 3: Worker Integration and wrangler.toml

```typescript
// src/index.ts
import { emitRequestMetrics } from "./lib/metrics";

interface Env {
  ROUTER: Fetcher;
  REQUEST_METRICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const startWall = Date.now();
    const startCpu  = (performance as { now(): number }).now();

    const response = await env.ROUTER.fetch(request.clone());
    const cloned   = response.clone();

    const wallMs = Date.now() - startWall;
    const cpuMs  = (performance as { now(): number }).now() - startCpu;

    // Read response body length without buffering entire body for large media
    const contentLength = parseInt(
      response.headers.get("Content-Length") ?? "0", 10,
    );

    ctx.waitUntil(
      Promise.resolve().then(() => {
        emitRequestMetrics(env.REQUEST_METRICS, request, {
          route:         new URL(request.url).pathname,
          method:        request.method,
          statusCode:    cloned.status,
          wallTimeMs:    wallMs,
          cpuTimeMs:     Math.round(cpuMs),
          responseBytes: contentLength,
          cacheHit:      cloned.headers.get("CF-Cache-Status") === "HIT",
          country:       request.headers.get("CF-IPCountry") ?? "XX",
        });
      }),
    );

    return response;
  },
};
```

```toml
# wrangler.toml
name = "example project-api"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[analytics_engine_datasets]]
binding = "REQUEST_METRICS"
dataset = "request_metrics_v2"
```

---

## Section 4: SQL API Query Patterns

The Analytics Engine SQL API accepts standard SQL with a Cloudflare-
specific time function set. All queries target the `CF_ANALYTICS`
schema; the dataset appears as a table with the same name.

```sql
-- Per-device-type p95 / p99 latency for the last hour
-- WAE does not have a native percentile function — use quantileTDigest
SELECT
  index1                                               AS device_type,
  quantileTDigest(0.50)(double1)                       AS p50_ms,
  quantileTDigest(0.95)(double1)                       AS p95_ms,
  quantileTDigest(0.99)(double1)                       AS p99_ms,
  count()                                              AS requests
FROM  request_metrics_v2
WHERE timestamp > now() - INTERVAL '1' HOUR
GROUP BY device_type
ORDER BY p99_ms DESC;

-- Mobile error rate per route for today
SELECT
  blob1                                                AS route,
  sum(double5)                                         AS errors,
  count()                                              AS total,
  ROUND(sum(double5) * 100.0 / count(), 2)             AS error_rate_pct
FROM  request_metrics_v2
WHERE timestamp > toStartOfDay(now())
  AND index1    = 'mobile'
GROUP BY route
HAVING total > 100
ORDER BY error_rate_pct DESC
LIMIT 20;

-- Cache hit rate comparison: mobile vs desktop (last 24 h)
SELECT
  index1                                               AS device_type,
  sum(double4)                                         AS cache_hits,
  count()                                              AS total,
  ROUND(sum(double4) * 100.0 / count(), 1)             AS hit_rate_pct
FROM  request_metrics_v2
WHERE timestamp > now() - INTERVAL '24' HOUR
  AND index1 IN ('mobile', 'desktop')
GROUP BY device_type;

-- CPU time budget compliance: share of requests under 10 ms CPU
SELECT
  index1                                               AS device_type,
  countIf(double2 < 10)                                AS within_budget,
  count()                                              AS total,
  ROUND(countIf(double2 < 10) * 100.0 / count(), 1)   AS compliance_pct
FROM  request_metrics_v2
WHERE timestamp > now() - INTERVAL '1' HOUR
GROUP BY device_type;
```

---

## Section 5: Grafana Integration via AE SQL API

Configure a Grafana JSON datasource pointing at the AE SQL API:

```json
{
  "url": "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/analytics_engine/sql",
  "jsonData": {
    "httpMethod": "POST",
    "httpHeaderName1": "Authorization"
  },
  "secureJsonData": {
    "httpHeaderValue1": "Bearer <CF_API_TOKEN>"
  }
}
```

Panel query (time-series, mobile p99 over last 6 hours):

```sql
SELECT
  toStartOfFiveMinutes(timestamp) AS time,
  quantileTDigest(0.99)(double1)  AS p99_ms
FROM  request_metrics_v2
WHERE timestamp > now() - INTERVAL '6' HOUR
  AND index1    = 'mobile'
GROUP BY time
ORDER BY time;
```

---

## Anti-patterns

- **Using blob fields as the `indexes` array for device type** — only
  `indexes` fields are used by WAE's internal routing and support
  efficient `WHERE index1 = ...` push-down. Using `blob1` for device
  type forces WAE to scan and filter rows after retrieval.
- **Writing a data point per sub-resource** (e.g., per image, per CSS
  file) — write one data point per user-facing route. Fine-grained
  instrumentation saturates the 1 M free writes/day allowance.
- **Relying on `User-Agent` parsing alone** — UA strings are easily
  spoofed and ambiguous for tablets. Always prefer `CF-Device-Type`
  and fall back to UA parsing only in non-CF environments.
- **Querying without a time-range filter** — the AE SQL API will scan
  the full dataset history. Always include `WHERE timestamp > now() - INTERVAL 'N' ...`.
- **Putting the route as an index value** — routes are potentially
  unbounded (user IDs in paths, etc.). Index fields have cardinality
  limits. Normalise routes to path templates and store as `blob1`.

---

## Gotchas

- Analytics Engine data points are written asynchronously and may have
  up to 60 seconds of ingestion lag. Do not compare AE data to
  real-time dashboard metrics expecting exact alignment.
- The `CF-Device-Type` header requires "Device Identification" to be
  enabled in Zone Settings → Speed → Optimisation. It is off by default
  on older zone configurations.
- WAE's `quantileTDigest` is an approximation (t-digest algorithm);
  error is bounded at ~1% at extreme percentiles. Do not use for exact
  SLO compliance — use it for trend monitoring and dashboards.
- The `indexes` array accepts up to 1 element (one string). If you need
  two segmentation axes (device_type × status_class), concatenate them:
  `indexes: ['mobile:5xx']` and parse in SQL with `splitByChar`.
- Free-tier WAE allows 1 million SQL API reads per day. Complex
  multi-window queries can consume the budget quickly. Prefer
  pre-aggregated recording queries over ad-hoc exploration on free tier.

---

## Verification

```bash
# Confirm the dataset is receiving data points (after a few requests)
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d "SELECT index1 AS device_type, count() AS n
      FROM request_metrics_v2
      WHERE timestamp > now() - INTERVAL '5' MINUTE
      GROUP BY device_type"

# Expected output: rows for mobile, desktop (and bot if bot traffic present)
# If empty: confirm `CF-Device-Type` header is enabled in zone settings
#           and that `writeDataPoint` is called inside `waitUntil`

# Check dataset list
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/datasets" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[].name'
```

---

## Related

- `cloudflare-analytics-engine-custom-metrics.md`
- `cloudflare-analytics-engine.md`
- `cloudflare-analytics-engine-grafana-dashboard.md`
- `rum-mobile-desktop-cwv-disparity.md`
- `mobile-desktop-slo-error-budget-split.md`

---

## Sources

- Cloudflare Analytics Engine overview — https://developers.cloudflare.com/analytics/analytics-engine/
- Analytics Engine SQL API reference — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Cloudflare CF-Device-Type header — https://developers.cloudflare.com/rules/transform/managed-transforms/reference/
- t-digest percentile approximation — https://github.com/tdunning/t-digest
