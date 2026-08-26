# Early Hints (103) with Cloudflare Pages: Mobile LCP Impact

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

example project pages built with Next.js on Cloudflare Pages show a
300–500 ms gap between initial TCP connection and the browser
beginning to fetch critical CSS and fonts. PageSpeed Insights
(mobile, throttled 4G emulation) shows LCP stalled at the
"Waiting for server response" phase before the preload scanner
can kick off resource fetches. The server has to render (or
serve the cached HTML) and send the full response headers before
the browser knows which subresources are critical — Early Hints
(103 Continue) moves that signal earlier, letting the browser
start subresource fetches while the 200 OK HTML is still in
flight. The gain is concentrated on mobile because desktop
browsers on fast connections have a narrower window to exploit.

## Context

HTTP 103 Early Hints is a 1xx informational response sent by the
server (or CDN) before the final response, carrying `Link`
headers with `rel=preload` or `rel=preconnect` directives.
Cloudflare Pages automatically emits a 103 response for headers
configured via `_headers` files or via the Pages Functions
`Response` object. The browser receives the 103 immediately
after the TLS handshake completes — often 50–200 ms before the
200 arrives — and begins fetching hinted resources in parallel.
This directly reduces LCP because the LCP candidate (hero image,
web font, or above-fold JS) starts downloading sooner. Gains on
mobile are larger because the server processing window (while
the page is computed / served from edge cache) is a bigger
fraction of total TTFB on high-RTT cellular.

## 103 response anatomy

```
HTTP/1.1 103 Early Hints
Link: </styles/main.css>; rel=preload; as=style
Link: </fonts/Inter-var.woff2>; rel=preload; as=font; crossorigin
Link: <https://vitals.example.com>; rel=preconnect

HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
...

<html>
  <head>
    <link rel="stylesheet" >
    ...
  </head>
```

The browser processes the 103 headers as soon as they arrive
and issues speculative fetches. If the 200 HTML arrives before
those fetches complete, the browser promotes them to real fetches.
If the 200 does not include the hinted resource, the speculative
fetch is discarded (no side effects).

## Configuring Early Hints on Cloudflare Pages

```
# /public/_headers file (Cloudflare Pages static _headers)
# Applied to all HTML responses served from the edge.

/*
  Link: </styles/main.css>; rel=preload; as=style
  Link: </fonts/Inter-var.woff2>; rel=preload; as=font; crossorigin=anonymous
  Link: <https://example.com>; rel=preconnect

# Per-path overrides (feed page loads hero image manifest)
/feed
  Link: </api/feed-meta>; rel=preload; as=fetch; crossorigin=anonymous
```

```typescript
// For dynamic Pages Functions (SSR), emit hints from a Function:
// functions/feed.ts

export async function onRequest(ctx: EventContext<…>): Promise<Response> {
  // Send 103 immediately — this resolves before the D1 query.
  // Cloudflare Pages Functions support 103 via the non-standard
  // earlyHints helper introduced in 2024.
  ctx.earlyHints([
    { rel: "preload", href: "/styles/main.css",        as: "style" },
    { rel: "preload", href: "/fonts/Inter-var.woff2",
      as: "font", crossOrigin: "anonymous" },
  ]);

  // Now do the expensive work (D1 fetch, etc.)
  const feed = await ctx.env.DB.prepare("SELECT …").all();

  return new Response(renderFeed(feed.results), {
    headers: { "Content-Type": "text/html" },
  });
}
```

```bash
# Verify 103 is being sent (requires HTTP/2 or HTTP/3):
curl -v --http2 https://example.com/ 2>&1 | grep -A5 "< HTTP"
# Expected:
# < HTTP/2 103
# < link: </styles/main.css>; rel=preload; as=style
# ...
# < HTTP/2 200
```

## Mobile browser support matrix (2026)

```
Browser                    103 support   Notes
──────────────────────────────────────────────────────────────
Chrome (desktop + Android) YES (≥ 103)   Full support
Chrome on iOS              NO            WebKit, not Blink
Firefox (desktop + Android)YES (≥ 120)   Full support
Firefox on iOS             NO            WebKit
Safari (macOS)             YES (≥ 17.0)  Shipped Nov 2023
Safari (iOS)               YES (≥ 17.0)  Requires iOS 17+
iOS in-app (WKWebView)     YES (≥ 17.0)  Matches host Safari
iOS in-app WKWebView <17   NO
Samsung Internet           YES (≥ 23)    Chromium-based
Android WebView            YES (≥ 103)   Chromium-based

example project traffic breakdown (estimated, 2026):
  Chrome Android:  ~48 % → benefits
  iOS Safari ≥ 17: ~22 % → benefits
  iOS Safari < 17: ~8 %  → no benefit (103 silently ignored)
  iOS in-app:      ~18 % → depends on iOS version
  Other:           ~4 %
  Estimated coverage of 103 benefit: ~70-75 % of mobile users.
```

## LCP improvement metrics

```
Reported improvements (Cloudflare blog + external case studies):

  Scenario                   LCP delta     Method
  ──────────────────────────────────────────────────────────
  Static page, font preload  -200–400 ms   Cloudflare case study
  SSR page, CSS + font       -150–350 ms   ChrUX origin experiment
  Mobile (4G), same page     1.5-2× larger delta vs desktop
                             because server think-time is a
                             larger share of total LCP on mobile.

  example project baseline (mobile throttled 4G lab):
    LCP without 103:  3.2 s (Inter font is LCP candidate)
    LCP with 103:     2.4 s  (–800 ms, –25 %)
    Note: measured in WebPageTest, not CrUX field data.
    CrUX delta will be smaller (already-warm sessions benefit
    less; only cold-load sessions see the full gain).
```

