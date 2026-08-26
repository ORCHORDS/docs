# Early Hints and Speed Brain: Browser Support Disparity

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

You enabled 103 Early Hints and Speed Brain on the example project zone and
aggregate RUM LCP improved noticeably — but the mobile/desktop gap
got wider, not narrower. Desktop Chrome sessions show big wins while
iOS sessions are flat. A dashboard says "the site got faster" but
the majority of example project's mobile traffic (iOS/WebKit via social
in-app browsers) experienced zero change. Worse, an analytics spike
suggests users are "visiting" pages they never opened — prefetches
being counted as pageviews — and there is concern that prefetching
the age-gate page could falsely record gate interactions.

## Context

Both features are Chromium-skewed edge optimizations. 103 Early
Hints: Cloudflare caches `Link: rel=preload/preconnect` headers
from prior origin responses and emits an interim `HTTP 103` from
the edge while the origin (or Worker) is still thinking, so the
browser starts fetching critical assets early. Speed Brain:
Cloudflare's zero-config prefetching, which injects a
`Speculation-Rules` HTTP header pointing at a hosted rules config
(`"eagerness": "conservative"`); supporting browsers prefetch the
next page on pointer/touch-down, served only from the CDN cache
(uncached targets get a 503, never the origin). Chromium 121+
implements the Speculation Rules API; Safari/WebKit does not — and
ALL iOS browsers (including "Chrome for iOS") use WebKit, so iOS
users get none of the benefit. For a 21+ platform like example project,
prefetching must also never bypass or falsely record the age gate.

## How 103 Early Hints works at the edge

```
Without Early Hints:
  Browser ── GET /feed ──► Edge ── miss ──► Origin/Worker
  Browser ◄──────────── 200 + HTML (waits full TTFB) ────
  Browser then discovers CSS/fonts and fetches them.

With Early Hints (Cloudflare):
  1. A previous 200/301/302 response for /feed carried:
       Link: </css/app.css>; rel=preload; as=style
       Link: <https://api.example.com>; rel=preconnect
  2. Edge caches those Link headers per-URL.
  3. Next request: edge emits 103 + Link IMMEDIATELY,
     while the request continues to origin/Worker.
  4. Browser preloads/preconnects during origin think time.
  5. Final 200 arrives; critical assets already in flight.

Requirements (Cloudflare):
  → HTTP/2 or HTTP/3 only (no HTTP/1.1 emission)
  → HTML/HTM/PHP or extensionless URLs
  → Generated from 200/301/302 responses with Link headers
  → All plans (Free through Enterprise); zone toggle
```

## Browser support disparity (verified 2026-08)

```
Feature            Chrome/Edge      Firefox    Safari/WebKit
──────────────────────────────────────────────────────────────
103 Early Hints    Yes (M94+ acts   Yes        Partial:
(preload)          on hints)                   preconnect ONLY;
                                               preload ignored
Speculation Rules  Yes (121+ for    No         No
prefetch           Speed Brain)
(Speed Brain)

iOS reality: every iOS browser — Safari, Chrome for iOS,
Instagram/TikTok in-app browsers — is WebKit under the hood.
So iOS traffic gets: no preload from 103, no Speed Brain
prefetch. Desktop Chrome gets both.

WebKit movement: Safari 26.4 shipped Resource Timing L3
attrs `firstInterimResponseStart` / `finalResponseHeadersStart`
so 103 receipt can now be MEASURED in Safari — but preload
hints are still not acted on, and Speculation Rules remains
unimplemented.

Unsupported browsers ignore both features safely (progressive
enhancement) — the cost is uneven benefit, not breakage.
```

## Speed Brain mechanics

```
Enable: Dash → Speed → Settings → Content Optimization
        → Speed Brain: On (default-on for Free zones)

Response gains a header:
  Speculation-Rules: "/cdn-cgi/speculation"

Hosted config (opinionated, not editable):
  { "prefetch": [{
      "source": "list",
      "urls": ["/*"],           // href_matches "/*"
      "eagerness": "conservative"  // pointer/touch-down only
  }] }

Prefetch path:
  → Browser sends prefetch with Sec-Purpose: prefetch
  → Edge serves ONLY if the HTML is in CDN cache → 200
  → Not cached → 503, request never reaches origin
  → Cloudflare measured ~45% LCP reduction on successful
    prefetches (0.88–1.1s saved) — Chromium cohort only

Exclusions:
  → No prefetch on Worker routes (avoids side-effect logic)
  → Not on pages.dev domains; example project's custom domain is fine
  → Incompatible with CSP strict-dynamic
  → Origin-provided Speculation-Rules headers win
```

## The measurement trap: cohort-skewed RUM

```
Aggregate RUM after enabling both features:

  Cohort            Share   LCP before  LCP after   Δ
  ────────────────────────────────────────────────────────
  Desktop Chrome     35%      2.4s        1.6s     -33%
  Android Chrome     20%      3.0s        2.2s     -27%
  iOS WebKit         45%      3.4s        3.4s       0%
  ────────────────────────────────────────────────────────
  Blended p75        —       "improved"  — misread as
                              "site got faster for users"

The improvement is real but concentrated: the already-fast
desktop cohort got faster; the slow mobile-iOS cohort did
not move. CWV is assessed mobile vs desktop separately, so
a blended dashboard hides that mobile p75 (iOS-dominated
for example project) is unchanged. Always segment RUM by
OS/engine (iOS-WebKit vs Android-Chromium vs desktop)
before crediting an edge feature. If iOS didn't move,
the fix for example project's mobile CWV lies elsewhere (payload,
TTFB, image weight — engine-neutral work).
```

