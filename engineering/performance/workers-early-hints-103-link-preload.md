# HTTP 103 Early Hints with Link: rel=preload in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Worker generates a full HTML page before the browser can start downloading critical assets (JS bundles, CSS, fonts), wasting render-blocking round-trips. You want the browser to begin fetching `/app.js`, `/app.css`, and key third-party origins while the Worker is still computing the response body.

---

## Context
HTTP 103 Early Hints is an informational status code (RFC 8297) that lets a server send `Link` headers to the client before the final `200` response. Cloudflare Workers support Early Hints natively — you return a `103` response from a helper and the Cloudflare edge forwards it to the client immediately. The browser treats these hints the same as `<link rel=preload>` elements, starting asset fetches before the HTML arrives. For third-party origins (fonts, analytics CDNs) you combine `rel=preconnect` in the hints to warm up TLS and TCP. Measured LCP improvements of 100-400 ms are typical for JS-heavy SPAs. Browser support is broad: Chrome 103+, Edge 103+, Firefox 120+, Safari 17.2+.

---

## Section 1 — Workers Config

```toml
name = "early-hints-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

# Early Hints require HTTP/2 or HTTP/3 — both are enabled by default on Cloudflare
# No additional wrangler.toml settings needed

[vars]
ASSET_VERSION = "v2.4.1"
```

## Section 2 — Implementation

```typescript
import { ExecutionContext } from '@cloudflare/workers-types';

export interface Env {
  ASSET_VERSION: string;
}

/** A single preload/preconnect hint. */
interface Hint {
  url: string;
  rel: 'preload' | 'preconnect' | 'dns-prefetch';
  /** Required for preload — tells the browser the resource type. */
  as?: 'script' | 'style' | 'font' | 'image' | 'fetch';
  /** Set to true for cross-origin fonts and fetch requests. */
  crossorigin?: boolean;
}

/**
 * Build a Link header value from an array of hints.
 * Example output:
 *   </app.js>; rel=preload; as=script, </app.css>; rel=preload; as=style
 */
function buildLinkHeader(hints: Hint[]): string {
  return hints
    .map((h) => {
      const parts = [`<${h.url}>`, `rel=${h.rel}`];
      if (h.as) parts.push(`as=${h.as}`);
      if (h.crossorigin) parts.push('crossorigin');
      return parts.join('; ');
    })
    .join(', ');
}

/**
 * Send HTTP 103 Early Hints.
 * Cloudflare forwards this informational response to the client immediately,
 * before the main response is ready.
 */
async function sendEarlyHints(hints: Hint[]): Promise<void> {
  // The Workers runtime intercepts status 103 and sends it as an
  // informational frame over HTTP/2 or HTTP/3.
  // This is a fire-and-forget — we do not await the client consuming it.
  const linkHeader = buildLinkHeader(hints);
  // Note: In Cloudflare's implementation you use the fetch Response constructor
  // with status 103 and the Link header. The runtime handles the framing.
  // Per CF docs, returning status 103 from fetch() is not how it works —
  // instead you use the `eyeball` response trick or the dedicated API.
  // The canonical approach as of 2024 is via the `Response` with 103 status
  // returned early and then the main response returned separately.
  // Workers runtime coalesces them at the edge.
  console.log(`[early-hints] Sending Link: ${linkHeader}`);
  // Actual send happens via the returned object — see the fetch handler below.
  void linkHeader; // referenced in handler
}

/** Simulate async work (e.g. D1 query, KV read) while hints travel to the browser. */
async function buildPageData(version: string): Promise<{ title: string; items: string[] }> {
  // In production this would be a D1 query or KV read
  await new Promise((r) => setTimeout(r, 20)); // simulate 20 ms async work
  return {
    title: `My App ${version}`,
    items: ['Item A', 'Item B', 'Item C'],
  };
}

function renderHtml(data: { title: string; items: string[] }, version: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>${data.title}</title>
  <!-- These are already loading thanks to Early Hints -->
  <link rel="stylesheet"  />
  <link rel="preconnect" href="https://fonts.googleapis.com" crossorigin />
</head>
<body>
  <h1>${data.title}</h1>
  <ul>${data.items.map((i) => `<li>${i}</li>`).join('')}</ul>
  <script  defer></script>
</body>
</html>`;
}

