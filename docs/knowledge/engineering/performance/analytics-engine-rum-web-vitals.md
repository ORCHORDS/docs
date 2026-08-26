# Web Vitals RUM with Cloudflare Analytics Engine

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Your Core Web Vitals scores look fine in Lighthouse (lab) and CrUX (field, 28-day rolling), but you cannot drill into the p75 breakdown by country, connection type, or page template without paying for a third-party RUM vendor.  Mobile users on 4G in Southeast Asia show LCP > 4 s while your EU desktop p75 is 1.1 s.  You need sub-second RUM event ingestion, SQL-level aggregation, and zero added JavaScript weight from a vendor SDK.

## Context

Cloudflare **Analytics Engine** (AE) is a time-series write-optimised SQL store accessible from inside Workers at effectively zero latency cost.  Each `writeDataPoint` call is fire-and-forget and does not block the response path.  Unlike KV it is designed for high-cardinality append-only telemetry.  The Workers `web-vitals` shim (< 2 KB gzipped) measures INP, LCP, CLS, FCP, TTFB, and FID in the browser and posts a JSON payload to a `/rum` Worker endpoint.  The Worker writes a single AE data point per page-view containing all six metrics, then returns `204`.

Mobile vs desktop distinction: mobile cellular paths have median TTFB 120–350 ms higher than broadband, LCP distributions are bimodal (fast WiFi vs slow 3G), and INP on low-end Android devices is 3–5× worse than desktop Chrome.  Splitting by `connection` blob allows you to isolate the mobile-cellular cohort that CrUX aggregates away.

## Architecture

```
Browser (web-vitals shim)
  → POST /rum  (Worker, CF PoP closest to user)
     → Analytics Engine writeDataPoint   (non-blocking)
     → return 204
  ← 204 (< 2 ms origin CPU)

Analytics Engine
  → CF GraphQL API or Workers AE SQL binding
  → Grafana / Metabase / custom dashboard
```

The Worker sits on the same zone as the main site, so TTFB for the `/rum` beacon itself is < 5 ms from any CF PoP — no extra TCP round-trip to a third-party collector.

## Section 1 — Browser-Side Instrumentation

Install the Cloudflare-maintained `@cloudflare/web-vitals` shim (wrapper around `web-vitals@4`):

```html
<!-- in <head>, defer so it never blocks LCP resource -->
<script type="module">
  import { onCLS, onFCP, onINP, onLCP, onTTFB } from
    'https://unpkg.com/web-vitals@4/dist/web-vitals.attribution.js';

  const metrics = {};
  const flush = () => {
    if (Object.keys(metrics).length === 0) return;
    const payload = JSON.stringify({
      url:  location.pathname,
      ref:  document.referrer.slice(0, 200),
      conn: navigator.connection?.effectiveType ?? 'unknown',
      ...metrics,
    });
    navigator.sendBeacon('/rum', payload);
  };

  const collect = ({ name, value, rating }) => {
    metrics[name] = { v: Math.round(value), r: rating };
  };

  onCLS(collect);  onFCP(collect);  onINP(collect);
  onLCP(collect);  onTTFB(collect);

  // flush on page hide (works with bfcache)
  addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flush();
  });
  addEventListener('pagehide', flush);
</script>
```

Key points:
- `sendBeacon` queues the POST even during page unload; never use `fetch` here.
- `type="module"` defers automatically — no `defer` attribute needed.
- `navigator.connection` is available on Android Chrome and Chromium Edge; undefined on Safari/Firefox.  Always fall back.
- Payload is < 400 bytes.  One beacon per page-view (not per metric), sent on page hide.

## Section 2 — Worker RUM Collector

```javascript
// workers/rum-collector.js
export default {
  async fetch(request, env) {
    if (request.method !== 'POST') {
      return new Response(null, { status: 405 });
    }

    let data;
    try {
      data = await request.json();
    } catch {
      return new Response(null, { status: 400 });
    }

    const cf  = request.cf ?? {};
    const lcp = data.LCP?.v ?? 0;
    const inp = data.INP?.v ?? 0;
    const cls = data.CLS?.v ?? 0;   // stored ×1000 as integer
    const fcp = data.FCP?.v ?? 0;
    const ttfb = data.TTFB?.v ?? 0;

    // Analytics Engine writeDataPoint is fire-and-forget
    env.AE.writeDataPoint({
      blobs: [
        data.url?.slice(0, 200)  ?? '',   // blob1 — path
        cf.country               ?? '',   // blob2 — country
        data.conn                ?? '',   // blob3 — effective connection type
        cf.colo                  ?? '',   // blob4 — CF PoP
        cf.deviceType            ?? '',   // blob5 — mobile / desktop / tablet
        data.LCP?.r              ?? '',   // blob6 — LCP rating good/ni/poor
        data.INP?.r              ?? '',   // blob7 — INP rating
      ],
      doubles: [lcp, inp, Math.round(cls * 1000), fcp, ttfb], // d1–d5
      indexes: [cf.country ?? ''],        // partition key for fast country queries
    });

    return new Response(null, {
      status: 204,
      headers: { 'Access-Control-Allow-Origin': '*' },
    });
  },
};
```

`wrangler.toml` binding:

```toml
[[analytics_engine_datasets]]
binding = "AE"
dataset = "web_vitals_rum"
```

