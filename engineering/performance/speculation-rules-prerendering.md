# speculation-rules-prerendering

**Issue:** Multi-page navigation feels slow because every click starts from zero: HTML fetch, then subresources, then render, all on the critical path of the user's next action. Traditional hints (`prefetch`, NoState Prefetch) either fetched only the document or faked rendering, so the navigation still waited on real work. The Speculation Rules API (Chrome/Edge, in progress elsewhere) lets the page declare which URLs to prefetch or fully prerender ahead of the click, making qualifying navigations render in near-zero time. This article covers how the API works, how to write document rules with the right eagerness, the same-site/HTTPS/`Supports-Loading-Mode` prerequisites, and how to measure whether speculation is actually firing.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core Concepts

1. **Speculation Rules target documents, not resources.** A `<script type="speculationrules">` block (or the `Speculation-Rules` header) declares URL patterns and an action — `prefetch` or `prerender` — so the browser optimizes the whole navigation, not one file. This is a fundamentally different model from `<link rel="prefetch">`, which fetches a single resource without any navigation semantics.
2. **Prefetch vs prerender.** `prefetch` fetches the response (optionally with credentials) for a future navigation and is cheap; `prerender` speculatively renders the full page off-screen — HTML, subresources, scripts — and activates it instantly on click. Prerender costs real memory, CPU, and bandwidth, so its rules must be more selective.
3. **Eagerness levels control the trigger.** In document rules, `eager` prerenders immediately on page load, `moderate` triggers on hover ~200 ms / touchstart heuristics, and `conservative` waits for pointerdown. Chrome enforces per-page caps to bound waste: roughly 2 prerenders for moderate/conservative and up to 10 for eager (dynamically extended by scroll-based prefetching for prefetch rules).
4. **Activation is what makes it instant.** On navigation to a prerendered URL, Chrome tears down the speculator page and activates the prerendered document, preserving state and replaying analytics in order; from the user's perspective, the click paints immediately. Until activation, prerendered pages run in a restricted mode (no full focus, some APIs deferred).
5. **It complements, not replaces, streaming and caching.** Speculation buys time with the user's hover/dwell intent and their device resources; it does not fix a slow origin, and a cache-busting rule set can multiply origin load. Treat it as the last layer on top of a fast critical path, and note browser support is Chromium-first — other engines simply ignore the rules harmlessly.

## Rule Configuration

1. **Inline document rules for site-wide link speculation.** A document rule with `where: { href_matches: "/*" }` and `eagerness: "moderate"` covers all same-site links with hover-based pragmatism; the browser applies its caps so you get the most-likely next pages. This one block is the recommended default for content sites.
2. **List rules for known hot destinations.** For login-success dashboards, onboarding step 2, or a paywall-success page, a list rule with explicit URLs and `eagerness: "eager"` prerenders immediately after load. Restrict eager to one or two high-confidence destinations — eager prerenders consume bandwidth and memory whether or not they are used.
3. **Conservative eagerness for expensive pages.** On devices or pages where prerendering is costly, `conservative` (pointerdown-only) nearly eliminates false positives while still removing most of the navigation cost, since a pointerdown precedes the click by 100-300 ms. Use it for the long tail of links matched by document rules.
4. **Prefetch-only tiers for uncertain targets.** `prefetch` with moderate eagerness warms the HTML response at a fraction of prerender cost and pairs with `stale-while-revalidate` on the document; on navigation the HTML is served from memory and only subresources load. A sensible ladder: prefetch for all internal links, prerender for the top handful.
5. **Exclude what must not be speculated.** Document rules accept `not_where` (and `relative_to` for scoping) to skip logout links, one-time action URLs like unsubscribe, and user-scoped pages where prefetch with credentials could cause side effects. Also set `referrer_policy` on prefetch rules when the destination should not receive full referrer data.

## Prerequisites and Constraints

1. **Same-site, HTTPS (or localhost) destinations.** Same-site speculation works without destination cooperation; cross-origin prefetch/prerender additionally requires the destination to opt in with the `Supports-Loading-Mode: credentialed-prerender` (or `fuzzy-prerender`/`prefetch` as appropriate) response header. Without it, cross-origin rules are ignored silently.
2. **The destination must be prerender-safe.** Prerendered pages execute JavaScript with `document.prerendering === true` (and fire `prerenderingchange` on activation); analytics, ads, and anything with side effects must wait for activation. Audit the target pages for code that assumes visibility or focus on load.
3. **Memory and bandwidth budgets.** Each prerender is a full document instance; on low-end mobile a handful of eager prerenders can evict useful cache or jank the foreground page. Prefer moderate/conservative on constrained devices (the caps do most of the work) and measure on the target hardware.
4. **No guarantee of use.** The browser may discard speculations under pressure, on navigation elsewhere, or at cap eviction; treat prerendering as best-effort latency removal, never as a delivery mechanism (a "viewed" event must not depend on the page having been prerendered).
5. **Header-delivered rules for cacheability.** Serving rules via the `Speculation-Rules` header (pointing at an external JSON rule file) keeps them out of the HTML and lets a CDN or edge worker inject speculation policy per route — useful when the HTML itself is static or shared across experiences.

## Measurement and Debugging

1. **Chrome's speculation status UI.** `chrome://histograms/Speculation` aside, the DevTools "Prerequisites" panel and internal pages show which URLs were prefetched/prerendered and why a rule did not fire (wrong eagerness window, cap reached, prerequisite failed); check here before assuming the API is broken.
2. **`performance.getEntriesByType('navigation')` activation evidence.** On a prerendered navigation, the entry has `activationStart > 0`; expose activation rate as a metric (share of navigations that landed on a prerender) to prove the feature is delivering instant loads to real users, not just in demos.
3. **RUM attribution of navigation speed.** Segment LCP and TTFB by `activationStart` presence: prerendered navigations should show near-zero LCP deltas from activation; if they do not, the destination page is doing post-activation heavy work that prerendering cannot hide.
4. **Origin traffic delta monitoring.** Speculation multiplies document fetches by (1 + false-positive rate); watch origin request volume and cache hit ratio after enabling eager/prefetch rules, especially for authenticated HTML where CDN caching does not apply.
5. **A/B test with care.** Randomizing the presence of the rules block (not the API) isolates effect; beware that lab tests hover deliberately and inflate speculation success versus field behavior. Prefer field metrics over lab medians when judging whether to widen eagerness.

## Related

resource-hints-prefetch, resource-hints-preload, lcp-optimization, service-worker-cache-strategy, above-fold-optimization
