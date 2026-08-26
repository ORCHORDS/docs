# Real User Monitoring (RUM) Beacon Endpoint in Workers with OpenTelemetry

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to collect Core Web Vitals (LCP, CLS, INP) and custom performance timings from real users in production, store them cheaply, and query aggregates — without sending data to a third-party analytics vendor. You want sub-millisecond beacon ACK latency so the beacon does not affect page unload.

## Context

A Cloudflare Worker acts as a RUM beacon receiver. The browser sends a `navigator.sendBeacon()` POST (or a `fetch` with `keepalive: true`) containing JSON-encoded performance observations. The Worker validates, enriches with geo/CF headers, and writes to Workers Analytics Engine — a built-in time-series store queryable via the Analytics Engine SQL API. OpenTelemetry semantic conventions are used for field naming so data is portable if you later export to an OTLP backend.

---

## Solution

### 1. Browser SDK — Collect and Send Metrics

```typescript
// public/js/rum.ts
import type { Metric } from 'web-vitals';

const BEACON_URL = 'https://rum.your-domain.workers.dev/v1/rum';

interface RumPayload {
  /** ISO-8601 timestamp */
  ts: string;
  /** Page URL without PII query params */
  url: string;
  /** Navigation entry type: navigate | reload | back_forward | prerender */
  navType: string;
  /** Connection effective type: 4g | 3g | 2g | slow-2g */
  ect: string | null;
  metrics: MetricEntry[];
  /** Performance timing deltas in ms */
  timing: TimingEntry[];
}

interface MetricEntry {
  name: string;   // LCP | CLS | INP | FCP | TTFB
  value: number;
  rating: 'good' | 'needs-improvement' | 'poor';
  id: string;     // web-vitals unique metric ID
}

interface TimingEntry {
  name: string;
  duration: number;
}

const metricsBuffer: MetricEntry[] = [];

/** Called by web-vitals library for each metric. */
export function onMetric(metric: Metric): void {
  metricsBuffer.push({
    name: metric.name,
    value: Math.round(metric.name === 'CLS' ? metric.value * 1000 : metric.value),
    rating: metric.rating,
    id: metric.id,
  });
}

/** Collect PerformanceResourceTiming for key assets. */
function collectTimings(): TimingEntry[] {
  return performance
    .getEntriesByType('resource')
    .filter((e) => e.name.match(/\.(js|css|woff2)$/))
    .slice(0, 20)
    .map((e) => ({
      name: new URL(e.name).pathname,
      duration: Math.round((e as PerformanceResourceTiming).duration),
    }));
}

/** Strip PII from URLs (emails in query params, auth tokens). */
function sanitizeUrl(url: string): string {
  const u = new URL(url);
  const safe = new URLSearchParams();
  for (const [k, v] of u.searchParams) {
    if (!/token|key|secret|email|user/i.test(k)) safe.set(k, v);
  }
  u.search = safe.toString();
  return u.toString();
}

/** Flush buffer on page hide (most reliable signal). */
function flush(): void {
  if (metricsBuffer.length === 0) return;

  const nav = performance.getEntriesByType('navigation')[0] as
    | PerformanceNavigationTiming
    | undefined;

  const payload: RumPayload = {
    ts: new Date().toISOString(),
    url: sanitizeUrl(location.href),
    navType: nav?.type ?? 'navigate',
    ect: (navigator as any).connection?.effectiveType ?? null,
    metrics: [...metricsBuffer],
    timing: collectTimings(),
  };

  // sendBeacon is fire-and-forget; keepalive fetch is the fallback
  const body = JSON.stringify(payload);
  const sent = navigator.sendBeacon(BEACON_URL, new Blob([body], { type: 'application/json' }));
  if (!sent) {
    fetch(BEACON_URL, { method: 'POST', body, keepalive: true, headers: { 'Content-Type': 'application/json' } });
  }
}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') flush();
});
```

### 2. Worker Beacon Receiver

