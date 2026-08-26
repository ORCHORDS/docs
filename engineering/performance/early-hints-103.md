# early-hints-103

**Issue:** Between the browser sending an HTTP request and the origin finishing "server think time" — rendering a page, querying a database, or waiting on a slow upstream — the connection sits idle while the browser could already be fetching the critical CSS, fonts, and hero images the HTML will inevitably reference. HTTP 103 Early Hints is the informational status code that fills that gap: the server (or CDN) sends an interim response carrying Link headers so subresources begin downloading before the final 200 arrives. Despite roughly 93% browser support, only around 5% of top sites used it as of the 2025 Web Almanac, mostly because origins rarely implement it — which is exactly why CDN-level implementations, led by Cloudflare, are where most teams should adopt it. This article covers how 103 works, what to hint, and how to avoid the pitfalls.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How 103 works

1. **An interim response, not a redirect.** The server sends a 103 response containing headers (typically Link with rel=preload or rel=stylesheet), then follows with the real response (200, 302, whatever it may be). The browser treats the 103 as advisory and starts speculative fetches that are later matched to the final document's resource references.
2. **It converts dead time into fetch time.** If origin think time is 150-400 ms (typical for SSR pages hitting a database), preloading a render-blocking stylesheet and a hero image during that window removes most of that time from the critical path, directly improving LCP and FCP.
3. **Browsers absorb the complexity.** Matching, priority, and deduplication against the final HTML are handled by the browser; mis-hinted resources are simply wasted bandwidth rather than breakage, which makes 103 low-risk to trial.
4. **It composes with preconnect.** Link headers with rel=preconnect can also travel in a 103, warming DNS/TCP/TLS to third-party origins (analytics, image CDNs) before the document tells the browser about them.

## Adoption and support

1. **The adoption gap.** Browser support sits near 93% (missing mainly older Safari and legacy enterprise browsers), yet only about 5% of top sites emitted 103 responses per 2025 Web Almanac data — the barrier is origin and middleware support, not client capability.
2. **CDNs are the adoption path.** Cloudflare caches Link headers observed on previous responses and automatically emits a 103 in front of the origin's response, so a site whose origin sends Link headers on the final response gets Early Hints with zero origin changes — enable it in the CDN tier.
3. **Workers can synthesize hints.** On Cloudflare, a Worker can hold a table of per-route hints (KV or inline) and stream the 103 itself while the origin or a subrequest is still in flight; community patterns combine Workers with static hosting (R2, Pages) to give static sites Early Hints.
4. **Fallbacks are graceful.** Browsers that ignore 103 simply wait for the final response; no code paths branch, and the cost is a few hundred bytes of headers.

## What to hint

1. **Render-blocking CSS.** rel=preload (as=style) or rel=stylesheet hints for the main CSS bundle are the highest-value hints because stylesheets are parser-blocking and almost always known ahead of time from the previous response of the same route.
2. **The LCP image.** If the hero image URL is stable per route (route-level caching of the hint table makes this tractable), hinting it with rel=preload as=image fetch-priority=high during think time is the single largest LCP lever on image-heavy pages; combined with fetchpriority on the img element, it removes the discovery delay entirely.
3. **Critical fonts.** Self-hosted woff2 files referenced by CSS are discovered late (after CSS parse); hinting them in the 103 pulls them forward. Subset fonts first — hinting a 300 KB font file to save 200 ms of discovery is a bad trade.
4. **Preconnect to known third parties.** A rel=preconnect for the API or image CDN domain the page will definitely use costs nothing when correct.
5. **Do not hint everything.** Hints are speculative; every hint competes for connection slots and bandwidth. Cap at roughly 3-5 hints for the genuinely critical path, sourced from the previous response's actual waterfall rather than optimism.

## Pitfalls and guardrails

1. **Stale hints after redesigns.** CDN-cached Link headers reference asset URLs from the last response; after a deploy that renames hashed bundles, hints can point at files that 404 — browsers recover, but you waste the round trip. Purge or version the hint table atomically with deploys.
2. **Dynamic pages with unstable heroes.** If the hero image depends on per-request data (personalization, A/B), a generic hint may fetch the wrong asset. Prefer hinting only route-stable resources and solving the dynamic LCP with fetchpriority in the HTML instead.
3. **Double-fetch bugs are mostly historical.** Early implementations occasionally double-fetched hinted resources; modern browsers dedupe by URL, but verify in the network panel during rollout — especially for hints crossing origins without proper CORS headers.
4. **Measure before and after.** Compare LCP and FCP field data (or lab runs with response throttling that reproduces think time) with hints on and off; on fast origins with sub-50 ms think time, 103 adds little, and the complexity budget is better spent elsewhere.

## Operations

1. **Verify emission.** curl -i against the HTML endpoint and confirm the 103 interim response appears before the final one; also check the CDN analytics, which count Early Hints responses served.
2. **Keep the hint inventory in code.** Maintain per-route hints as data (a Worker route table or build-time manifest) so they are reviewed in PRs, tested in CI against the current asset manifest, and never drift into folklore.
3. **Route around caches carefully.** 103 responses must not be cached independently of the final response in ways that pin old hints; follow CDN guidance on cache keys, and disable Early Hints on endpoints whose critical resources churn per request.