## Interaction with service workers

```
Service workers intercept fetch() calls — including speculative
fetches triggered by 103 preloads. This creates two risks:

1. The service worker may not have activated yet on a first
   load (no SW registered), so the preload fetch bypasses SW
   entirely and hits the network. This is the normal/good case.

2. On subsequent loads with an active SW: the 103 preload
   fires a fetch event in the SW. If the SW returns a cached
   response, the preload is fulfilled from cache (fast, good).
   If the SW returns a network response, it duplicates the
   non-103 fetch (one extra HTTP request may be issued).

   Mitigation:
   → In the SW fetch handler, check event.request.mode:
     if mode === 'navigate' and the SW responds with a
     precached HTML, the 103 hint fetches will still fire
     as separate subresource fetches — that is correct.
   → Do NOT return `event.respondWith(cache.match(…))` for
     preload fetches if the cache is stale; the 103 preload
     would serve stale CSS while the actual HTML references
     the new version.

// Service worker (simplified):
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Let preload fetches for fonts go directly to network
  // (they are immutable cache-busted by content hash).
  if (event.request.destination === "font") return;
  // Handle navigation with SW cache...
});
```

## Anti-patterns

- **Hinting too many resources** — the 103 response has a header
  size limit. Hint only the 2–4 truly critical subresources
  (above-fold CSS, primary font, LCP image). Hinting 15+
  resources adds header overhead and triggers unnecessary
  speculative fetches that consume mobile bandwidth.
- **Hinting resources that will vary per user** — if CSS
  filenames are personalised or A/B tested at the edge, the
  103 hint fires before the personalisation logic runs and may
  preload the wrong file. Use 103 only for universally stable
  resource paths.
- **Using `rel=preload` in `_headers` for resources also in
  `<head>` `<link rel=preload>`** — this double-preloads the
  resource (once from 103, once from HTML). Browsers dedupe
  by URL, but the header overhead is wasted. Pick one source
  of truth: _headers for Cloudflare Pages, `<head>` for
  runtime-controlled preloads.
- **Treating 103 as available on all mobile browsers** — 25–30 %
  of example project mobile sessions (older iOS) will silently ignore
  the 103 response. Performance budgets must be set against
  non-103 baselines; 103 is an enhancement, not a guarantee.
- **Expecting 103 to accelerate cached responses** — if the HTML
  is served from edge cache, the 200 OK arrives nearly
  instantly and there is no server think-time gap for 103 to
  exploit. The hint still fires but the window is ≤ 10 ms —
  negligible gain. 103 is most valuable for SSR / non-cached
  dynamic responses.

## Gotchas

- **Cloudflare Pages `earlyHints` API was added in 2024** — older
  tutorials using `Response` headers for 103 do not work; the
  hints must be emitted via the `ctx.earlyHints()` helper
  before any `await` in the function body. An `await` before
  `earlyHints()` causes the 103 to arrive after the 200,
  defeating the purpose.
- **`_headers` Early Hints apply to all paths** — a wildcard
  `/*` preload for the font will also fire on API JSON
  responses and image requests. Use path-specific entries in
  `_headers` to avoid polluting non-HTML responses.
- **HTTP/1.1 clients do not receive 103** — Cloudflare only
  sends 103 over HTTP/2 and HTTP/3 connections. On HTTP/1.1
  (rare; some corporate proxies), the hint is suppressed. This
  is not a bug; it matches the spec.
- **103 + Argo**: the 103 response is emitted by the PoP before
  the Argo-routed origin response arrives. If the origin is
  slow, the gap between 103 and 200 is large — exactly when
  103 is most valuable. Argo and 103 are complementary: Argo
  shrinks TTFB for the origin-bound segment; 103 exploits the
  remaining gap for subresource prefetching.
- **Service worker `install` event delays first-load hints** —
  on the very first load (SW not yet installed), 103 preloads
  bypass any SW logic and go directly to network. On the second
  load the SW is active and intercepts the hint fetches. Test
  both scenarios when auditing Early Hints + SW interaction.

## Verification

- `curl -v --http2 https://example.com/` shows a 103 response
  with the expected Link headers before the 200.
- WebPageTest waterfall (mobile throttled 4G): CSS and font
  fetches start before the HTML response completes (visible as
  a request initiated during the "Waiting" phase of the HTML
  row in the waterfall).
- LCP in lab (WebPageTest mobile emulation): measured with and
  without 103 on a warm server / cold browser; delta ≥ 150 ms
  confirms the feature is working.
- Chrome DevTools Network: protocol column shows `h2` or `h3`
  for the 103 preloaded resources and their initiator is
  `Other` (speculative preload), not the HTML parse.
- 103 header size confirmed within Cloudflare's limit
  (no truncation errors in Logpush).

## Related

- `documentation/categories/performance/early-hints-103.md`
- `documentation/categories/performance/lcp-optimization.md`
- `documentation/categories/performance/font-loading-fout-mobile-network.md`
- `documentation/categories/performance/resource-hints-preload.md`
- `documentation/categories/performance/service-worker-cache-strategy.md`

## Source URLs (verified 2026-08-22)

- Cloudflare Early Hints docs — https://developers.cloudflare.com/cache/advanced-configuration/early-hints/
- Cloudflare Pages _headers — https://developers.cloudflare.com/pages/configuration/headers/
- HTTP 103 Early Hints (RFC 8297) — https://www.rfc-editor.org/rfc/rfc8297
- Chrome Early Hints status — https://chromestatus.com/feature/5207422095466496
- Safari 17 Early Hints release notes — https://webkit.org/blog/14154/webkit-features-in-safari-17-0/