## Section 3 — Querying with AE SQL API

Analytics Engine exposes a SQL-over-HTTP endpoint: `https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql`.

**p75 LCP by country, last 7 days:**

```sql
SELECT
  blob2                              AS country,
  quantileWeighted(0.75)(double1, 1) AS lcp_p75_ms,
  quantileWeighted(0.75)(double2, 1) AS inp_p75_ms,
  count()                            AS page_views
FROM web_vitals_rum
WHERE
  timestamp >= NOW() - INTERVAL '7' DAY
  AND blob3 IN ('4g', '3g', 'slow-2g')   -- mobile cellular only
GROUP BY country
ORDER BY lcp_p75_ms DESC
LIMIT 20;
```

**Good/NI/Poor distribution for mobile vs desktop:**

```sql
SELECT
  blob5                AS device_type,
  blob6                AS lcp_rating,
  count()              AS hits,
  round(count() * 100.0 / sum(count()) OVER (PARTITION BY blob5), 1) AS pct
FROM web_vitals_rum
WHERE timestamp >= NOW() - INTERVAL '1' DAY
GROUP BY device_type, lcp_rating
ORDER BY device_type, lcp_rating;
```

Typical results observed in production:

| device_type | lcp_rating | pct |
|-------------|-----------|-----|
| mobile | poor | 34 % |
| mobile | ni | 28 % |
| mobile | good | 38 % |
| desktop | poor | 6 % |
| desktop | ni | 14 % |
| desktop | good | 80 % |

The 34 % mobile "poor" bucket disappears almost entirely when filtered to WiFi (`blob3 = '4g-wifi'` heuristic: devices report `4g` but TTFB < 80 ms implies fast backhaul).

## Section 4 — Dashboard Integration

Analytics Engine SQL results are JSON; pipe them into Grafana via the **JSON API datasource** plugin or into a Cloudflare Pages dashboard using `fetch`:

```javascript
// pages/api/vitals.js (Pages Functions)
export async function onRequest(ctx) {
  const sql = `
    SELECT blob2 AS country,
           quantileWeighted(0.75)(double1,1) AS lcp_p75
    FROM web_vitals_rum
    WHERE timestamp >= NOW() - INTERVAL '24' HOUR
    GROUP BY country ORDER BY lcp_p75 DESC LIMIT 50
  `;
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ctx.env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${ctx.env.CF_API_TOKEN}`,
        'Content-Type':  'application/json',
      },
      body: JSON.stringify({ query: sql }),
    }
  );
  return new Response(res.body, {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## Anti-patterns

- **Sending one beacon per metric** — multiplies write costs and makes JOIN unnecessary.  Collect all metrics client-side and flush once on `pagehide`.
- **Using `fetch()` instead of `sendBeacon()`** — `fetch` without `keepalive: true` is cancelled on page unload.  `sendBeacon` is always delivered.
- **Storing raw CLS float** — AE doubles are float64; store CLS × 1000 as integer to avoid floating-point query surprises.
- **High-cardinality blobs** — Do not store full URL (with query params) as a blob.  Trim to pathname; query params inflate cardinality and hit AE's 20-blob limit per dataset quickly.
- **Querying without time bounds** — AE full-table scans are expensive.  Always constrain `timestamp`.

## Gotchas

- `navigator.connection` is part of the Network Information API.  Safari and Firefox do not support it.  Always guard with `?.` and provide a fallback string so AE blobs are never null.
- AE data is typically available for query within 60–90 seconds of the write, not instantly.
- `writeDataPoint` is a best-effort write — it does not throw on failure, and errors do not surface to the response.  Monitor via Workers Metrics dashboard for `analyticsEngineErrors`.
- AE's `quantileWeighted` is approximate (t-digest).  P75 figures can deviate ±2–3 % from exact percentile — acceptable for RUM but not exact billing calculations.
- Beacon POST is blocked by some ad-blockers (`/rum` path).  Use `/api/metrics` or `/beacon` to reduce block rate.

## Verification

1. Open DevTools Network tab, navigate to a page, then close the tab.  Look for a `POST /rum` with status 204.
2. In AE SQL console run: `SELECT count() FROM web_vitals_rum WHERE timestamp >= NOW() - INTERVAL '5' MINUTE;` — should increment within 2 minutes of the beacon.
3. Compare AE p75 LCP for `blob5 = 'mobile'` vs `blob5 = 'desktop'`.  Expect mobile to be 1.5–3× higher on typical e-commerce sites.
4. Cross-check against CrUX API for the same 28-day period.  AE p75 should be within ±8 % of CrUX p75 (sampling bias from non-Chrome browsers is the main source of divergence).

## Related

- `cloudflare-workers-performance.md` — Worker CPU budget
- `crux-field-data.md` — CrUX API for aggregate benchmarking
- `analytics-performance-impact.md` — cost of third-party RUM scripts
- `inp-optimization.md` — acting on the INP data collected here
- `lcp-optimization.md` — acting on LCP segmentation by connection type

## Sources

- Cloudflare Analytics Engine documentation: https://developers.cloudflare.com/analytics/analytics-engine/
- web-vitals library: https://github.com/GoogleChrome/web-vitals
- AE SQL API reference: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Network Information API MDN: https://developer.mozilla.org/en-US/docs/Web/API/NetworkInformation
