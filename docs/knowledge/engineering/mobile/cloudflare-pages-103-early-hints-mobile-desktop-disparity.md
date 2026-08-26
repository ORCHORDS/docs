# Cloudflare Pages 103 Early Hints and HTML Delivery Disparity: Mobile vs Desktop

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

The example project Next.js app (example.com) loads measurably faster on desktop Chrome than on iOS
Safari or Android Chrome. Waterfall traces show desktop clients receiving preloaded font and
JS chunk assets before the main HTML document body arrives, while mobile clients show a flat
stall with nothing loading until the full 200 response completes. Lighthouse mobile scores are
15–25 points lower than desktop despite identical HTML output.

## Context

Cloudflare Pages has supported HTTP 103 Early Hints since 2022. The feature lets the edge send
a provisional `103 Early Hints` response with `Link: preload` headers before the origin (or
Worker) finishes generating the full response. Desktop Chrome has supported 103 since version
103 (2022); Firefox since 120 (2023). iOS Safari gained 103 support only in Safari 17.4 / iOS
17.4 (March 2024) and the implementation remains incomplete — it parses `preload` hints but
silently drops `preconnect` and `dns-prefetch` hints in WebView contexts. Android WebView
(Chromium-based) did not enable 103 processing until Chromium 117, which shipped in Android
WebView 117 (September 2023), meaning devices still on WebView 114 (Android 9–10 stranded
devices) receive the hint frame but ignore it entirely.

For the example project React Native app using a WebView (Capacitor / Expo Web), the in-app browser
never processes 103 at all — all embedded runtimes (WKWebView, Android WebView in Capacitor)
receive 103 frames but the JavaScript bridge is not wired to act on them, so the preloads are
lost. Native fetch calls from React Native itself (Hermes / JSI) do not see 103 at all because
the HTTP client (Fetch API over the native networking layer) strips informational responses
before surfacing to JS.

## Section 1 — How Cloudflare Pages Emits 103

Cloudflare Pages automatically generates `103 Early Hints` from any `Link` header your Worker or
`_headers` file places on the response. The edge intercepts the outbound headers, issues the 103
frame to the client, then buffers the remaining origin response while the client starts fetching
the hinted assets in parallel.

```
# example.com public/_headers
/
  Link: </fonts/inter-var.woff2>; rel=preload; as=font; crossorigin=anonymous
  Link: </_next/static/chunks/main.js>; rel=preload; as=script

/feed
  Link: </api/feed?hydration=1>; rel=prefetch
  Link: </_next/static/chunks/feed.js>; rel=preload; as=script
```

The edge converts each `Link` header that carries `rel=preload` or `rel=preconnect` into a
103 frame sent before the HTML body. Only `preload` and `preconnect` trigger 103; `prefetch`
is passed through as a standard header in the 200 but does not generate a 103.

## Section 2 — Mobile Client Behaviour Matrix

| Client                              | 103 Processed | preload | preconnect | Notes                                    |
|-------------------------------------|---------------|---------|------------|------------------------------------------|
| Desktop Chrome 103+                 | Yes           | Yes     | Yes        | Full support                             |
| Desktop Firefox 120+                | Yes           | Yes     | Partial    | preconnect hints dropped silently        |
| Desktop Safari 17.4+                | Yes           | Yes     | No         | preconnect ignored                       |
| iOS Safari 17.4+ (native)           | Yes           | Yes     | No         | preconnect dropped, font crossorigin OK  |
| iOS Safari < 17.4                   | No            | N/A     | N/A        | 103 frame ignored entirely               |
| iOS WKWebView (Capacitor/RN)        | No            | N/A     | N/A        | WKWebView never surfaced 103 to JS       |
| Android Chrome 117+                 | Yes           | Yes     | Yes        | Full support on Android Chrome           |
| Android WebView 117+                | Partial       | Yes     | No         | preconnect stripped by WebView layer     |
| Android WebView < 117               | No            | N/A     | N/A        | Chromium engine ignores 103              |
| React Native Hermes (fetch)         | No            | N/A     | N/A        | Informational frames stripped pre-JS     |
| React Native Capacitor WebView      | No            | N/A     | N/A        | Same as platform WebView + bridge gap    |

## Section 3 — Next.js Server Component Impact

Next.js 14+ App Router uses `generateMetadata` and the internal `headers()` API to attach Link
preload headers. When running on Cloudflare Pages via the `@cloudflare/next-on-pages` adapter,
these headers are forwarded to the edge correctly. The problem is that Next.js may emit them
only for the HTML document route — not for API routes that return JSON. For the feed route
this means:

```typescript
// app/feed/page.tsx — headers here DO produce 103 for desktop
import { headers } from 'next/headers';

export async function generateMetadata() {
  // Cloudflare Pages reads these and emits 103 preload
  return {
    other: {
      'Link': '</_next/static/chunks/feed.js>; rel=preload; as=script',
    },
  };
}
```

```typescript
// app/api/feed/route.ts — headers here DO NOT produce 103
// because the client is a React Native fetch, not a browser navigation
export async function GET(request: Request) {
  return new Response(JSON.stringify(data), {
    headers: {
      // This Link header will NOT generate a 103 because the client
      // is identified as a non-browser UA by Cloudflare's UA parser
      'Link': '</api/feed?page=2>; rel=prefetch',
    },
  });
}
```

Cloudflare's edge only emits 103 for requests where the User-Agent matches a known browser UA
pattern. React Native's default UA (`okhttp/4.x`, `CFNetwork/x`, or a custom UA set by Expo)
is not in that pattern list, so the edge skips 103 emission entirely for native API calls.

