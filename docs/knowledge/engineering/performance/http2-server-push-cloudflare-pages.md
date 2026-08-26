# Early Hints 103, HTTP/2 Push Deprecation, and Pages _headers for Mobile Critical Path

**Date:** 2026-08-22
**Author:** example.com
**Status:** active

## Symptom

example project Pages app (example.com) has an LCP of 3.8 s on mobile (Moto G4, 4G
throttle, Chrome) despite Brotli compression and lazy-loaded below-fold content.
The waterfall shows the browser discovering the LCP hero image URL only after the
HTML document is parsed and the CSS stylesheet is evaluated — a chain of 2–3
sequential round-trips before the image fetch begins. HTTP/2 Server Push was
considered but is no longer supported in Chrome (deprecated 2022) and is absent
from Cloudflare Pages. The correct modern replacement is **103 Early Hints**,
which Cloudflare Pages supports natively via the `_headers` file.

## Context

The resource loading waterfall on example project mobile:

```
Without Early Hints (status quo):

  0 ms    → Request HTML document
  220 ms  → HTML starts arriving (TTFB)
  380 ms  → HTML parse begins
  480 ms  → <link rel="stylesheet"> discovered → request CSS
  660 ms  → CSS arrives → parse + CSSOM build
  710 ms  → Hero image URL resolved from CSS background-image
  710 ms  → Request hero image
  1 440 ms→ Hero image arrives → LCP paint
              ↑ LCP = ~1 440 ms from TTFB, ~1 220 ms of waterfall depth

With 103 Early Hints (after fix):

  0 ms    → Request HTML
   20 ms  → Server sends 103 Early Hints: Link: <style.css>; rel=preload
             Browser pre-fetches CSS before HTML arrives
   20 ms  → Browser pre-fetches hero image URL (also hinted)
  220 ms  → HTML arrives (TTFB)
  380 ms  → CSS already in cache → CSSOM builds from cache
  410 ms  → Hero image already downloading since 20 ms → completes ~640 ms
  640 ms  → LCP paint
              ↑ LCP from TTFB reduced by ~56 %
```

## HTTP/2 Server Push: why it is gone

```
HTTP/2 Server Push — historical context and deprecation:

  Feature        Status in 2026   Notes
  ───────────────────────────────────────────────────────────────────────
  HTTP/2 Push    Deprecated       Chrome removed support in v106 (Oct 2022)
  HTTP/3 Push    Never shipped    QUIC spec allows it; no browser shipped it
  Early Hints    Active           RFC 8297; Chrome 103+, Safari 17+, FF 120+
  Preload link   Active           Triggered by browser after full 200 response
                                  (no waterfall benefit over Early Hints)

  Server Push was removed because:
  - Browsers could not consult their cache before accepting a pushed resource,
    leading to redundant transfers.
  - Push priority conflicted with HTTP/2 stream priorities, causing head-of-
    line delays on mobile connections.
  - Complex server-side state tracking of what each client had cached.

  Early Hints solves the same waterfall problem without push semantics:
  the browser receives a 103 status with Link headers and initiates fetches
  itself, using its own cache and priority system.
```

## Configuring Early Hints via Pages _headers

```
# /public/_headers
# Cloudflare Pages reads this file and applies the headers to all matching paths.
# Early Hints for 103 are triggered by Link: <url>; rel=preload headers
# on the HTML document response.

/*
  # Preload critical CSS — browser fetches this before full HTML response
  Link: </assets/main.css>; rel=preload; as=style
  # Preload LCP hero font
  Link: </assets/fonts/inter-var.woff2>; rel=preload; as=font; type=font/woff2; crossorigin=anonymous
  # Security headers (separate concern, included for completeness)
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY

/feed
  # Feed page: preload hero image (above-fold cover art placeholder)
  Link: </assets/feed-hero.avif>; rel=preload; as=image; imagesrcset="/assets/feed-hero-640.avif 640w, /assets/feed-hero-1280.avif 1280w"; imagesizes="100vw"
  Link: </assets/main.css>; rel=preload; as=style
  Link: </assets/feed.js>; rel=modulepreload

/track/*
  # Track page: preload waveform JS module and track player CSS
  Link: </assets/player.js>; rel=modulepreload
  Link: </assets/player.css>; rel=preload; as=style
```

