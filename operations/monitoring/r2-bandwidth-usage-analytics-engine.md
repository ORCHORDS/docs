# R2 Bandwidth Usage Trending with Analytics Engine

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

R2 egress to the public internet is billed per GB, but Cloudflare's default R2
dashboard only surfaces aggregated totals over fixed calendar windows. You cannot
see which bucket, object prefix, or geographic region is driving a cost spike, and
you have no programmatic way to alert when egress exceeds a daily threshold. Teams
discover over-budget months only after receiving their invoice.

---

## Context

Every R2 operation passes through a Worker when using the `r2.get` / `r2.put`
binding. That Worker has full visibility into object keys, content lengths, and
request headers (`cf.country`, `cf.colo`). Writing one Analytics Engine row per
significant R2 operation gives you a sub-minute-latency, queryable ledger of bytes
served, segmented by bucket, prefix, and region.

Analytics Engine rows cost ~$0.25 per million writes. For most R2 workloads with
< 50M object serves per day, the telemetry overhead is negligible compared to the
egress savings of catching runaway traffic early.

---

## 1. Wrangler Bindings

```toml
# wrangler.toml
name = "r2-bandwidth-tracker"
compatibility_date = "2025-01-01"

[[r2_buckets]]
binding = "ASSETS"
bucket_name = "my-assets-bucket"

[[analytics_engine_datasets]]
binding = "BW_METRICS"
dataset = "r2_bandwidth"
```

---

## 2. Middleware Worker — Instrument R2 Gets

```typescript
// src/index.ts
import type { R2Bucket, AnalyticsEngineDataset } from "@cloudflare/workers-types";

interface Env {
  ASSETS: R2Bucket;
  BW_METRICS: AnalyticsEngineDataset;
  BUCKET_NAME: string;
}

// Extract the top-level prefix (first path segment) from an object key
function objectPrefix(key: string): string {
  const slash = key.indexOf("/");
  return slash === -1 ? "__root__" : key.slice(0, slash);
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    // Strip leading slash to get the R2 object key
    const key = url.pathname.slice(1);
    if (!key) return new Response("Not Found", { status: 404 });

    const cf = request.cf as { country?: string; colo?: string } | undefined;
    const country = cf?.country ?? "XX";
    const colo = cf?.colo ?? "UNKNOWN";
    const prefix = objectPrefix(key);

    const object = await env.ASSETS.get(key);
    if (!object) return new Response("Not Found", { status: 404 });

    const contentLength = object.size;
    const contentType = object.httpMetadata?.contentType ?? "application/octet-stream";

    // Write telemetry asynchronously — do not block response
    ctx.waitUntil(
      Promise.resolve(
        env.BW_METRICS.writeDataPoint({
          blobs: [
            env.BUCKET_NAME, // index 1: bucket
            prefix,          // index 2: key prefix
            country,         // index 3: requester country
            colo,            // index 4: Cloudflare colo
            contentType,     // index 5: mime type
          ],
          doubles: [
            contentLength,   // index 1: bytes_served
            1,               // index 2: request_count
          ],
          indexes: [env.BUCKET_NAME],
        })
      )
    );

    return new Response(object.body, {
      headers: {
        "Content-Type": contentType,
        "Content-Length": String(contentLength),
        "Cache-Control": "public, max-age=86400",
      },
    });
  },
};
```

---

## 3. Query Bandwidth by Bucket and Prefix

```bash
# Daily egress GB by prefix, last 7 days
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{
    "query": "
      SELECT
        toDate(timestamp)             AS day,
        blob2                         AS prefix,
        sum(double1) / 1073741824.0   AS egress_gb,
        sum(double2)                  AS requests
      FROM r2_bandwidth
      WHERE timestamp >= now() - INTERVAL 7 DAY
      GROUP BY day, prefix
      ORDER BY day DESC, egress_gb DESC
      LIMIT 100
    "
  }'
```

---

## 4. Regional Egress Breakdown

