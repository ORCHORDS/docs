# Workers Geolocation Regional Breakdown with Analytics Engine

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your Workers application serves a global audience but error rates and latency
degrade in specific regions without triggering global SLO alerts. A Cloudflare
incident in APAC, a misrouted DNS update, or a country-specific cache miss pattern
can surface as a regional anomaly invisible to aggregate metrics. You need per-country
and per-colo request, error, and latency breakdowns queryable in real time and
renderable as a choropleth map in Grafana.

---

## Context

Every incoming request to a Worker carries the `request.cf` object populated by
Cloudflare's edge. Fields like `cf.country`, `cf.region`, `cf.colo`, `cf.timezone`,
and `cf.asn` are available without any external GeoIP library. Writing these to
Analytics Engine per request gives you a geographically segmented dataset without
third-party services.

For high-traffic Workers (> 10 000 req/s), write only sampled rows (1 in 10 or
1 in 100) and multiply the doubles by the sample rate when querying. For
error events always write 100% — errors are rare enough that sampling would lose
signal.

---

## 1. Wrangler Binding

```toml
# wrangler.toml
name = "geo-metrics-worker"
compatibility_date = "2025-01-01"

[[analytics_engine_datasets]]
binding = "GEO_METRICS"
dataset = "workers_geo"
```

---

## 2. Request Middleware — Write Geo Rows

```typescript
// src/index.ts
import type { AnalyticsEngineDataset } from "@cloudflare/workers-types";

interface Env {
  GEO_METRICS: AnalyticsEngineDataset;
  SAMPLE_RATE: string; // e.g. "0.1" = 10% sampling for success requests
}

interface CfProps {
  country?: string;
  region?: string;
  city?: string;
  colo?: string;
  timezone?: string;
  asn?: number;
  asOrganization?: string;
  postalCode?: string;
  latitude?: string;
  longitude?: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    const cf = (request.cf ?? {}) as CfProps;
    const sampleRate = parseFloat(env.SAMPLE_RATE ?? "0.1");

    const country = cf.country ?? "XX";
    const colo = cf.colo ?? "UNKNOWN";
    const region = cf.region ?? "UNKNOWN";
    const asOrg = (cf.asOrganization ?? "UNKNOWN").slice(0, 64); // cap cardinality

    let response: Response;
    let status = 500;
    try {
      response = await handleRequest(request, env);
      status = response.status;
    } catch (err) {
      response = new Response("Internal Server Error", { status: 500 });
    }

    const latencyMs = Date.now() - start;
    const isError = status >= 500 ? 1 : 0;
    const isClientError = status >= 400 && status < 500 ? 1 : 0;

    // Always write errors; sample successes
    const shouldWrite = isError === 1 || Math.random() < sampleRate;

    if (shouldWrite) {
      const multiplier = isError === 1 ? 1 : Math.round(1 / sampleRate);
      ctx.waitUntil(
        Promise.resolve(
          env.GEO_METRICS.writeDataPoint({
            blobs: [
              country,                   // index 1: country code (ISO 3166-1 alpha-2)
              region,                    // index 2: region / state
              colo,                      // index 3: Cloudflare colo IATA code
              String(status),            // index 4: HTTP status code
              asOrg,                     // index 5: AS organization name
            ],
            doubles: [
              multiplier,                // index 1: request_count (adjusted for sampling)
              latencyMs * multiplier,    // index 2: total_latency_ms (for avg)
              isError * multiplier,      // index 3: error_count
              isClientError * multiplier,// index 4: client_error_count
            ],
            indexes: [country],
          })
        )
      );
    }

    return response;
  },
};

async function handleRequest(request: Request, env: Env): Promise<Response> {
  // Your actual business logic here
  return new Response("Hello, World!");
}
```

---

## 3. Query: Error Rate by Country

```bash
# Error rate per country, last 1 hour — spot regional incidents
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{
    "query": "
      SELECT
        blob1                               AS country,
        sum(double1)                        AS requests,
        sum(double3)                        AS errors,
        sum(double3) / sum(double1)         AS error_rate,
        sum(double2) / sum(double1)         AS avg_latency_ms
      FROM workers_geo
      WHERE timestamp >= now() - INTERVAL 1 HOUR
      GROUP BY country
      HAVING requests > 100
      ORDER BY error_rate DESC
      LIMIT 50
    "
  }'
```

---

## 4. Query: Colo Performance Breakdown

```bash
# Average latency per Cloudflare colo, last 6 hours
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{
    "query": "
      SELECT
        blob3                               AS colo,
        sum(double1)                        AS requests,
        sum(double2) / sum(double1)         AS avg_latency_ms,
        sum(double3) / sum(double1)         AS error_rate
      FROM workers_geo
      WHERE timestamp >= now() - INTERVAL 6 HOUR
      GROUP BY colo
      ORDER BY avg_latency_ms DESC
      LIMIT 40
    "
  }'
```