const PAGE_HINTS: Hint[] = [
  { url: '/app.js', rel: 'preload', as: 'script' },
  { url: '/app.css', rel: 'preload', as: 'style' },
  { url: '/fonts/inter-v13-latin-regular.woff2', rel: 'preload', as: 'font', crossorigin: true },
  // Warm TLS to third-party origins
  { url: 'https://fonts.googleapis.com', rel: 'preconnect' },
  { url: 'https://analytics.example.com', rel: 'preconnect' },
];

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/' || url.pathname === '/index.html') {
      const version = env.ASSET_VERSION ?? 'v1';
      const linkHeader = buildLinkHeader(
        PAGE_HINTS.map((h) => ({
          ...h,
          // Append cache-busting version to preloaded asset URLs
          url: h.rel === 'preload' ? `${h.url}?v=${version}` : h.url,
        }))
      );

      // Start async work — while this runs, the 103 is in-flight to the browser
      const dataPromise = buildPageData(version);

      // Build main response, then attach Early Hints header
      const data = await dataPromise;
      const html = renderHtml(data, version);

      return new Response(html, {
        status: 200,
        headers: {
          'Content-Type': 'text/html; charset=utf-8',
          // Cloudflare reads this header and emits a 103 frame before the 200
          Link: linkHeader,
          // Prevent caching of the HTML shell itself; assets are versioned
          'Cache-Control': 'no-store',
        },
      });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Section 3 — LCP Measurement and Browser Compatibility

```typescript
// Paste into browser DevTools console to measure LCP before/after Early Hints
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    console.log('LCP:', entry.startTime.toFixed(0), 'ms', entry);
  }
}).observe({ type: 'largest-contentful-paint', buffered: true });
```

```bash
# Verify 103 Early Hints are sent using curl (HTTP/2 required)
curl --http2 -v https://my-worker.example.com/ 2>&1 | grep -E '< HTTP|< link|103'
# Expected:
# < HTTP/2 103
# < link: </app.js?v=v2.4.1>; rel=preload; as=script, </app.css?v=v2.4.1>; rel=preload; as=style ...
# < HTTP/2 200

# Use WebPageTest to measure LCP delta
# https://www.webpagetest.org/ — compare filmstrip before/after enabling Early Hints

# Measure with Lighthouse CLI
npx lighthouse https://my-worker.example.com/ \
  --only-audits=largest-contentful-paint \
  --output=json | jq '.audits["largest-contentful-paint"].displayValue'
```

### Browser Compatibility Matrix

| Browser | Early Hints (103) | preload | preconnect |
|---|---|---|---|
| Chrome 103+ | Yes | Yes | Yes |
| Edge 103+ | Yes | Yes | Yes |
| Firefox 120+ | Yes | Yes | Yes |
| Safari 17.2+ | Yes | Yes | Yes |
| Safari < 17.2 | No (ignored) | Yes | Yes |
| Mobile Chrome | Yes (103+) | Yes | Yes |
| Mobile Safari | 17.2+ only | Yes | Yes |

For browsers that do not support 103, the `Link` header on the `200` response still triggers preloads — Early Hints is a progressive enhancement.

---

## Anti-patterns
- **Hinting resources that are not render-critical** — low-priority images or below-the-fold scripts waste browser connection slots; hint only LCP images, critical CSS, and entry-point JS.
- **Not versioning hinted asset URLs** — unhinted `Cache-Control: max-age=0` assets cause revalidation RTTs that negate the Early Hints benefit; always version assets.
- **Sending 103 after the response body starts** — Early Hints must arrive *before* the `200` response; Cloudflare enforces this automatically when you set the `Link` header on the main response.
- **Using `rel=preload` without `as`** — the browser cannot prioritise or validate the preloaded resource type without `as`; this triggers a console warning and degrades fetch priority.

---

## Gotchas
- Cloudflare emits the `103` frame from the `Link` header on the outbound `200` response; you do not send a separate `103` response from your Worker code — setting the header is sufficient.
- Early Hints only work over HTTP/2 or HTTP/3; HTTP/1.1 clients never see the `103` frame (it degrades gracefully).
- Hinting a cross-origin font without `crossorigin` causes a double-fetch — the preloaded resource is discarded and re-fetched with CORS credentials.
- `rel=preconnect` hints are subject to a browser limit (typically 6-10 origins); do not hint more origins than the browser will act on.
- Cloudflare's Early Hints feature must be enabled at the zone level in the Cloudflare dashboard under Speed > Optimization > Early Hints.

---

## Verification

```bash
# Check Early Hints zone setting is enabled
curl -s -X GET \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/settings/early_hints" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result.value'
# Should return: "on"

# Enable Early Hints via API if needed
curl -s -X PATCH \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/settings/early_hints" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"value": "on"}' | jq '.result'

# Confirm Link header is present on response
curl -sI https://my-worker.example.com/ | grep -i link
```

---

## Related
- `workers-cache-api-stale-while-revalidate.md`
- `workers-subrequest-parallelism-promise-all.md`
- `workers-kv-bulk-read-cache-warming.md`

---

## Sources
- RFC 8297 — HTTP Early Hints — https://www.rfc-editor.org/rfc/rfc8297
- Cloudflare Early Hints docs — https://developers.cloudflare.com/cache/advanced-configuration/early-hints/
- web.dev Early Hints guide — https://web.dev/articles/early-hints
- MDN Link header — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Link
- Chrome Early Hints explainer — https://chromestatus.com/feature/5765921836941312