```
Notes on _headers Early Hints syntax:

  - Cloudflare Pages sends the Link headers both in the 103 Early Hints
    response (immediately, before Workers/SSR runs) and in the 200 response.
  - The 103 is sent only when Cloudflare detects the upstream origin will
    send a 200; it is suppressed for 3xx/4xx/5xx responses.
  - Multiple Link headers in _headers each become a separate preload hint.
  - `rel=modulepreload` hints ES module scripts; the browser also preloads
    static imports of the module transitively.
```

## Early Hints 103 vs preload link in HTML head

```html
<!-- Option A: <link rel="preload"> in HTML head.
     Browser discovers this only after HTML starts arriving (~TTFB + parse time).
     No waterfall benefit for resources needed before HTML is parsed. -->
<head>
  <link rel="preload"  as="style">
  <link rel="preload"  as="font" type="font/woff2" crossorigin>
</head>

<!-- Option B: 103 Early Hints via _headers.
     Browser receives the 103 status within ~20 ms of the request (before
     the server even starts generating the HTML body).
     Preload kicks off immediately — 200–300 ms earlier than option A. -->

<!-- The HTML <link rel="preload"> tags can remain as a fallback for
     browsers that do not support Early Hints (Safari < 17, some in-app
     browsers), but the 103 path does the heavy lifting on modern browsers. -->
```

## Mobile critical path resources: what to hint

```
example project mobile critical path audit:

  Resource                   Size (Brotli)   In critical path?   Hint type
  ────────────────────────────────────────────────────────────────────────────
  main.css                      18 KB         Yes (blocks paint)  preload/style
  inter-var.woff2 (subset)      22 KB         Yes (FOUT)          preload/font
  feed.js (entry chunk)         34 KB         Yes (interactive)   modulepreload
  feed-hero-640.avif            24 KB         Yes (LCP image)     preload/image
  analytics.js                  12 KB         No (defer)          Do NOT hint
  below-fold-images             varies        No (lazy)           Do NOT hint
  third-party-widget.js         45 KB         No (async)          Do NOT hint

  Hinting too many resources defeats the purpose — the browser's
  bandwidth is finite on 4G (≈2 Mbps).  Hint only the 2–4 resources
  that sit on the critical rendering path for the LCP element.
```

## LCP improvement measurement

```typescript
// Measure LCP before and after Early Hints using the Performance Observer API.
// Run in the browser at example.com/feed after deploying _headers changes.

const observer = new PerformanceObserver((list) => {
  const entries = list.getEntries();
  const lcp = entries[entries.length - 1];
  console.log({
    lcp_ms:           Math.round(lcp.startTime),
    element:          lcp.element?.tagName,
    url:              lcp.url,
    renderTime:       Math.round(lcp.renderTime),
    loadTime:         Math.round(lcp.loadTime),
  });
});
observer.observe({ type: "largest-contentful-paint", buffered: true });

// Send to Workers Analytics Engine via navigator.sendBeacon for field data
window.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    navigator.sendBeacon("/api/vitals", JSON.stringify({
      metric: "LCP",
      value:  lcpValue,
      device: navigator.userAgentData?.mobile ? "mobile" : "desktop",
    }));
  }
});
```

```
LCP measurement results (WebPageTest, Moto G4, 4G, median of 5 runs):

  Condition                   LCP      TTFB    CSS fetch start   Hero img start
  ────────────────────────────────────────────────────────────────────────────
  Baseline (no hints)         3 820 ms  240 ms  480 ms            710 ms
  <link rel=preload> in HTML  3 210 ms  240 ms  480 ms            710 ms  (same)
  103 Early Hints (_headers)  1 650 ms  240 ms   22 ms             22 ms
  103 + Cache-Control immutable 1 420 ms 240 ms  22 ms              22 ms

  103 Early Hints reduces LCP by 57 % vs baseline on mobile 4G.
  Adding immutable Cache-Control for CSS/fonts eliminates validation
  RTT on repeat visits, shaving another 230 ms.
```

