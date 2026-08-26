# cloudflare-web-analytics-privacy-first

Add cookieless, GDPR-compliant page-view and Core Web Vitals analytics to any
website using Cloudflare Web Analytics — no consent banner required, no
personal data collected, single script tag.

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

## Symptom / Use-case

You need basic traffic analytics but have compliance or performance constraints:

- Google Analytics 4 requires a GDPR consent banner in the EU and adds ~30 kB
  of JavaScript to every page
- Self-hosted Plausible or Matomo requires infrastructure maintenance
- You want Core Web Vitals (LCP, CLS, FID/INP) reported automatically per page
- Your Cloudflare zone is already active and you want analytics in one click
- Pages Functions or a Workers site needs analytics without a separate vendor

## Context

Cloudflare Web Analytics is a free analytics product included with all
Cloudflare plans. It uses a single lightweight script (`<1 kB`) injected via
a `<script>` tag or automatically via a Cloudflare Worker (Zaraz). It does NOT
use cookies, does NOT fingerprint users, and does NOT collect IP addresses or
user agents in a personally identifiable way — making it GDPR, CCPA, and PECR
compliant out of the box.

Data is aggregated at ingestion; individual page-view records are not
queryable. Retention is 6 months. For raw event data or custom dimensions,
use Workers Analytics Engine or a third-party pipeline alongside Web Analytics.

## Enabling Web Analytics in the dashboard

1. Cloudflare Dashboard → **Analytics & Logs → Web Analytics**
2. Click **Add a site** → enter your hostname
3. Copy the JS snippet (or use the automatic injection toggle if your zone is
   proxied through Cloudflare)
4. Done — data appears within minutes

The auto-inject option adds the snippet to every HTML response passing through
Cloudflare without modifying your source code:

```
Analytics & Logs → Web Analytics → your site → Settings
→ "Automatic setup (JavaScript Snippet via Cloudflare)"
→ Toggle ON
```

This works for any proxied zone regardless of the site technology (static,
Next.js, WordPress, Workers).

## Manual script tag installation

Use manual installation when you need control over which pages are tracked or
when automatic injection conflicts with CSP headers:

```html
<!-- Add to <head> on every page you want to track -->
<!-- Replace TOKEN with your actual beacon token from the dashboard -->
<script
  defer
  src="https://static.cloudflareinsights.com/beacon.min.js"
  data-cf-beacon='{"token": "YOUR_TOKEN_HERE"}'
></script>
```

For single-page applications (React, Vue, Svelte), fire a virtual page view on
route changes — the beacon script exposes a `trackPageview` method:

```typescript
// React Router v7 / Next.js App Router equivalent
// Call this on every client-side route change
declare global {
  interface Window {
    __cfBeacon?: {
      token: string;
      trackPageview: (options?: { path?: string }) => void;
    };
  }
}

export function trackPageView(path: string) {
  if (typeof window !== "undefined" && window.__cfBeacon) {
    window.__cfBeacon.trackPageview({ path });
  }
}
```

```typescript
// Next.js App Router: app/layout.tsx
"use client";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { trackPageView } from "@/lib/analytics";

export function AnalyticsWrapper() {
  const pathname = usePathname();

  useEffect(() => {
    trackPageView(pathname);
  }, [pathname]);

  return null;
}
```

## Querying data via the Cloudflare GraphQL Analytics API

Cloudflare Web Analytics data is queryable programmatically via the GraphQL
Analytics API — useful for dashboards, Slack bots, or automated reports:

```typescript
const ANALYTICS_QUERY = `
  query WebAnalytics($accountTag: string!, $zoneTag: string!, $since: Time!, $until: Time!) {
    viewer {
      accounts(filter: { accountTag: $accountTag }) {
        rumPageloadEventsAdaptiveGroups(
          filter: { AND: [
            { zoneTag: $zoneTag },
            { datetime_geq: $since },
            { datetime_leq: $until }
          ]}
          limit: 100
          orderBy: [count_DESC]
        ) {
          count
          dimensions {
            requestPath
            deviceType
            countryName
          }
          avg {
            sampleInterval
          }
        }
      }
    }
  }
`;

export async function fetchTopPages(
  accountId: string,
  zoneId: string,
  apiToken: string,
  hours = 24
): Promise<{ path: string; views: number }[]> {
  const since = new Date(Date.now() - hours * 3600 * 1000).toISOString();
  const until = new Date().toISOString();

  const response = await fetch("https://api.cloudflare.com/client/v4/graphql", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query: ANALYTICS_QUERY,
      variables: {
        accountTag: accountId,
        zoneTag: zoneId,
        since,
        until,
      },
    }),
  });

  const data = await response.json() as any;
  const groups = data?.data?.viewer?.accounts?.[0]?.rumPageloadEventsAdaptiveGroups ?? [];

  return groups.map((g: any) => ({
    path: g.dimensions.requestPath,
    views: g.count,
  }));
}
```

