# Self-hosted Cloudflare Web Analytics Beacon with Custom Dimensions

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You serve HTML from a Worker and want page-view analytics without a client-side tag manager. You need the Cloudflare Web Analytics beacon injected automatically by the Worker, enriched with custom dimensions (user role, plan tier, A/B variant), and queryable via the GraphQL Analytics API so you can compare traffic data against your own Analytics Engine events.

---

## Context
Cloudflare Web Analytics (CWA) is a privacy-first, cookieless analytics product built into the Cloudflare dashboard. It works by loading a small beacon script (`https://static.cloudflare.com/zaraz/i.js` or the classic beacon) that calls home with page-view data. When you control the HTML output through a Worker, you can inject the `<script>` tag via HTMLRewriter, set the `window.__cfBeacon` configuration object before the script loads, and call `zaraz.track()` for custom events. The GraphQL Analytics API (`https://api.cloudflare.com/client/v4/graphql`) exposes the `httpRequestsAdaptiveGroups` and `webAnalyticsVisitorsAdaptiveGroups` datasets for programmatic querying, making it possible to cross-reference CWA page views against Analytics Engine funnel data.

---

## Setup / Config

```toml
# wrangler.toml
name = "beacon-injector"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
# Obtain from Cloudflare Dashboard → Web Analytics → Sites → Manage Site
CWA_TOKEN = "your-32-char-web-analytics-token"
```

For Zaraz custom events, enable **Zaraz** on the zone in the Cloudflare dashboard and add a **Custom Event** trigger named `page_action`.

---

## Implementation — Beacon Injection via HTMLRewriter

```typescript
// src/beacon.ts

export interface BeaconConfig {
  token: string;
  spa: boolean;
  /** Optional custom dimensions passed via data attributes on the script tag */
  customDimensions?: Record<string, string>;
}

/**
 * HTMLRewriter handler that injects the CWA beacon script
 * immediately before </head>.
 *
 * The window.__cfBeacon object must be set BEFORE the beacon script
 * loads, so we inject a <script> block first, then the beacon src.
 */
export class BeaconInjector implements HTMLRewriterElementContentHandlers {
  constructor(private readonly config: BeaconConfig) {}

  element(element: Element): void {
    const { token, spa, customDimensions = {} } = this.config;

    // Inline config block — must precede the beacon script
    const configScript = `<script>
window.__cfBeacon = { token: '${token}', spa: ${spa} };
</script>`;

    // Custom dimension data attributes become properties on __cfBeacon
    const dataAttrs = Object.entries(customDimensions)
      .map(([k, v]) => `data-${k}="${v}"`)
      .join(" ");

    const beaconScript = `<script defer src='https://static.cloudflare.com/beacon/beacon.min.js' ${dataAttrs}></script>`;

    element.before(configScript + "\n" + beaconScript, { html: true });
  }
}
```

```typescript
// src/index.ts
import { BeaconInjector } from "./beacon";

export interface Env {
  CWA_TOKEN: string;
}

/** Extract custom dimension values from the request context. */
function resolveCustomDimensions(
  request: Request
): Record<string, string> {
  // Example: read role from a JWT claim or cookie header
  const role = request.headers.get("X-User-Role") ?? "anonymous";
  const plan = request.headers.get("X-User-Plan") ?? "free";
  const variant = request.headers.get("X-AB-Variant") ?? "control";
  return { role, plan, variant };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Fetch the origin HTML (or render it inline)
    const originResponse = await fetch(request);

    const contentType = originResponse.headers.get("content-type") ?? "";
    if (!contentType.includes("text/html")) {
      return originResponse;
    }

    const customDimensions = resolveCustomDimensions(request);

    const rewriter = new HTMLRewriter().on(
      "head",
      new BeaconInjector({
        token: env.CWA_TOKEN,
        spa: true,
        customDimensions,
      })
    );

    return rewriter.transform(originResponse);
  },
};
```

---

## Zaraz Custom Event Tracking

Call `zaraz.track()` from client-side JavaScript to send named events:

