# Speculation Rules Prerender With Document Rules

## Scope

Driving the Speculation Rules API's `document_rules` keyset — `where` link matching, `eagerness` tiers, `relative_to` resolution, and `requires` predicates — inside `<script type="speculationrules">` blocks, plus the multi-document concerns that document-level prerendering raises: activation via `prerenderingchange`, `No-Vary-Search` reuse, and cross-origin opt-in headers. Covers the rule schema and deployment as a progressive enhancement; excludes the older hardcoded-`urls` form except as a contrast, and excludes asset-level `<link rel="prefetch">` strategies covered by the resource-hints article in this leaf.

## Workflow or implementation guidance

Document rules turn speculation from an enumerated URL list into a live selector over the page's own link graph. The rule block:

```html
<script type="speculationrules">
{
  "prerender": [{
    "where": "href_matches('/*\\/app\\/*')",
    "eagerness": "moderate",
    "relative_to": "document"
  }]
}
</script>
```

`where` accepts a small predicate language: `href_matches(pattern)` (URL-prefix or wildcard matching against the link's absolute href), `selector_matches(css)` (restricts candidate links by DOM selector), and combinators `and`, `or`, `not`. That composes site policy precisely — same-origin app routes but not sign-out, and only links inside the primary nav:

```json
{
  "where": {
    "and": [
      { "href_matches": "/*\\/*" },
      { "not": { "href_matches": "/*\\/logout" } },
      { "selector_matches": "nav.primary a[href]" }
    ]
  },
  "eagerness": "moderate"
}
```

`eagerness` decides when a matching URL is speculated. `immediate` fires at rule parse — reserve it for one high-confidence destination. `eager` speculates all matches subject to the browser's internal caps. `moderate` (the workhorse) triggers on hover or pointer-down with a short dwell, so cost tracks demonstrated intent. `conservative` requires pointer/touch-down only, for metered or flaky contexts. Choosing `eager` for a nav-heavy page is the classic overshoot: dozens of full page fetches for zero activations.

`relative_to` anchors `href_matches` patterns: `"document"` (default) resolves against the current URL; an explicit base URL anchors absolute patterns elsewhere. Escaping in patterns is regular-expression-flavored — the `/*\\/app\\/*` form above is the pattern-grammar escaping for a path segment, and getting it wrong matches nothing, silently.

The runtime contract lives on the prerendered side. During prerender, `document.prerendering` is `true`; the document is rendered off-screen with script running, and activation on click fires `prerenderingchange`. Side effects with session or analytics meaning belong after that event:

```js
if (document.prerendering) {
  document.addEventListener('prerenderingchange', activateSideEffects, { once: true });
} else {
  activateSideEffects();
}
```

`PerformanceNavigationTiming.activationStart` (nonzero on activated prerenders) is the timestamp to subtract when attributing metrics to the user-visible navigation.

Cross-origin and cache-consistency requirements are the deployment hard parts. A cross-origin prerender target must opt in with `Supports-Loading-Mode: credentialed-prerender` (when the prerender carries credentials); without the header the browser skips the candidate with no page-visible error. When the target's response varies on something the prerender cannot predict — typically query strings — `No-Vary-Search` on the target declares which query params may differ while reusing the prerendered response; without it, a param difference forces a refetch and the instant navigation degrades to normal.

## Controls

- Prefer `eagerness: "moderate"` plus a `where` clause limiting candidates to same-origin, non-transactional links; treat `eager` as an exception needing justification.
- Gate analytics, cookies, and session beacons on `prerenderingchange`; assert on `document.prerendering` before anything that should count as a visit.
- Set `No-Vary-Search` on prerender targets whose query strings are cosmetic, and keep the true-varying parameters out of that list.
- Send `Supports-Loading-Mode: credentialed-prerender` from authenticated targets that intend to be prerendered cross-origin.
- Verify rule behavior in DevTools' "Speculative loads" view before shipping — it reports each candidate, the matching rule, and the discard reason.

## Validation evidence

- Hover-then-click trace: hover a matching link, confirm in the Speculative loads panel that a prerender started; click and assert `activationStart > 0` and near-zero navigation-to-render gap in the RUM payload.
- Discard-reason audit: load every major template with the panel open and record why each candidate was not speculated (referrer policy mismatch, memory pressure, non-matching `where`); fix rule text until the discard reasons are intentional.
- Analytics parity check: prerender-activate a page with the analytics gate in place and assert exactly one pageview event — not one at prerender time plus one at activation.
- Vary/No-Vary-Search test: prerender a target, navigate with an ignored param added, and assert from the panel that the prerender was reused rather than refetched.

## Failure modes and correction

- Nothing is ever speculated: the `where` pattern is over-escaped or anchored to the wrong base. Patterns are validated only at match time — test them in the panel, not by reading the JSON.
- Pageview counts inflate: prerendered documents ran load-time analytics. Move beacons behind `prerenderingchange`.
- Prerenders constantly discarded after ~30 s unactivated: that is expected lifecycle, not a bug; do not retry-loop speculation from page script, and do not depend on prerender for correctness of any feature.
- Logged-in users get logged-out prerenders: the target varied on cookies without `No-Vary-Search` awareness, or the cross-origin target lacked the `Supports-Loading-Mode` opt-in; align response variance with the speculation contract or restrict `where` to stateless pages.
- Duplicate name/snapshot breakage after activation: elements that assume "first paint equals first user exposure" (autoplay media, focus capture) fire during prerender; gate them on `activationStart`/`prerenderingchange`.
- Referrer-policy blocked candidates: a target with a stricter `Referrer-Policy` than the initiating page is skipped by design; relax the mismatch or exclude the route.

## Limitations

- Chromium-only implementation; the script block is inert in other engines, which is also the fallback — no JS branch is needed or possible.
- Prerender budget and lifetime are browser-controlled (caps on concurrent prerenders, discard under memory pressure); the API is a hint with no guarantees.
- The `where` grammar supports a fixed predicate set; complex routing policies need server-rendered rule generation per template.
- Only document speculation is covered here; script-speculation rules and prefetch-rule details are adjacent surfaces with their own constraints.
- Activation preserves no in-page JS state from the prerendered document's execution; anything computed before activation must be revalidated after it.

## Canonical sources

- W3C Web Incubator CG, Speculation Rules: https://wicg.github.io/nav-speculation/speculation-rules.html
- WHATWG, No-Vary-Search header: https://httpwg.org/http-extensions/draft-ietf-httpbis-no-vary-search.html
- MDN, Speculation Rules: https://developer.mozilla.org/en-US/docs/Web/API/Speculation_Rules_API