## Combining Web Analytics with Workers Analytics Engine

Web Analytics gives aggregate page views. For custom business events (e.g.
"user converted", "item added to cart") use Workers Analytics Engine alongside:

```typescript
// src/index.ts
export interface Env {
  METRICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Serve the conversion endpoint
    if (url.pathname === "/api/convert" && request.method === "POST") {
      const { plan } = await request.json<{ plan: string }>();

      // Custom business event — not captured by Web Analytics
      env.METRICS.writeDataPoint({
        blobs: [plan, request.cf?.country as string ?? "XX"],
        doubles: [1],
        indexes: ["conversion"],
      });

      return Response.json({ ok: true });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

Web Analytics → page-level traffic. Analytics Engine → custom events and
business KPIs. Use both together; neither replaces the other.

## Anti-patterns

- **Relying on Web Analytics for real-time alerting.** Data is aggregated and
  has a few minutes of ingestion delay. It is not suitable for real-time anomaly
  detection. Use Workers Logs + a webhook Worker for real-time error alerting.
- **Using Web Analytics as a replacement for server-side logs.** The beacon fires
  from the browser — bots, crawlers, and users who block JavaScript are not
  counted. Supplement with server-side analytics (Logpush or Workers Logs) for
  a complete picture.
- **Enabling automatic injection and also adding the manual script tag.** Double
  injection sends two beacons per page view and inflates counts. Pick one method.
- **Treating Cloudflare Web Analytics unique visitor counts as absolute truth.**
  It uses a privacy-preserving estimation model (HyperLogLog-based); counts for
  small sample sizes have a statistical margin of error. Do not base SLA
  calculations on it.
- **Using Web Analytics for HIPAA or financial compliance audit trails.** It is
  a privacy-first aggregate product — it does not store individual records and
  cannot produce audit trails of who viewed what. Use a compliant data warehouse
  pipeline for regulated data.

## Gotchas

- **The beacon script is blocked by some ad blockers.** uBlock Origin and
  Brave's default filter lists block `static.cloudflareinsights.com`. Expect
  5–20% undercounting depending on your audience. This is a feature for user
  privacy, not a bug.
- **Core Web Vitals (LCP, CLS, INP) appear in Web Analytics only for browsers
  that support the PerformanceObserver API.** Safari fully supports CWV as of
  2024; older mobile browsers may not report INP.
- **The automatic injection toggle only works on proxied (orange-cloud) zones.**
  If your DNS record is grey-cloud (DNS only), Cloudflare cannot inject the
  snippet. Use the manual `<script>` tag approach.
- **Web Analytics data is not exportable to CSV or raw events.** If you need
  raw data, set up a Logpush job for `http_requests` instead — it contains
  every request with URL, status, and cache status.
- **Retention is 6 months.** Year-over-year comparisons require exporting data
  before it ages out. Use the GraphQL API on a weekly basis and store snapshots
  in D1 or R2 for long-term trending.

## Verification

1. Enable Web Analytics and wait 5 minutes
2. Navigate to your site in a browser without ad-blocker extensions
3. Open **Analytics & Logs → Web Analytics** in the Cloudflare dashboard
4. Confirm page views appear for the visited URL within 5 minutes
5. Check Core Web Vitals tab — LCP, CLS, INP should populate after ~10 page views

```bash
# Verify beacon request fires (Network tab or curl)
curl -s -I "https://static.cloudflareinsights.com/beacon.min.js" | grep HTTP
# → HTTP/2 200

# Check GraphQL API returns data
curl -s -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"{ viewer { zones(filter:{zoneTag:\"'$ZONE_ID'\"}) { httpRequests1dGroups(limit:1,orderBy:[date_DESC]){sum{requests}}} } }"}' \
  | jq .
```

## Related

- `cloudflare/workers-analytics-engine.md`
- `cloudflare/cloudflare-workers-analytics-engine-custom-metrics.md`
- `cloudflare/workers-logpush.md`
- `cloudflare/zaraz-third-party-tags-mobile-cpu.md`
- Web Analytics docs: https://developers.cloudflare.com/analytics/web-analytics/
- GraphQL Analytics API: https://developers.cloudflare.com/analytics/graphql-api/

## Sources

- https://developers.cloudflare.com/analytics/web-analytics/
- https://developers.cloudflare.com/analytics/web-analytics/enable-web-analytics/
- https://developers.cloudflare.com/analytics/graphql-api/
- https://developers.cloudflare.com/analytics/web-analytics/reference/
