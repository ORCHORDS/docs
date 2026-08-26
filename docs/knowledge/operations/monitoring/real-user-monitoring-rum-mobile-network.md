# Real User Monitoring RUM Mobile Network Segmentation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Core Web Vitals and API call latency look healthy in synthetic tests
but mobile users on cellular networks report sluggish interactions.
The existing RUM setup sends a single `performance` beacon without
segmenting by network type (4G, 3G, WiFi, unknown). Dashboard graphs
average across connection types, hiding severe degradation on 3G.
Cloudflare Web Analytics custom dimensions are not yet configured.

## Context

The Beacon API (`navigator.sendBeacon`) delivers small payloads to a
collector endpoint after the page unloads without blocking rendering.
`navigator.connection` (Network Information API) exposes
`effectiveType` (`4g`, `3g`, `2g`, `slow-2g`) and `downlink` on
Chrome and Android WebView; it is undefined on iOS Safari. example project
(example.com) targets both iOS and Android PWA; the beacon payload
must fall back gracefully when the API is absent. Cloudflare Web
Analytics supports up to 5 custom dimensions on the paid plan, which
map to WAE blob fields when routed through a Worker.

## Beacon payload design

```typescript
// src/rum/beacon.ts
export interface RumBeacon {
  url:          string;   // pathname only — no PII
  connectionType: string; // '4g' | '3g' | '2g' | 'wifi' | 'unknown'
  downlinkMbps: number;   // 0 if unavailable
  lcp:          number;   // ms, 0 if unavailable
  fid:          number;   // ms, 0 if unavailable
  cls:          number;   // unitless * 1000 (stored as integer)
  ttfb:         number;   // ms
  durationMs:   number;   // navigation timing total
  deviceType:   string;   // 'mobile' | 'desktop' | 'tablet'
}

export function buildBeacon(): RumBeacon {
  const nav  = performance.getEntriesByType('navigation')[0] as
    PerformanceNavigationTiming | undefined;
  const conn = (navigator as any).connection;

  return {
    url:          location.pathname,
    connectionType: resolveConnectionType(conn),
    downlinkMbps:   conn?.downlink ?? 0,
    lcp:            getWebVital('LCP'),
    fid:            getWebVital('FID'),
    cls:            Math.round((getWebVital('CLS') ?? 0) * 1000),
    ttfb:           nav ? nav.responseStart - nav.requestStart : 0,
    durationMs:     nav?.duration ?? 0,
    deviceType:     getDeviceType(),
  };
}

function resolveConnectionType(conn: any): string {
  if (!conn) return 'unknown';
  if (conn.type === 'wifi') return 'wifi';
  return conn.effectiveType ?? 'unknown';   // '4g' | '3g' | '2g'
}
```

## Beacon dispatch via Beacon API

```typescript
// src/rum/dispatch.ts
import { buildBeacon } from './beacon';

export function scheduleBeacon(endpoint: string): void {
  // Fire after page is visually stable — avoid competing with LCP
  if (document.readyState === 'complete') {
    dispatch(endpoint);
  } else {
    window.addEventListener('load', () => {
      // Give web-vitals library 2 s to capture LCP
      setTimeout(() => dispatch(endpoint), 2000);
    });
  }
}

function dispatch(endpoint: string): void {
  const payload = buildBeacon();
  const blob    = new Blob([JSON.stringify(payload)], {
    type: 'application/json',
  });
  // sendBeacon returns false if queue is full; fall back to fetch
  if (!navigator.sendBeacon(endpoint, blob)) {
    fetch(endpoint, {
      method: 'POST',
      body:   blob,
      keepalive: true,
    }).catch(() => { /* best effort */ });
  }
}
```

## Worker collector — WAE write and custom dimension forwarding

```typescript
// src/workers/rum-collector.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const beacon = await request.json() as RumBeacon;

    // Write to Analytics Engine
    env.AE.writeDataPoint({
      blobs: [
        beacon.url,             // blob1: pathname
        beacon.deviceType,      // blob2: device type
        beacon.connectionType,  // blob3: network type
      ],
      doubles: [
        beacon.lcp,             // double1: LCP ms
        beacon.cls,             // double2: CLS * 1000
        beacon.ttfb,            // double3: TTFB ms
        beacon.fid,             // double4: FID ms
        beacon.downlinkMbps,    // double5: downlink Mbps
        beacon.durationMs,      // double6: nav duration ms
      ],
      indexes: [beacon.connectionType],
    });

    return new Response(null, {
      status: 204,
      headers: {
        'Access-Control-Allow-Origin': 'https://example.com',
      },
    });
  },
};
```

## Network type segmentation queries

```sql
-- Median LCP by network type, last 24 h
SELECT
  blob3                               AS network_type,
  blob2                               AS device_type,
  count()                             AS sessions,
  quantile(0.50)(double1)             AS lcp_p50_ms,
  quantile(0.75)(double1)             AS lcp_p75_ms,
  quantile(0.95)(double1)             AS lcp_p95_ms
FROM rum_metrics
WHERE timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY network_type, device_type
ORDER BY lcp_p75_ms DESC;

-- Poor LCP rate (> 4000 ms) by network type
SELECT
  blob3                                                AS network_type,
  countIf(double1 > 4000)                             AS poor_lcp_count,
  count()                                             AS total,
  round(countIf(double1 > 4000) / count() * 100, 1)  AS poor_pct
FROM rum_metrics
WHERE timestamp > NOW() - INTERVAL '24' HOUR
  AND double1 > 0          -- exclude beacons missing LCP
GROUP BY network_type
ORDER BY poor_pct DESC;
```

