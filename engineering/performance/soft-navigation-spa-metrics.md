# soft-navigation-spa-metrics

**Issue:** Core Web Vitals field data is built around page loads, but modern SPAs often load once and then "navigate" client-side for the entire session via the History API. Traditional measurement records the initial load's LCP/INP/CLS and ignores every subsequent route change, so a React/Vue app with a 4-second route transition looks identical in CrUX to one with 200 ms transitions. This blinded both dashboards and ranking signals to the dominant user experience. The Soft Navigation API (heuristic detection of client-side navigations, per-navigation performance entries, origin trial from Chrome 139 in 2025) finally standardizes how to attribute vitals to each soft navigation, and RUM pipelines, frameworks, and analytics SDKs spent 2025-2026 adopting it. Teams that keep measuring only the hard load are optimizing a page most users see once.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What the API actually does

1. **Heuristic detection.** The browser detects a soft navigation when a user interaction (click) is followed by a URL change via the History API and accompanying DOM mutations within a time window. No explicit API call is required from the app; the heuristics run in the browser, which is what makes it work across frameworks.
2. **New performance entry types.** A soft-navigation entry appears in the PerformanceObserver, and paint and LCP entries are re-emitted tagged with the new navigation (navigationMode soft), so each transition gets its own first-paint and largest-contentful-paint measurements tied to the interaction that started it.
3. **Origin trial status.** Chrome shipped the Soft Navigation API behind an origin trial starting with Chrome 139 (2025), later expanding availability into 2026; Safari and Firefox are not there. Treat it as progressive enhancement for measurement, never as the only source of truth.

## What changes in measurement practice

1. **Per-route vitals.** With soft navigation entries, you can compute LCP for each route transition (time from click to the new view's largest content paint) and slice by route. This converts "our SPA is fast" into "the /settings route transition p95 is 3.1 s," which is an actionable statement.
2. **INP scope widens.** Interactivity delays during long route transitions (data fetching, big renders) now fall inside a navigation window you can attribute. Route transitions are frequently the worst interactions in an SPA; soft-nav attribution surfaces them instead of averaging them away.
3. **CrUX is not there yet.** As of 2025-2026, CrUX and the search ranking signals are still hard-load based; soft-nav data improves your own RUM visibility and UX, not your Search Console scores. Expect that to change as the API stabilizes, which is the strategic reason to instrument now.
4. **Click-to-paint budgets replace load budgets.** Define budgets on time from initiating click to new-view LCP rather than document load metrics; DebugBear and Chrome's guidance both frame soft-nav measurement around this interaction-relative timing.

## Implementation checklist

1. **Register a PerformanceObserver early.** Observe the soft-navigation entry type plus LCP re-emissions, buffer them per navigation with the start time, and attach route metadata (path, transition duration) in your RUM payload. Guard the code behind feature detection so unsupported browsers degrade to today's page-load metrics.
2. **Fix your analytics session model.** Most tools assume one page view per document; extend events to carry a navigation ID and route so funnel analysis counts virtual views correctly and vitals join to the right route.
3. **Verify heuristics fire on your router.** History-API pushState plus real DOM changes is required; transitions that only swap innerHTML without URL change, or URL changes without user interaction (redirects), may not qualify. Test each route pattern and record which routes escape detection.
4. **Watch for missed detections in production.** Compare soft-nav event counts against client-side router events; a persistent gap means heuristics are missing navigations (for example, deferred DOM mutations outside the detection window), and your route-level medians are subtly biased.

## Acting on the data

1. **Profile the worst routes, not the app.** Route-level p75/p95 LCP immediately ranks where transition time goes: bundle fetch (lazy chunk waterfall), data fetch (serial await), or render (long task). Each has a different fix: prefetch chunks, parallelize or cache queries, virtualize or defer rendering.
2. **Pair with existing tooling.** Combine soft-nav entries with the Long Animation Frames API to attribute transition jank to specific scripts, and with resource timing to see chunk-fetch waterfalls per route change. The navigation timestamp is the join key across all three.
3. **Set regression gates.** Add route-transition p75 budgets to CI dashboards (Lighthouse SPA mode and RUM-based checks) so a new slow route or a heavier chunk fails visibility rather than silently shipping. This is how the SPA equivalent of a slow page load stops being invisible.
4. **Do not game the heuristics.** Triggering artificial DOM mutations to force detection, or delaying URL updates to shrink measured paint windows, corrupts your own data without affecting users. The metric exists to reflect the experience; optimize the transition, not the timestamp.
