# Real User Monitoring (RUM) Beacon Endpoint

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to collect Core Web Vitals (LCP, CLS, FID/INP) and custom paint timings from real browsers without running a third-party RUM SaaS. `navigator.sendBeacon()` is fire-and-forget and survives page unload, making it ideal for flushing metrics. A Cloudflare Worker acts as the receiving endpoint, writing into Analytics Engine for queryable, cost-efficient time-series storage.

## Context

Analytics Engine is Cloudflare's write-optimised time-series store with a SQL query API. It supports up to 20 blob columns and 20 double columns per dataset, and queries are answered by the `/v1/accounts/{accountId}/analytics_engine/sql` REST endpoint. This makes it well-suited for RUM: high write throughput, cheap storage, low-latency queries for dashboards.

---

## Section 1 — Browser-side beacon script

```typescript
// public/rum.ts  (bundled and served as a script tag)
import { onLCP, onCLS, onINP, type Metric } from 'web-vitals';

const BEACON_URL = 'https://rum.example.com/beacon';

function send(metric: Metric): void {
  const payload = JSON.stringify({
    name:  metric.name,
    value: metric.value,
    delta: metric.delta,
    id:    metric.id,
    url:   location.href,
    ua:    navigator.userAgent,
    ts:    Date.now(),
  });
  if (navigator.sendBeacon) {
    navigator.sendBeacon(BEACON_URL, new Blob([payload], { type: 'application/json' }));
  } else {
    fetch(BEACON_URL, { method: 'POST', body: payload, keepalive: true }).catch(() => {});
  }
}

onLCP(send);
onCLS(send);
onINP(send);
```

## Section 2 — Worker beacon receiver

```typescript
// rum-worker/src/index.ts
export interface Env {
  RUM: AnalyticsEngineDataset;
}

interface BeaconPayload {
  name:  string;   // 'LCP' | 'CLS' | 'INP' | 'FCP' | 'TTFB'
  value: number;
  delta: number;
  id:    string;
  url:   string;
  ua:    string;
  ts:    number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'OPTIONS') {
      return corsResponse(new Response(null, { status: 204 }));
    }

    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    let payload: BeaconPayload;
    try {
      payload = await request.json<BeaconPayload>();
    } catch {
      return new Response('Bad Request', { status: 400 });
    }

    const { name, value, delta, id, url, ua, ts } = payload;

    // Validate metric name to avoid garbage data
    const validMetrics = new Set(['LCP', 'CLS', 'INP', 'FCP', 'TTFB']);
    if (!validMetrics.has(name)) {
      return new Response('Bad Request', { status: 400 });
    }

    // Parse the pathname for grouping without PII
    const pathname = (() => {
      try { return new URL(url).pathname; } catch { return '/unknown'; }
    })();

    env.RUM.writeDataPoint({
      blobs:   [name, pathname, id, ua.slice(0, 200)],
      doubles: [value, delta, ts],
      indexes: [name],   // shard key — keeps metric types co-located
    });

    return corsResponse(new Response(null, { status: 204 }));
  },
};

function corsResponse(r: Response): Response {
  const headers = new Headers(r.headers);
  headers.set('Access-Control-Allow-Origin', '*');
  headers.set('Access-Control-Allow-Headers', 'Content-Type');
  return new Response(r.body, { status: r.status, headers });
}
```

## Section 3 — Analytics Engine SQL queries

```bash
# Replace $ACCOUNT_ID and $API_TOKEN with your values
export AE_URL="https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql"
export AUTH="Authorization: Bearer $API_TOKEN"

# Median LCP by pathname over the last 24 hours
curl -s -H "$AUTH" \
  --data-urlencode "query=
    SELECT
      blob2                        AS pathname,
      quantileWeighted(0.5)(double1, 1) AS median_lcp_ms,
      count()                      AS samples
    FROM RUM
    WHERE blob1 = 'LCP'
      AND timestamp > NOW() - INTERVAL '1' DAY
    GROUP BY pathname
    ORDER BY median_lcp_ms DESC
    LIMIT 20" \
  "$AE_URL"

# 75th-percentile CLS per hour
curl -s -H "$AUTH" \
  --data-urlencode "query=
    SELECT
      toStartOfHour(timestamp)     AS hour,
      quantileWeighted(0.75)(double1, 1) AS p75_cls
    FROM RUM
    WHERE blob1 = 'CLS'
      AND timestamp > NOW() - INTERVAL '7' DAY
    GROUP BY hour
    ORDER BY hour" \
  "$AE_URL"
```

## Section 4 — wrangler.toml

```toml
# rum-worker/wrangler.toml
name = "rum-worker"
main = "src/index.ts"
compatibility_date = "2025-10-01"
routes = [{ pattern = "rum.example.com/beacon", custom_domain = true }]

[[analytics_engine_datasets]]
binding = "RUM"
dataset = "rum_metrics"
```

```bash
# Deploy
wrangler deploy --config rum-worker/wrangler.toml

# Verify dataset exists
curl -s -H "Authorization: Bearer $API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/datasets"
```

## Anti-patterns

- **Logging full User-Agent strings** — PII concern and wastes blob space. Truncate to 200 chars or parse to browser family only.
- **Using fetch instead of sendBeacon for page-unload metrics** — fetch is cancelled on navigation; `sendBeacon` is guaranteed delivery.
- **Querying Analytics Engine in real-time for every dashboard load** — AE queries have 1–2 s latency. Cache results in KV with a 60-second TTL for dashboards.
- **Storing metric IDs as the shard index** — IDs are unique per page view, resulting in a huge cardinality fan-out. Use the metric name as the index.

## Gotchas

- `writeDataPoint()` is best-effort: if the Worker throws after calling it but before returning a response, the data point is still written.
- Analytics Engine has a maximum of 25 data points written per Worker invocation; batch logic is not required for RUM (1 point per beacon call).
- The AE SQL API only supports a subset of ClickHouse SQL — `JOIN`, `WITH`, and window functions are not available as of 2025.
- CORS preflight (`OPTIONS`) must be handled explicitly; browsers send it before `sendBeacon` when `Content-Type: application/json` is used.

## Verification

```bash
# Send a test beacon
curl -s -X POST https://rum.example.com/beacon \
  -H 'Content-Type: application/json' \
  -d '{"name":"LCP","value":1234,"delta":1234,"id":"v3-abc","url":"https://example.com/","ua":"curl/8","ts":1724515200000}'

# Wait ~60s then query for the test row
curl -s -H "Authorization: Bearer $API_TOKEN" \
  --data-urlencode "query=SELECT blob1, double1 FROM rum_metrics ORDER BY timestamp DESC LIMIT 1" \
  "$AE_URL"
```

## Related

- `workers-tail-worker-request-sampling.md` — server-side trace sampling
- `workers-multi-environment-status-dashboard.md` — status dashboard pattern
- web-vitals library: https://github.com/GoogleChrome/web-vitals

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://web.dev/vitals/
- https://developer.mozilla.org/en-US/docs/Web/API/Navigator/sendBeacon