```typescript
// worker/src/rum-beacon.ts
import { Hono } from 'hono';
import { cors } from 'hono/cors';

export interface Env {
  RUM_AE: AnalyticsEngineDataset;
}

/** Analytics Engine allows up to 20 double fields and 20 blob fields. */
interface AEDataPoint {
  doubles: number[];
  blobs: string[];
}

const ALLOWED_ORIGINS = [
  'https://your-domain.com',
  'https://www.your-domain.com',
];

const app = new Hono<{ Bindings: Env }>();

// CORS — beacons are cross-origin; OPTIONS preflight must succeed
app.use(
  '/v1/rum',
  cors({
    origin: (origin) => (ALLOWED_ORIGINS.includes(origin) ? origin : ''),
    allowMethods: ['POST', 'OPTIONS'],
    allowHeaders: ['Content-Type'],
    maxAge: 86400,
  })
);

app.post('/v1/rum', async (c) => {
  // 1. Parse and validate
  let payload: any;
  try {
    payload = await c.req.json();
  } catch {
    return c.text('Bad Request', 400);
  }

  if (!Array.isArray(payload.metrics)) return c.text('Bad Request', 400);

  // 2. Extract Cloudflare-enriched geo data from request headers
  const country = c.req.header('CF-IPCountry') ?? 'XX';
  const colo = c.req.header('CF-Ray')?.split('-')[1] ?? 'UNK';
  const ua = c.req.header('User-Agent') ?? '';

  // 3. Write one data point per metric to Analytics Engine
  for (const metric of payload.metrics) {
    if (typeof metric.name !== 'string' || typeof metric.value !== 'number') continue;

    /**
     * Analytics Engine schema (OTel-inspired naming):
     * doubles[0] = metric value (ms or unitless * 1000 for CLS)
     * blobs[0]   = metric name (LCP|CLS|INP|FCP|TTFB)
     * blobs[1]   = rating (good|needs-improvement|poor)
     * blobs[2]   = page URL
     * blobs[3]   = country code
     * blobs[4]   = CF colo
     * blobs[5]   = connection type
     * blobs[6]   = nav type
     * blobs[7]   = metric ID (for deduplication)
     */
    const point: AEDataPoint = {
      doubles: [metric.value],
      blobs: [
        metric.name,
        metric.rating ?? '',
        (payload.url ?? '').slice(0, 512),
        country,
        colo,
        payload.ect ?? '',
        payload.navType ?? '',
        metric.id ?? '',
      ],
    };

    c.env.RUM_AE.writeDataPoint(point);
  }

  // 4. Return 204 — no body needed; keeps beacon ACK tiny
  return new Response(null, { status: 204 });
});

export default app;
```

### 3. wrangler.toml

```toml
name = "rum-beacon"
main = "worker/src/rum-beacon.ts"
compatibility_date = "2024-09-23"

[[analytics_engine_datasets]]
binding = "RUM_AE"
dataset = "rum_web_vitals"
```

### 4. Analytics Engine SQL Queries — Core Web Vitals Aggregates

```sql
-- P75 LCP by country over the last 24 hours
SELECT
  blob4                          AS country,
  quantileWeighted(0.75)(double1, 1) AS lcp_p75_ms,
  COUNT()                        AS samples
FROM rum_web_vitals
WHERE
  blob1 = 'LCP'
  AND timestamp > NOW() - INTERVAL '1' DAY
GROUP BY country
ORDER BY lcp_p75_ms DESC
LIMIT 20;

-- CWV pass rate (% of pageviews with all three "good")
-- Requires joining three subqueries on metric.id
SELECT
  toStartOfHour(timestamp) AS hour,
  ROUND(
    100 * COUNTIf(blob2 = 'good') / COUNT(),
    1
  ) AS pct_good
FROM rum_web_vitals
WHERE blob1 IN ('LCP', 'CLS', 'INP')
  AND timestamp > NOW() - INTERVAL '7' DAY
GROUP BY hour
ORDER BY hour;

-- P75 INP breakdown by colo
SELECT
  blob5                              AS colo,
  quantileWeighted(0.75)(double1, 1) AS inp_p75_ms,
  COUNT()                            AS samples
FROM rum_web_vitals
WHERE blob1 = 'INP'
  AND timestamp > NOW() - INTERVAL '1' DAY
GROUP BY colo
HAVING samples > 50
ORDER BY inp_p75_ms DESC;
```

### 5. Query the Analytics Engine via REST

```typescript
// scripts/query-rum.ts
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;

async function queryAE(sql: string): Promise<any> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );
  if (!res.ok) throw new Error(`AE query failed: ${res.status} ${await res.text()}`);
  return res.json();
}

const result = await queryAE(`
  SELECT blob1 AS metric, quantileWeighted(0.75)(double1, 1) AS p75
  FROM rum_web_vitals
  WHERE timestamp > NOW() - INTERVAL '1' DAY
  GROUP BY metric