| Network | LCP p75 target | CLS target | TTFB target |
|---------|---------------|------------|-------------|
| WiFi    | < 2500 ms     | < 0.10     | < 200 ms    |
| 4G      | < 3000 ms     | < 0.10     | < 400 ms    |
| 3G      | < 4000 ms     | < 0.15     | < 800 ms    |
| 2G      | alert only    | —          | —           |

## Cloudflare Web Analytics custom dimensions

Cloudflare Web Analytics (CWA) supports up to 5 custom dimension
slots on the paid plan. Map network type and device type to slots
so they appear in the CWA dashboard alongside built-in data.

```html
<!-- Inject before </body> on example.com Pages -->
<script>
  window.__cfBeaconConfig = {
    token: 'YOUR_BEACON_TOKEN',
    spa:   true,
  };
  // Custom dimensions via __cfBeaconData (set before beacon fires)
  const conn = navigator.connection;
  window.__cfBeaconData = {
    d1: conn ? (conn.type === 'wifi' ? 'wifi' : conn.effectiveType) : 'unknown',
    d2: /mobile|android|iphone/i.test(navigator.userAgent) ? 'mobile' : 'desktop',
  };
</script>
<script
  defer
  src="https://static.cloudflare.com/zaraz/i.js"
  data-cf-beacon='{"token": "YOUR_BEACON_TOKEN"}'
></script>
```

Custom dimension slots `d1`–`d5` map to CWA filter dimensions in
the Cloudflare dashboard under Analytics → Web Analytics → Custom.

## Anti-patterns

- **Dispatching the beacon on `DOMContentLoaded`** — LCP is
  reported after the largest element paints, which may be 2–3 s
  after DOMContentLoaded; fire the beacon on `load` + a 2 s delay.
- **Sending full URL with query params** — query strings often
  contain session tokens or search terms (PII); send `pathname` only.
- **Treating `navigator.connection` as always present** — it is
  absent on iOS Safari and Firefox; guard all accesses with optional
  chaining.
- **Storing CLS raw float (0.048…) in WAE doubles** — WAE stores
  float64 but Grafana panels show many decimal places; multiply by
  1000 and store as integer for clean display.
- **Sending one beacon per page interaction** — single-page apps
  may fire dozens of beacons per session; rate-limit to one per
  route change or batch with a short debounce.

## Gotchas

- `navigator.sendBeacon` has a 64 KB payload limit; JSON beacons
  should be well under 1 KB but avoid attaching stack traces.
- iOS Safari 17+ added partial Network Information API support
  (`navigator.connection.effectiveType`) but `downlink` remains
  undefined — test explicitly.
- The WAE SQL API `quantile` function requires at least one non-null
  data point in the window; a 0-row result set does not mean the
  query failed — it means no beacons arrived in that interval.
- Cloudflare Web Analytics custom dimension slots are fixed at
  provisioning time; reordering them requires re-instrumenting all
  pages.
- CORS preflight: the RUM collector Worker must respond to `OPTIONS`
  with `Access-Control-Allow-Origin` and `Access-Control-Allow-
  Headers: Content-Type` or browsers will block the beacon POST.

## Verification

- On a Chrome Android device (4G sim): load the app, wait 4 s,
  switch to background; confirm WAE receives a beacon with
  `blob3 = '4g'` within 2 min.
- On iOS Safari: confirm beacon fires with `blob3 = 'unknown'` and
  no JS error in the console.
- Query `SELECT count() FROM rum_metrics WHERE blob3 = 'unknown'`
  for the last hour and confirm the count is consistent with iOS
  Safari share in analytics.
- CWA dashboard → Custom → d1 shows `wifi`, `4g`, `3g`, `unknown`
  within 15 min of test traffic.
- Beacon size: `JSON.stringify(buildBeacon()).length` < 512 bytes.

## Related

- `documentation/docs/policies/monitoring/frontend-real-user-monitoring-rum.md`
- `documentation/docs/policies/monitoring/rum-mobile-desktop-cwv-disparity.md`
- `documentation/docs/policies/monitoring/core-web-vitals-monitoring.md`
- `documentation/docs/policies/monitoring/cloudflare-analytics-engine-custom-metrics.md`
- `documentation/docs/policies/monitoring/mobile-crash-monitoring.md`
- `documentation/docs/policies/monitoring/log-security-masking.md`

## Sources

- Network Information API (MDN) —
  https://developer.mozilla.org/en-US/docs/Web/API/NetworkInformation
- Beacon API (MDN) —
  https://developer.mozilla.org/en-US/docs/Web/API/Beacon_API
- web-vitals library —
  https://github.com/GoogleChrome/web-vitals
- Cloudflare Web Analytics custom dimensions —
  https://developers.cloudflare.com/web-analytics/get-started/
- WAE Worker binding write API —
  https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