```typescript
// Injected inline script (rendered by the Worker or a static JS bundle)
declare const zaraz: {
  track: (event: string, properties?: Record<string, unknown>) => void;
};

// Track a button click with properties
document.getElementById("upgrade-btn")?.addEventListener("click", () => {
  zaraz.track("page_action", {
    action: "upgrade_clicked",
    plan: window.__cfBeacon?.data?.plan ?? "free",
    location: window.location.pathname,
  });
});

// Track SPA route changes
history.pushState = new Proxy(history.pushState, {
  apply(target, thisArg, args) {
    Reflect.apply(target, thisArg, args);
    zaraz.track("page_action", { action: "spa_navigate", path: args[2] });
  },
});
```

---

## Querying the Web Analytics GraphQL API

```bash
# Page view counts for the last 7 days, grouped by path
curl -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{
    "query": "query PageViews($accountTag: String!, $start: String!, $end: String!) { viewer { accounts(filter: { accountTag: $accountTag }) { webAnalyticsVisitorsAdaptiveGroups(filter: { date_geq: $start, date_leq: $end }, limit: 10, orderBy: [count_DESC]) { count dimensions { path } } } } }",
    "variables": {
      "accountTag": "'"${CF_ACCOUNT_ID}"'",
      "start": "2026-08-17",
      "end": "2026-08-24"
    }
  }'
```

```bash
# Compare CWA page views vs Analytics Engine funnel signup_start events
# Step 1: CWA total visitors
curl -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"query":"query { viewer { accounts(filter:{accountTag:\"'${CF_ACCOUNT_ID}'\"}) { webAnalyticsVisitorsAdaptiveGroups(limit:1) { count } } } }"}'

# Step 2: AE signup_start events (from workers-analytics-engine-funnel-tracking.md)
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: text/plain" \
  --data "SELECT COUNT(DISTINCT index1) AS signups FROM funnel_events WHERE blob1 = 'signup_start' AND timestamp > NOW() - INTERVAL '7' DAY"
```

---

## Anti-patterns
- **Injecting `__cfBeacon` after the beacon script tag** — the beacon reads `window.__cfBeacon` synchronously on load; setting it afterward has no effect.
- **Using `element.append()` on `<head>` instead of `element.before()` on `</head>`** — `append` adds content as the last child before the closing tag, but some browsers parse `<script>` tags injected into an open `<head>` differently; targeting the closing tag with `before` is more reliable.
- **Hardcoding the CWA token in source code** — store it in `[vars]` (non-secret) or `wrangler secret put CWA_TOKEN` for tokens you want to rotate without a redeploy.
- **Calling `zaraz.track()` before Zaraz has loaded** — wrap in a `zaraz` readiness check or push events to `window.zarazQueue = window.zarazQueue || []` then flush on load.

---

## Gotchas
- CWA does not track users behind Cloudflare's Bot Fight Mode as human visitors; bot-filtered traffic will be lower than raw server-side counts.
- The `spa: true` flag makes the beacon re-fire on history API navigation; disable it for MPA (multi-page) sites to avoid double-counting.
- GraphQL API rate limits are 1,200 requests per 5 minutes per token; cache responses in Workers KV for dashboard use cases.
- Custom `data-*` attributes on the beacon `<script>` are passed to the beacon but not automatically forwarded to the GraphQL API as filterable dimensions; use Zaraz properties for filterable custom data.
- HTMLRewriter handlers run streaming; do not `await` inside `element()` — all logic must be synchronous.

---

## Verification

```bash
# Deploy the injector Worker
wrangler deploy

# Fetch a page and check that the beacon script is present
curl -s https://beacon-injector.example.workers.dev/ | grep -A2 '__cfBeacon'
# Expected output includes:
# window.__cfBeacon = { token: 'YOUR_TOKEN', spa: true };
# <script defer src='https://static.cloudflare.com/beacon/beacon.min.js' ...></script>

# Open in browser, open DevTools → Network, filter by 'beacon'
# You should see a POST to https://cloudflareinsights.com/cdn-cgi/rum
```

---

## Related
- `workers-analytics-engine-funnel-tracking.md`
- `workers-opentelemetry-trace-export-d1.md`

---

## Sources
- Cloudflare Web Analytics — https://developers.cloudflare.com/analytics/web-analytics/
- HTMLRewriter API — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Cloudflare Zaraz — https://developers.cloudflare.com/zaraz/
- Analytics GraphQL API — https://developers.cloudflare.com/analytics/graphql-api/
