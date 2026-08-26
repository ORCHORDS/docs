# RUM Beacon Endpoint Using Workers and Analytics Engine

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Third-party RUM vendors add external script overhead, send data to foreign origins, and expose user behaviour to a third party. A Cloudflare Worker acts as a first-party beacon endpoint that collects Core Web Vitals and custom performance marks, then writes them directly into Analytics Engine for long-term analysis without leaving the Cloudflare network.

## Context

The Web Performance Working Group's PerformanceObserver API surfaces CWV metrics (LCP, INP, CLS, TTFB, FCP) in the browser. A lightweight inline snippet can POST those values to a same-origin `/beacon` route handled by a Worker. The Worker normalises the payload, attaches geo and device metadata from the incoming request, and writes a single Analytics Engine data point per page view. Querying is done later via the Analytics Engine SQL-over-HTTP API or a Grafana datasource — no separate metrics store is needed.

## Beacon Collector Worker

```typescript
export interface Env {
  RUM: AnalyticsEngineDataset;
}

interface BeaconPayload {
  url: string;
  lcp?: number;   // Largest Contentful Paint ms
  inp?: number;   // Interaction to Next Paint ms
  cls?: number;   // Cumulative Layout Shift score × 1000 (integer)
  fcp?: number;   // First Contentful Paint ms
  ttfb?: number;  // Time to First Byte ms
  route?: string; // client-inferred route slug
  connectionType?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "https://example.com",
          "Access-Control-Allow-Methods": "POST",
          "Access-Control-Allow-Headers": "Content-Type",
        },
      });
    }

    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    let payload: BeaconPayload;
    try {
      payload = await request.json();
    } catch {
      return new Response("Bad Request", { status: 400 });
    }

    const cf = request.cf ?? {};
    const country = (cf.country as string) ?? "XX";
    const deviceType = resolveDeviceType(request.headers.get("user-agent") ?? "");
    const route = sanitiseRoute(payload.route ?? payload.url);

    // Analytics Engine writeDataPoint accepts up to 20 blobs and 20 doubles.
    env.RUM.writeDataPoint({
      blobs: [
        country,                                   // blob1: country code
        deviceType,                                // blob2: desktop|mobile|tablet
        route,                                     // blob3: normalised route
        payload.connectionType ?? "unknown",       // blob4: 4g|wifi|unknown
      ],
      doubles: [
        payload.lcp ?? 0,
        payload.inp ?? 0,
        payload.cls ?? 0,
        payload.fcp ?? 0,
        payload.ttfb ?? 0,
      ],
      indexes: [route],  // partition key for efficient per-route queries
    });

    // 204 with no body — keep response tiny for sendBeacon compatibility
    return new Response(null, {
      status: 204,
      headers: { "Access-Control-Allow-Origin": "https://example.com" },
    });
  },
};

function resolveDeviceType(ua: string): string {
  if (/Mobi|Android/i.test(ua)) return "mobile";
  if (/Tablet|iPad/i.test(ua)) return "tablet";
  return "desktop";
}

function sanitiseRoute(raw: string): string {
  try {
    const url = new URL(raw.startsWith("http") ? raw : `https://x.com${raw}`);
    // Replace numeric path segments with :id to reduce cardinality
    return url.pathname.replace(/\/\d+/g, "/:id").slice(0, 64);
  } catch {
    return "/unknown";
  }
}
```

## Browser Snippet

```typescript
// Inline in <head> — no external script dependency
function sendBeacon(metrics: Record<string, number | string | undefined>): void {
  const payload = JSON.stringify({
    url: location.href,
    route: location.pathname,
    connectionType: (navigator as unknown as { connection?: { effectiveType?: string } })
      .connection?.effectiveType,
    ...metrics,
  });

  // navigator.sendBeacon survives page unload; fetch as fallback for older browsers
  const endpoint = "/api/rum/beacon";
  if (navigator.sendBeacon) {
    navigator.sendBeacon(endpoint, new Blob([payload], { type: "application/json" }));
  } else {
    fetch(endpoint, { method: "POST", body: payload, keepalive: true });
  }
}

// Register CWV observers via web-vitals library (loaded async)
import("https://cdn.your-cdn.com/web-vitals.js").then(({ onLCP, onINP, onCLS, onFCP, onTTFB }) => {
  const acc: Record<string, number> = {};
  const flush = (name: string, value: number): void => {
    acc[name.toLowerCase()] = Math.round(name === "cls" ? value * 1000 : value);
    // Send after INP which arrives last on page-hide
    if (Object.keys(acc).length === 5) sendBeacon(acc);
  };
  onLCP((m) => flush("lcp", m.value));
  onINP((m) => flush("inp", m.value));
  onCLS((m) => flush("cls", m.value));
  onFCP((m) => flush("fcp", m.value));
  onTTFB((m) => flush("ttfb", m.value));
});
```

## Analytics Engine Query for p75 LCP per Route

```sql
-- Run against the Analytics Engine SQL API
SELECT
  blob3                            AS route,
  blob2                            AS device,
  quantileWeighted(0.75)(double1, 1) AS lcp_p75_ms,
  quantileWeighted(0.75)(double2, 1) AS inp_p75_ms,
  count()                          AS samples
FROM rum
WHERE timestamp >= now() - INTERVAL '7' DAY
  AND blob1 != 'XX'
GROUP BY route, device
HAVING samples > 50
ORDER BY lcp_p75_ms DESC
LIMIT 50;
```

## Anti-patterns

- Writing one data point per CWV metric instead of one per page view — costs 5× the write quota and makes cross-metric correlation impossible.
- Using the Worker URL as the `indexes` key — high-cardinality index destroys query efficiency; use the normalised route slug.
- Sending raw `document.referrer` as a blob without sanitisation — leaks external URLs into the dataset and inflates cardinality.

## Gotchas

- Analytics Engine has a 25-blob / 25-double limit per data point and a write throughput limit of ~25 000 writes/s per dataset — batch multiple metric events per page view, not per observation.
- `sendBeacon` is silently dropped on some iOS Safari builds when the page is backgrounded immediately; the Worker must treat missing metric fields as nullable and not reject incomplete payloads.

## Verification

```bash
# Tail the beacon Worker in real time to confirm writes are reaching it
wrangler tail rum-beacon --format pretty

# Run a quick SQL query against your Analytics Engine dataset (replace ACCOUNT_ID and API_TOKEN)
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT count() AS n FROM rum WHERE timestamp > now() - INTERVAL '\''1'\'' HOUR"}' \
  | jq '.data'
```

## Related

- `monitoring/cloudflare-analytics-engine.md`
- `monitoring/real-user-monitoring-rum.md`
- `monitoring/analytics-engine-sql-api-programmatic-querying.md`
- `monitoring/core-web-vitals-monitoring.md`

## Sources

- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/runtime-apis/analytics-engine/
- https://web.dev/articles/vitals