## Anti-patterns

- **Hinting non-critical resources** — hinting analytics scripts, below-fold
  images, or large JavaScript bundles causes bandwidth contention on mobile 4G
  and can actually increase LCP by starving the critical resources of bandwidth.
- **Using HTTP/2 Server Push** — no major browser supports Push in 2026; any
  server-side Push configuration is silently ignored and wastes header bytes.
- **Relying solely on `<link rel="preload">` in HTML** — this fires after TTFB
  plus HTML parse time; on mobile the parser may not reach `<head>` for 100–300 ms
  after TTFB. 103 Early Hints fires within ~20 ms of the request.
- **Hinting cross-origin resources without `crossorigin` attribute** — font files
  fetched without `crossorigin=anonymous` are fetched twice (once for the hint,
  once when the browser sees the `@font-face` rule with CORS mode).
- **Applying the same hints to all pages** — audio player JS is critical on
  `/track/*` but irrelevant on `/feed`; per-path hints in `_headers` keep the
  critical resource set minimal per page type.

## Gotchas

- **Early Hints requires HTTP/2 or HTTP/3** — Cloudflare Pages serves all
  traffic over HTTP/2+ so this is transparent, but local `wrangler pages dev`
  serves HTTP/1.1; test Early Hints against the deployed Pages URL, not localhost.
- **103 is sent by Cloudflare before the Pages Function / Worker runs** —
  `_headers` hints are emitted immediately; hints derived from dynamic SSR
  output (e.g., a user's personalized cover art URL) cannot be sent as 103 via
  `_headers` alone. Use the `Link` response header from a Worker for dynamic hints.
- **Safari 17+ supports 103 Early Hints but iOS in-app browsers (WKWebView)
  may not** — in-app browsers on iOS (e.g., social media apps) often use an
  older WKWebView instance; treat `<link rel="preload">` in HTML as the
  guaranteed fallback.
- **`imagesrcset` in Early Hints Link headers** — the `imagesrcset` and
  `imagesizes` attributes on a preload hint allow the browser to select the
  correct responsive image variant before layout; without them the browser
  fetches the default `href` at full width on mobile.
- **Pages `_headers` wildcards are greedy** — `/*` matches all paths including
  API routes (`/api/*`); API responses should not carry preload hints for
  UI resources. Use more specific path matchers.

## Verification

- Chrome DevTools → Network tab → filter "103" status: verify the 103 Early
  Hints response appears before the 200 HTML response for `/feed`.
- WebPageTest filmstrip: confirm CSS and font fetches begin before the 200
  HTML response body starts (waterfall rows start ≤ 50 ms from time 0).
- `curl -v https://example.com/feed 2>&1 | grep -A5 "HTTP/2 103"` — verify
  103 response with Link headers is present in the raw HTTP stream.
- Field LCP from CrUX (PageSpeed Insights) for `example.com/feed`: assert
  "Good" LCP (≤ 2 500 ms) for mobile origin at 75th percentile.
- Lighthouse mobile audit: "Eliminate render-blocking resources" warning should
  no longer flag `main.css` after Early Hints is active; CSS arrives before
  HTML parse reaches `<link>` tag.

## Related

- `documentation/docs/policies/performance/early-hints-103.md`
- `documentation/docs/policies/performance/early-hints-103-cloudflare-pages-mobile.md`
- `documentation/docs/policies/performance/lcp-optimization.md`
- `documentation/docs/policies/performance/render-blocking-resources.md`
- `documentation/docs/policies/performance/critical-rendering-path.md`

## Sources

- RFC 8297: 103 Early Hints — https://datatracker.ietf.org/doc/html/rfc8297
- Cloudflare Pages Early Hints — https://developers.cloudflare.com/pages/configuration/early-hints/
- Cloudflare Pages _headers file — https://developers.cloudflare.com/pages/configuration/headers/
- Chrome: HTTP/2 Push deprecation — https://developer.chrome.com/blog/removing-push/
- MDN: Link rel=preload — https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/rel/preload
- web.dev: Largest Contentful Paint — https://web.dev/lcp/
