# Web Vitals + Cloudflare RUM Integration

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

example project has no visibility into real-user performance on
mobile devices. Lighthouse scores look fine in CI but field
data from mobile users shows poor INP (Interaction to Next
Paint) on low-end Android devices and elevated LCP on iOS
Safari. Cloudflare Pages Analytics shows request counts and
error rates but no Core Web Vitals. There is no current
mechanism to correlate device type, connection speed, or
geographic PoP with performance regressions.

## Context

Google's Core Web Vitals are measured differently in the
lab (Lighthouse, CI) vs the field (real user browsers). Lab
data uses a simulated 4× CPU throttle on desktop — it does
not capture the variance of real Android mid-range phones.
Field data requires a Real User Monitoring (RUM) pipeline:
JavaScript running in the user's browser collects the
metrics and POSTs them to a collection endpoint.

Cloudflare has two relevant products:
- **Cloudflare Browser Insights** — automatic JS injection
  on Cloudflare-proxied sites. Collects LCP, FID, CLS, TTFB.
  Cannot be customised; no INP yet (as of mid-2026).
- **Cloudflare Analytics Engine** — a time-series write API
  available via Workers. You push any metric from your own
  RUM script and query it in Grafana or Workers Analytics.

For example project, the recommended approach is a custom RUM
script using the `web-vitals` npm package posted to a
Cloudflare Worker that writes to Analytics Engine. This
gives full INP visibility, mobile vs desktop segmentation,
and route-level breakdown.

## FID to INP migration

Google retired First Input Delay (FID) from Core Web Vitals
in March 2024. INP (Interaction to Next Paint) is the
replacement and is now a ranking signal.

```
Metric     Measures                        Good      Poor
──────────────────────────────────────────────────────────
FID        Delay before first interaction  < 100 ms  > 300 ms
           handled (deprecated March 2024)

INP        Worst interaction delay over    < 200 ms  > 500 ms
           the entire page lifetime —
           99th percentile of all
           interactions (tap, click, key)
──────────────────────────────────────────────────────────
FID only measured the input delay component; INP includes
input delay + processing time + presentation delay.
INP is much harder to pass on complex React pages and
is significantly worse on mobile (slower JS engines).
```

Mobile vs desktop INP difference in example project context:

```
Factor                        Desktop effect    Mobile effect
──────────────────────────────────────────────────────────────
React re-render on tap        < 10 ms usually   50–200 ms on
  (large component tree)                        mid-range Android

Long tasks blocking main      Rare on desktop   Common: JS parse,
  thread                                        layout on scroll,
                                                image decode

Touch event to pointer        N/A               +8–16 ms on iOS
  event conversion overhead                     Safari

Passive event listener miss   Occasional        Frequent on feed
  (blocking touchstart)                         scroll — degrades
                                                INP and scroll perf
──────────────────────────────────────────────────────────────
```

## web-vitals package setup

```sh
pnpm add web-vitals
```

```ts
// src/lib/vitals.ts
import {
  onCLS,
  onINP,
  onLCP,
  onFCP,
  onTTFB,
  type Metric,
} from 'web-vitals';

const ENDPOINT = '/api/vitals';  // CF Worker endpoint

type DeviceType = 'mobile' | 'tablet' | 'desktop';

function getDeviceType(): DeviceType {
  const ua = navigator.userAgent;
  if (/Mobi|Android/i.test(ua)) return 'mobile';
  if (/Tablet|iPad/i.test(ua)) return 'tablet';
  return 'desktop';
}

function sendMetric(metric: Metric) {
  const body = JSON.stringify({
    name:       metric.name,
    value:      metric.value,
    rating:     metric.rating,        // 'good' | 'needs-improvement' | 'poor'
    delta:      metric.delta,
    id:         metric.id,
    navigationType: metric.navigationType,
    device:     getDeviceType(),
    path:       window.location.pathname,
    connection: (navigator as any).connection?.effectiveType ?? 'unknown',
    timestamp:  Date.now(),
  });

  // Use sendBeacon for metrics sent on page unload/visibility change
  if (navigator.sendBeacon) {
    navigator.sendBeacon(ENDPOINT, body);
  } else {
    fetch(ENDPOINT, {
      method: 'POST',
      body,
      keepalive: true,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

export function initVitals() {
  onCLS(sendMetric);
  onINP(sendMetric);   // Was onFID() — INP is the replacement
  onLCP(sendMetric);
  onFCP(sendMetric);
  onTTFB(sendMetric);
}
```