## Section 4 — Adaptive Preload Strategy for Mobile

Since 103 Early Hints cannot be relied on for mobile, the correct strategy is to layer
approaches by context:

**For the Next.js web app (mobile browsers):**

```typescript
// middleware.ts — detect mobile and adjust hint aggressiveness
import { NextRequest, NextResponse } from 'next/server';

export function middleware(request: NextRequest) {
  const ua = request.headers.get('user-agent') ?? '';
  const cfDeviceType = request.headers.get('cf-device-type') ?? 'desktop';
  const isMobile = cfDeviceType === 'mobile' || cfDeviceType === 'tablet';

  const response = NextResponse.next();

  if (!isMobile) {
    // Desktop: rely on 103 Early Hints via Link headers
    response.headers.set(
      'Link',
      [
        '</_next/static/chunks/main.js>; rel=preload; as=script',
        '</_next/static/chunks/feed.js>; rel=preload; as=script',
        '</fonts/inter-var.woff2>; rel=preload; as=font; crossorigin=anonymous',
        'https://fonts.googleapis.com; rel=preconnect',
      ].join(', ')
    );
  } else {
    // Mobile: only preload critical above-fold font — preconnect dropped by mobile browsers
    // Avoid over-hinting on mobile to prevent contention on constrained connections
    response.headers.set(
      'Link',
      '</fonts/inter-var.woff2>; rel=preload; as=font; crossorigin=anonymous'
    );
  }

  return response;
}
```

**For the React Native app (no 103):**

```typescript
// Prefetch next page data explicitly before navigation
import { useEffect } from 'react';
import { useNavigation } from '@react-navigation/native';

export function usePrefetchFeed(nextCursor: string | null) {
  useEffect(() => {
    if (!nextCursor) return;
    // Manual prefetch — no 103, no browser hint, just an early fetch
    const controller = new AbortController();
    fetch(`https://api.example.com/feed?cursor=${nextCursor}`, {
      signal: controller.signal,
      headers: { 'Accept': 'application/json' },
    })
      .then(r => r.json())
      .then(data => {
        // Store in React Query / SWR cache so it's instant on navigation
        queryClient.setQueryData(['feed', nextCursor], data);
      })
      .catch(() => {}); // prefetch failure is silent
    return () => controller.abort();
  }, [nextCursor]);
}
```

## Anti-patterns

- **Relying on `preconnect` hints on mobile**: Mobile browsers drop them silently. Always test
  with Chrome DevTools network throttling emulating a mobile UA — the `103` frame will appear
  in the waterfall but `preconnect` hints will show no effect.
- **Emitting many preload hints**: On cellular, parallel preload requests contend for the same
  narrow TCP window. Sending 8 `preload` hints on a 2G link is worse than sending 2 — the
  browser opens multiple connections that each slow the others down. Limit to 2–3 critical
  resources on mobile.
- **Assuming WebView == browser**: WKWebView (Capacitor, React Native WebView) does not process
  103 frames. Any performance budget built on 103 preloads must have a fallback for the WebView
  context.
- **Using `rel=prefetch` in `_headers` expecting it to generate 103**: It won't. Only `preload`
  and `preconnect` trigger 103 frames from Cloudflare Pages.

## Gotchas

- **`cf-device-type` is only available on paid Cloudflare plans.** Free plans do not populate
  this header. On free tiers, fall back to UA parsing or serve conservative (mobile-safe) hints
  to all clients.
- **iOS Safari 17.4 103 support is navigation-only.** Subresource requests (fetch, XHR) made
  from within the page do not benefit from 103 even on Safari 17.4+.
- **Cloudflare Pages strips 103 in preview deployments.** Branch preview URLs (`*.pages.dev`)
  do not emit 103 Early Hints. Only production custom domain deployments do. This makes it
  impossible to test 103 behaviour in PR previews; use `wrangler pages deploy --branch main`
  against the production zone or test locally with a Cloudflare Tunnel.
- **The Cloudflare Pages 103 feature can be disabled per-zone in the dashboard** under Speed →
  Optimization → Early Hints. If the feature is toggled off, all Link preload headers still
  appear in the 200 response but no 103 frame is sent. Verify the toggle is on after any zone
  settings migration.

## Verification

```bash
# Confirm 103 is being sent from the edge (desktop UA)
curl -sD - \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36' \
  https://example.com/ | head -30
# Expect: HTTP/2 103 followed by link: headers, then HTTP/2 200

# Confirm 103 is NOT sent for React Native UA
curl -sD - \
  -H 'User-Agent: okhttp/4.12.0' \
  https://example.com/ | head -10
# Expect: HTTP/2 200 directly — no 103 frame

# Check Cloudflare Early Hints toggle
curl -s https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/settings/early_hints \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.value'
# Expect: "on"
```

## Related

- `mobile-network-resilience-cloudflare-workers.md`
- `android-webview-cloudflare-cache-control.md`
- `ios-wkwebview-cloudflare-cookies.md`
- `pwa-stale-assets-cloudflare-pages-ios-safari.md`
- `cloudflare/cloudflare-pages-headers-file.md` (if exists)

## Sources

- Cloudflare Blog: "Early Hints: How Cloudflare Can Improve Website Load Times by 30%" (2022)
- MDN Web Docs: HTTP 103 Early Hints
- WebKit Bug Tracker: `preconnect` in 103 not processed (Bug 248174)
- Chromium issue tracker: WebView 103 Early Hints support (issue #<number>)
- Next.js docs: `next/headers` and Link preload in App Router
- RFC 8297: An HTTP Status Code for Indicating Hints