---

## 5. Time-Series Regional Trend — Grafana

```sql
-- Hourly request volume stacked by country (top 10 countries by volume)
SELECT
  toStartOfHour(timestamp) AS time,
  blob1                    AS country,
  sum(double1)             AS requests
FROM workers_geo
WHERE
  timestamp BETWEEN $__fromTime AND $__toTime
  AND blob1 IN (
    SELECT blob1 FROM workers_geo
    WHERE timestamp >= now() - INTERVAL 7 DAY
    GROUP BY blob1
    ORDER BY sum(double1) DESC
    LIMIT 10
  )
GROUP BY time, country
ORDER BY time
```

For a world map / choropleth panel, use the Geomap visualization in Grafana with
`country` as the location field and `requests` or `error_rate` as the metric.

---

## 6. Scheduled Regional Anomaly Alert

```typescript
// Fire when a country's error rate in the last 15 min is 3× its prior 1-hour baseline
interface Env {
  CF_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  PAGERDUTY_KEY: string;
}

export default {
  async scheduled(_: ScheduledEvent, env: Env): Promise<void> {
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.CF_API_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: `
            SELECT
              blob1 AS country,
              sumIf(double3, timestamp >= now() - INTERVAL 15 MINUTE)
                / sumIf(double1, timestamp >= now() - INTERVAL 15 MINUTE) AS err_rate_now,
              sumIf(double3, timestamp < now() - INTERVAL 15 MINUTE)
                / sumIf(double1, timestamp < now() - INTERVAL 15 MINUTE) AS err_rate_baseline
            FROM workers_geo
            WHERE
              timestamp >= now() - INTERVAL 75 MINUTE
            GROUP BY country
            HAVING
              sumIf(double1, timestamp >= now() - INTERVAL 15 MINUTE) > 50
              AND err_rate_now > 0.05
              AND err_rate_now > err_rate_baseline * 3
            ORDER BY err_rate_now DESC
            LIMIT 10
          `,
        }),
      }
    );

    const json = await res.json<{ data: Array<Record<string, number | string>> }>();
    for (const row of json.data) {
      await fetch("https://events.pagerduty.com/v2/enqueue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          routing_key: env.PAGERDUTY_KEY,
          event_action: "trigger",
          payload: {
            summary: `Workers regional error spike: ${row.country} error rate ${(Number(row.err_rate_now) * 100).toFixed(1)}%`,
            severity: "warning",
            source: "workers-geo-monitor",
            custom_details: row,
          },
        }),
      });
    }
  },
};
```

---

## Anti-patterns

- **Writing `cf.city` as a blob** — city has very high cardinality (millions of
  distinct values globally). Use country + region only; look up city-level data
  in Logpush if needed.
- **Tracking latitude/longitude as blobs** — these are floats; store them as
  `doubles` only for rare aggregation use-cases, not per-request rows.
- **Not adjusting for sample rate in doubles** — if you write every 10th request,
  queries that `sum(double1)` will undercount by 10×. Multiply by `1/sampleRate`
  at write time so queries need no knowledge of the sample rate.
- **Alerting on absolute counts per country** — always normalize to error rate;
  low-traffic countries have noisy absolute error counts even from single failures.

---

## Gotchas

- `cf.country` returns `"T1"` for Tor exit nodes and `"XX"` for unknown. Handle
  these as distinct buckets rather than `null`.
- `cf.colo` is the three-letter IATA airport code of the Cloudflare PoP (e.g.
  `"LHR"`, `"LAX"`), not the country. Do not confuse with `cf.country`.
- Workers running on a **custom domain with orange-cloud enabled** always serve
  from the nearest Cloudflare PoP, so `cf.colo` is meaningful. Workers behind a
  gray-cloud DNS record may bypass Cloudflare entirely and `cf.colo` will be the
  fallback colo.
- For Workers deployed as **Service Workers** (not ES Module format), `event.request.cf`
  is accessible but some fields may be absent for internally-routed subrequests.

---

## Verification

```bash
# Confirm country codes are populated correctly
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query": "SELECT blob1, count() FROM workers_geo WHERE timestamp >= now() - INTERVAL 1 HOUR GROUP BY blob1 ORDER BY count() DESC LIMIT 10"}'

# Expected: top countries match your known audience geography
# Verify sample rate: total requests from Analytics Engine / Workers Metrics requests ≈ SAMPLE_RATE
```

---

## Related

- `analytics-engine-mobile-desktop-segmentation.md`
- `cloudflare-analytics-engine-custom-metrics.md`
- `real-user-monitoring-rum.md`
- `workers-error-alerting-pagerduty-integration.md`
- `cloudflare-health-checks-origin-monitoring.md`

---

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://www.cloudflare.com/network/