```tsx
// src/app/layout.tsx
'use client';
import { useEffect } from 'react';
import { initVitals } from '@/lib/vitals';

export function VitalsReporter() {
  useEffect(() => {
    initVitals();
  }, []);
  return null;
}
```

## Cloudflare Worker: vitals collection endpoint

Deploy a Cloudflare Worker as the `/api/vitals` endpoint.
For a `next build --export` project (no server), the Worker
is deployed separately and the URL is configured via an
environment variable.

```ts
// workers/vitals-collector/index.ts
import type { AnalyticsEngineDataset } from '@cloudflare/workers-types';

interface Env {
  VITALS: AnalyticsEngineDataset;
}

interface VitalPayload {
  name:           string;
  value:          number;
  rating:         string;
  delta:          number;
  id:             string;
  navigationType: string;
  device:         string;
  path:           string;
  connection:     string;
  timestamp:      number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': 'https://example project.example.com',
          'Access-Control-Allow-Methods': 'POST',
          'Access-Control-Allow-Headers': 'Content-Type',
        },
      });
    }

    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    let payload: VitalPayload;
    try {
      payload = await request.json();
    } catch {
      return new Response('Invalid JSON', { status: 400 });
    }

    // Write to Analytics Engine
    // Blobs: string dimensions for grouping
    // Doubles: numeric metric values
    env.VITALS.writeDataPoint({
      blobs: [
        payload.name,          // metric name: LCP, INP, CLS …
        payload.rating,        // good | needs-improvement | poor
        payload.device,        // mobile | tablet | desktop
        payload.path,          // URL path for route breakdown
        payload.connection,    // 4g | 3g | 2g | slow-2g
        payload.navigationType,
      ],
      doubles: [
        payload.value,         // metric value in ms (or score for CLS)
        payload.delta,
      ],
      indexes: [
        payload.id.slice(0, 32), // unique metric ID for dedup
      ],
    });

    return new Response(null, {
      status: 204,
      headers: {
        'Access-Control-Allow-Origin': 'https://example project.example.com',
      },
    });
  },
};
```

```toml
# wrangler.toml
name = "example project-vitals-collector"
main = "index.ts"
compatibility_date = "2024-09-23"

[[analytics_engine_datasets]]
binding = "VITALS"
dataset = "web_vitals"
```

## Querying Analytics Engine for mobile INP

Analytics Engine is queried via the Cloudflare API or in
a Worker using the `env.VITALS` SQL binding.

```sql
-- INP p75 by device type for the last 7 days
SELECT
  blob3 AS device,
  quantileWeighted(0.75)(double1) AS inp_p75,
  count() AS samples
FROM web_vitals
WHERE
  timestamp > NOW() - INTERVAL '7' DAY
  AND blob1 = 'INP'
GROUP BY device
ORDER BY inp_p75 DESC;

-- INP poor ratings by path (find worst routes)
SELECT
  blob4 AS path,
  countIf(blob2 = 'poor') AS poor_count,
  count() AS total,
  round(countIf(blob2 = 'poor') / count() * 100, 1) AS pct_poor
FROM web_vitals
WHERE blob1 = 'INP'
GROUP BY path
ORDER BY poor_count DESC
LIMIT 20;
```

## Mobile vs desktop INP: what to look for