```bash
# Top countries by egress, last 24 hours
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{
    "query": "
      SELECT
        blob3                           AS country,
        sum(double1) / 1073741824.0     AS egress_gb,
        sum(double2)                    AS requests,
        avg(double1)                    AS avg_object_size_bytes
      FROM r2_bandwidth
      WHERE timestamp >= now() - INTERVAL 1 DAY
      GROUP BY country
      ORDER BY egress_gb DESC
      LIMIT 30
    "
  }'
```

---

## 5. Scheduled Alert — Daily Egress Budget

```typescript
// Cron trigger: "0 * * * *" — check hourly, alert if on pace to exceed daily budget
interface Env {
  CF_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  ALERT_WEBHOOK_URL: string;
  DAILY_BUDGET_GB: string; // e.g. "500"
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const budgetGb = parseFloat(env.DAILY_BUDGET_GB);

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
            SELECT sum(double1) / 1073741824.0 AS egress_gb_today
            FROM r2_bandwidth
            WHERE timestamp >= toStartOfDay(now())
          `,
        }),
      }
    );

    const json = await res.json<{ data: Array<{ egress_gb_today: number }> }>();
    const egressGb = json.data[0]?.egress_gb_today ?? 0;

    // Extrapolate to end-of-day based on current hour
    const hourOfDay = new Date().getUTCHours() + 1;
    const projectedGb = (egressGb / hourOfDay) * 24;

    if (projectedGb > budgetGb * 0.8) {
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `R2 egress alert: ${egressGb.toFixed(1)} GB used today, ` +
                `projected ${projectedGb.toFixed(1)} GB vs ${budgetGb} GB budget`,
        }),
      });
    }
  },
};
```

---

## 6. Grafana Time-Series Panel

```sql
-- Hourly egress GB stacked by prefix
SELECT
  toStartOfHour(timestamp) AS time,
  blob2                    AS prefix,
  sum(double1) / 1073741824.0 AS egress_gb
FROM r2_bandwidth
WHERE
  timestamp BETWEEN $__fromTime AND $__toTime
GROUP BY time, prefix
ORDER BY time
```

Set **visualization** to Time series, **Stack series** to Normal, **legend** to
`{{prefix}}`. This surfaces which prefixes drive egress spikes at a glance.

---

## Anti-patterns

- **Writing one row per byte range request** — range requests can be hundreds per
  object for video streaming. Aggregate to one row per full object GET; for range
  requests, write only when `content-length > 1MB` or sample at 10%.
- **Using `object.body` byte count from streaming** — use `object.size` from the
  R2 metadata, not a byte counter on the stream body; the Worker may terminate
  before the full body is consumed.
- **Tracking PUT egress** — R2 ingress (PUT) is free; only GET / public egress
  is billed. Do not conflate them in the same dataset.
- **High-cardinality blobs on full object keys** — individual keys explode
  cardinality. Use prefix segments only; query individual keys via Logpush if
  needed.

---

## Gotchas

- `object.size` reflects the stored object size. If you use Transform Rules to
  rewrite responses (e.g., WebP conversion), the actual bytes served differ. For
  true byte counts, wrap the stream and count in a `TransformStream`.
- Analytics Engine has a **25 blobs + 25 doubles per row** limit. The binding
  silently drops extra fields rather than throwing.
- Queries against `r2_bandwidth` only return data written after the dataset was
  first created. There is no way to backfill historical data from R2 access logs.
- R2 public bucket access (via `r2.dev` URL) bypasses your Worker entirely; this
  telemetry only covers Worker-proxied requests.

---

## Verification

```bash
# Confirm writes are arriving
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query": "SELECT count(), max(timestamp) FROM r2_bandwidth WHERE timestamp >= now() - INTERVAL 1 HOUR"}'

# Validate bytes match R2 usage metrics in dashboard (allow ~5% variance from sampling)
```

---

## Related

- `cloudflare-analytics-engine-custom-metrics.md`
- `cloudflare-analytics-engine.md`
- `analytics-engine-write-limits-and-backpressure.md`
- `cloudflare-billing-cost-anomaly-detection.md`
- `observability-cost-control.md`

---

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/r2/pricing/