`);
console.table(result.data);
```

---

## Implementation Details

- **`sendBeacon` vs `keepalive fetch`**: `sendBeacon` is preferred because it survives page unload but has a 64 KB body size limit. `keepalive` fetch has the same guarantee in modern browsers with no size restriction. The SDK tries `sendBeacon` first, falls back to fetch.
- **`visibilitychange` + `hidden`**: More reliable than `unload`/`beforeunload` for mobile browsers (which may kill the page without firing those events). The Page Visibility API fires `hidden` before the process is suspended.
- **CLS value scaling**: CLS is a unitless score (e.g., 0.15). Multiplying by 1000 before storing as an integer avoids floating-point precision issues in Analytics Engine's `double` fields.
- **Deduplication by metric ID**: The web-vitals library generates a stable `id` per metric per page load. Store it in `blobs[7]` to deduplicate if you later export to a warehouse and the Worker emits duplicate points during retries.
- **Analytics Engine write budget**: Workers can emit up to 25 million data points/month on the free tier. Each `writeDataPoint()` call is one point. A single page load with 5 metrics = 5 points.

---

## Anti-patterns

- **Awaiting `writeDataPoint()`**: The method is fire-and-forget and returns `undefined`. There is nothing to await. Awaiting a resolved promise wastes CPU budget.
- **Sending raw `location.href` without PII stripping**: Auth tokens, session IDs, or email addresses in query params become permanently stored in the analytics dataset.
- **Wide CORS (`origin: '*'`)**: A wildcard origin allows anyone to flood your beacon endpoint. Always restrict to your own domains.
- **Logging every resource timing entry**: Browsers can produce hundreds of resource entries per page. Filter and cap to the 20 most relevant (JS, CSS, fonts).
- **Blocking the main thread on flush**: Always use `sendBeacon` or `keepalive` fetch — never `XMLHttpRequest` in the `unload` handler (deprecated and blocks the page close).

---

## Gotchas

- Analytics Engine data has a **~1-minute ingestion delay** before it appears in SQL queries. Do not build real-time dashboards expecting sub-second freshness.
- The Analytics Engine SQL API supports a **subset of ClickHouse SQL**. Not all functions available in standard ClickHouse work (e.g., `argMax`, `groupArray`). Check the Cloudflare docs for the current function allowlist.
- `CF-IPCountry` returns `XX` for Tor exit nodes and `T1` for privacy proxies (VPNs). Filter these if you want clean geo breakdowns.
- Workers Analytics Engine **blobs are capped at 1024 bytes each**. Long URLs must be truncated. The SDK's `slice(0, 512)` guard handles this.
- The web-vitals library reports INP as a **final value on page hide**, not a live value. You will not see INP in SPAs until the user navigates away or closes the tab.

---

## Verification

```bash
# Deploy the beacon worker
npx wrangler deploy

# Send a test beacon
curl -X POST https://rum.your-domain.workers.dev/v1/rum \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://your-domain.com' \
  -d '{"ts":"2026-08-24T10:00:00Z","url":"https://your-domain.com/","navType":"navigate","ect":"4g","metrics":[{"name":"LCP","value":1800,"rating":"good","id":"v3-1234"}],"timing":[]}'
# Expected: HTTP 204

# Wait 2 minutes, then query
node scripts/query-rum.ts
# Expected: table with LCP p75 ~1800

# CORS preflight check
curl -X OPTIONS https://rum.your-domain.workers.dev/v1/rum \
  -H 'Origin: https://your-domain.com' \
  -H 'Access-Control-Request-Method: POST' -sI \
  | grep -i 'access-control'
# Expected: access-control-allow-origin: https://your-domain.com
```

---

## Related

- `documentation/docs/policies/frontend/workers-view-transitions-api-edge.md`
- `documentation/docs/policies/frontend/workers-edge-personalisation-htmlrewriter.md`
- Cloudflare Analytics Engine documentation

---

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://github.com/GoogleChrome/web-vitals
- https://developer.mozilla.org/en-US/docs/Web/API/Navigator/sendBeacon
- https://opentelemetry.io/docs/specs/semconv/http/
- https://web.dev/articles/vitals