```
INP component       How to identify         Fix
──────────────────────────────────────────────────────────
Input delay         > 50 ms between         Yield to main thread
  (main thread      tap and event           before heavy work:
  blocked)          handler fires           setTimeout(0) or
                                            scheduler.yield()

Processing time     Event handler is        Break render into
  (long task)       slow; component         smaller chunks; use
                    re-render is large      React.startTransition
                                            for non-urgent updates

Presentation        Commit to paint is      Avoid synchronous
  delay             slow; layout            layout thrashing;
                    thrashing               batch DOM reads/writes

Touch vs click      touchstart fires        Ensure touchstart
  event latency     earlier than click;     handlers are passive
                    300 ms click delay      or absent; use
                    on some mobile          pointer events
                    browsers
──────────────────────────────────────────────────────────
```

## Anti-patterns

- **Measuring only in Lighthouse** — Lighthouse runs on a
  single simulated device in a controlled environment. Real
  Android mid-range phones show 3–5× worse INP. Always
  collect field data.
- **Using `onFID` instead of `onINP`** — FID is deprecated
  and removed from Google ranking signals. The `web-vitals`
  package still exports it for backward compatibility, but
  new integrations must use `onINP`.
- **Sending metrics via `fetch` without `keepalive: true`**
  — metrics are often sent on `visibilitychange` or
  `pagehide`. A regular `fetch()` is cancelled when the
  page unloads. Use `sendBeacon` or `fetch({ keepalive: true })`.
- **Not setting CORS headers on the vitals Worker** —
  browser `sendBeacon` to a cross-origin endpoint requires
  CORS preflight. Without the `Access-Control-Allow-Origin`
  header, metrics are silently dropped.
- **Collecting metrics without sampling on high-traffic
  pages** — Analytics Engine has a write quota. Add client-
  side sampling for very high-traffic routes:
  `if (Math.random() > 0.1) return;` before `sendMetric`.

## Gotchas

- **INP is a page-level metric** — `web-vitals` reports it
  at the end of the session (page unload / 5-second idle).
  You will not see INP for users who leave immediately.
  Set up the `reportAllChanges: true` option to get
  intermediate INP values during the session.
- **Analytics Engine SQL is BigQuery-like but not standard
  SQL** — `quantileWeighted` is a ClickHouse function; JOIN
  is not available within a single dataset. Export to R2 +
  Parquet for complex cross-dataset queries.
- **Cloudflare Browser Insights does not include INP** —
  the built-in CF analytics only has FID, LCP, CLS, TTFB as
  of mid-2026. For INP you must deploy the custom Worker.
- **`delta` vs `value` for CLS** — CLS `value` is the total
  cumulative score; `delta` is the change since the last
  report. When using `reportAllChanges` store `value`, not
  `delta`, to avoid double-counting.

## Verification

- `POST /api/vitals` returns `204` from the deployed Worker.
- Analytics Engine dataset `web_vitals` has rows after a
  real mobile page visit (check via Cloudflare API or a
  Worker SQL query).
- INP `p75` for `device = 'mobile'` is visible and
  segmented by path in the SQL query results.
- No CORS errors appear in the browser console when the
  vitals payload is sent on page unload.

## Related

- `documentation/docs/policies/frontend/html-web-vitals-inp.md`
- `documentation/docs/policies/frontend/html-web-vitals-lcp.md`
- `documentation/docs/policies/frontend/html-web-vitals-cls.md`
- `documentation/docs/policies/cloudflare/analytics-engine.md`
- `documentation/docs/policies/performance/core-web-vitals-mobile.md`

## Source URLs (verified 2026-08-22)

- web-vitals npm package —
  https://github.com/GoogleChrome/web-vitals
- web.dev — INP —
  https://web.dev/articles/inp
- Cloudflare Analytics Engine SQL API —
  https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Cloudflare — Bind Analytics Engine to a Worker —
  https://developers.cloudflare.com/analytics/analytics-engine/get-started/
- Google Search Central — INP replaces FID (March 2024) —
  https://developers.google.com/search/blog/2023/05/introducing-inp