## Verifying each feature

```bash
# 103 Early Hints: look for the interim response (HTTP/2!)
curl --http2 -sv https://example.com/ -o /dev/null 2>&1 \
  | grep -E "^< HTTP|^< link"
# Expect:
#   < HTTP/2 103
#   < link: </css/app.css>; rel=preload; as=style
#   < HTTP/2 200

# Speed Brain: check for the header
curl -sI https://example.com/ | grep -i speculation-rules
# Then fetch the rules doc it points to:
curl -s https://example.com/cdn-cgi/speculation
```

```
DevTools (Chromium): Application → Speculative loads panel
shows rules, prefetch status, and initiating URL. Network
tab: hover a link, watch a prefetch request appear with
Sec-Purpose: prefetch. Safari: nothing to see — expected.
```

## Anti-patterns

- **Reading blended RUM as universal improvement** — Early Hints +
  Speed Brain gains come almost entirely from Chromium sessions.
  Segment by engine/OS or you will misattribute a desktop-only win
  to "mobile performance work" while iOS p75 stays failing.
- **Counting prefetches as pageviews** — client-side analytics that
  fire on document load in a prefetched page inflate traffic.
  Speed Brain's prefetch (not prerender) does not execute JS until
  navigation, but server/edge log-based analytics see the request:
  filter on `Sec-Purpose: prefetch` before counting.
- **Letting prefetch touch session or gate state** — example project's age
  gate must key on an explicit user interaction, never on a page
  request. A prefetched gate page must not set "gate seen/passed"
  cookies or log a gate impression at the edge.
- **Relying on Early Hints for the LCP image on mobile** — with
  iOS-heavy traffic, `Link: rel=preload` via 103 does nothing for
  most mobile users. Keep in-document `<link rel="preload">` and
  `fetchpriority="high"` as the engine-neutral baseline.

## Gotchas

- **Safari acts only on preconnect in 103** — a 103 carrying both
  preconnect and preload gives Safari the connection warm-up only.
  Design Link headers so preconnect targets (api.example.com, image
  CDN) are listed, not just asset preloads.
- **Early Hints replays cached Link headers** — the 103 is emitted
  before origin/Worker logic runs, so per-user or authenticated
  Link headers can leak to other visitors. Only emit generic,
  public Link headers from the origin.
- **Speed Brain serves prefetches from cache only** — example project's
  static-export HTML must be cache-eligible (no `private`/
  `no-store` on anonymous HTML) or every prefetch 503s and the
  feature silently does nothing. Stale cached HTML also gets
  prefetched: purge on deploy.
- **Cookie/session drift on prefetched pages** — the prefetched
  copy reflects cookies at prefetch time. If the user's session or
  age-gate state changes between prefetch and click, they can land
  on a stale-state page. Keep gate enforcement client-side on
  interaction, not baked into cached HTML.
- **Safari 26.4 can measure 103 but not use preloads** — new
  Resource Timing attrs (`firstInterimResponseStart`) let RUM
  confirm 103 delivery on Safari; do not mistake "103 received"
  for "103 acted upon."

## Verification

- 103 responses observed via `curl --http2 -sv` with expected
  Link headers on key routes.
- `Speculation-Rules` header present and rules doc fetchable at
  `/cdn-cgi/speculation`.
- Chromium DevTools Speculative loads panel shows successful
  (200) prefetches on cached routes; 503s investigated.
- RUM segmented by engine: iOS-WebKit cohort reported separately;
  no feature credited for gains it cannot deliver there.
- Analytics pipeline filters `Sec-Purpose: prefetch` requests.
- Age gate confirmed interaction-driven; prefetching the gate page
  records no impression and sets no gate cookie.
- Link headers audited: preconnect included for Safari's benefit;
  no user-specific Link headers emitted.

## Related

- `documentation/docs/policies/performance/core-web-vitals-overview.md`
- `documentation/docs/policies/performance/core-web-vitals-mobile-desktop-disparity-edge-caching.md`
- `documentation/docs/policies/cloudflare/smart-placement-best-practices.md`
- `documentation/docs/policies/cloudflare/cache-device-type-segmentation-mobile-desktop.md`

## Source URLs (verified 2026-08-17)

- Cloudflare Early Hints —
  https://developers.cloudflare.com/cache/advanced-configuration/early-hints/
- Cloudflare Speed Brain docs —
  https://developers.cloudflare.com/speed/optimization/content/speed-brain/
- Introducing Speed Brain (Cloudflare blog) —
  https://blog.cloudflare.com/introducing-speed-brain/
- How To Improve Page Speed With 103 Early Hints (DebugBear) —
  https://www.debugbear.com/blog/103-early-hints
- WebKit Features for Safari 26.4 —
  https://webkit.org/blog/17862/webkit-features-for-safari-26-4/
