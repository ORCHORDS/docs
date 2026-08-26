# speculation-rules-api-prerender

**Issue:** Multi-page-app navigations feel slow because the browser only starts fetching the next page after the user clicks the link. The Speculation Rules API (`<script type="speculationrules">`) fixes this by letting the browser prefetch or fully prerender likely next destinations ahead of the click, but teams either skip it (Safari/Firefox do not support it), over-prerender (wasting user data and memory), or ship it with analytics that double-counts prerendered pageviews. As of 2026 this API is a pure progressive enhancement: Chromium users get near-instant navigations, everyone else falls back to normal loading with zero code changes.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core mechanics

1. **JSON-in-script instead of link tags.** Speculation is declared in a `<script type="speculationrules">` block containing a JSON list of rules, each with an `action` (`"prefetch"` or `"prerender"`) and either a static `urls` list or a `document_rules` object. This replaces the deprecated `<link rel="prerender">`, which only ever prerendered one hardcoded URL with no lifecycle control.
2. **Prefetch vs prerender are different tiers.** `prefetch` fetches the document (and can lift it into the HTTP cache, including via the newer "prefetch cache") but does not execute it — cheap, but the page still has to render after click. `prerender` fully renders the page off-screen, runs scripts, and fires no visible lifecycle signals until activation, so the navigation is genuinely instant. Prefetch anything plausible; prerender only what the user is very likely to visit.
3. **Prerendered documents are activated, not reloaded.** When the user clicks a prerendered link, Chrome activates the existing document, appends a single session-history entry, and fires `prerenderingchange`. During the pre-activation phase, `document.prerendering` is `true` — scripts must gate side effects (analytics, cookies, notifications) on that flag plus the `prerenderingchange` event, not on DOMContentLoaded.
4. **DevTools has a dedicated panel.** Chromium's Application tab exposes "Speculative loads" showing which URLs were prefetched/prerendered, which rule matched them, and why a speculation was discarded — always verify there before assuming rules are firing.

## Document rules and eagerness tuning

1. **`eagerness: immediate`.** Speculation starts as soon as the rule is parsed. Use for the single most likely next page (e.g., the top item in a list the user just searched), never for whole sitemaps.
2. **`eagerness: eager`.** Speculates on all URLs matched by the rule, subject to Chrome's internal limits (tens of prerenders, fewer on memory-constrained mobile). Intended for small site sections like a paginated article chain; it will still be throttled on Data Saver-like conditions.
3. **`eagerness: moderate`.** Chrome hovers the trigger: speculation starts when the user hovers or presses pointer-down on a matching link (hover requires a short dwell, roughly 200ms, to avoid firing on accidental mouse sweeps). This is the default recommendation for site-wide link prerendering because it pays cost only for links with demonstrated intent.
4. **`eagerness: conservative`.** Only pointer/touch-down triggers speculation — the cheapest tier of intent, useful on flaky or metered connections where even a hover-triggered prerender is a waste.
5. **Filter with `where` clauses.** Document rules accept a relative selector (`"where": "href.match('/*\\/blog\\/*')"` style matching) so you can restrict speculation to same-origin links, exclude logout/POST-only links, or skip UGC hrefs. Without a filter, a CMS content link field is a prerender shotgun pointed at arbitrary external sites (which will fail cross-origin rules anyway, see below).

## Browser support and fallback strategy (2026 state)

1. **Chromium-only, but safely so.** Prefetch shipped in Chrome 109, document rules with `eagerness` in Chrome 121; Edge and other Chromium browsers follow. Safari and Firefox have not shipped it as of 2026 — it has been proposed for Web Platform Tests Interop consideration, which signals intent but no timeline. The API degrades silently: unsupported browsers parse the script tag, ignore the unknown type, and navigate normally.
2. **Never feature-detect-and-branch your app code.** There is no JS surface to detect (by design — speculation is a hint). Write rules once, let Chromium act on them, and treat any behavior change as a bonus, not a contract. Do not build UX (e.g., "instant nav" animations) that assumes prerender succeeded; Chrome can cancel a prerender at any time on memory pressure or page weight.
3. **Keep legacy hints only where they add reach.** `<link rel="prefetch">` still works everywhere-ish and is respected by Firefox's own prefetch mechanism; keep it for critical next-assets (the JS chunk of the next route), and layer Speculation Rules on top for document-level speed. Remove any legacy `<link rel="prerender">` — it is deprecated in favor of this API.
4. **Cross-origin speculation requires opt-in.** Same-site (including subdomain) prerender works with `"relative_to": "document"` defaults, but cross-origin prerender requires the target server to send `Supports-Loading-Mode: credentialed-prerender` (for credentialed requests). Cross-origin prefetch similarly benefits from the `Sec-Purpose: prefetch` handling to avoid cache mismatches — if the target server doesn't cooperate, Chrome silently skips it.

## Pitfalls that bite in production

1. **Analytics inflation.** Third-party tags (Google Analytics, GPT, AdSense) defer themselves until activation, but any first-party analytics that runs on load will count prerendered pages that were never visited, skewing pageviews, session duration, and bounce rate. Gate every beacon: skip when `document.prerendering === true`, and fire from a `prerenderingchange` listener instead.
2. **Memory and quantity limits.** Chrome caps concurrent prerenders (roughly 2 for `immediate`/`eager` on desktop, and it discards prerenders after ~30 seconds unactivated or under memory pressure). Heavy pages can be cancelled mid-prerender; do not rely on prerender for correctness of anything.
3. **Referrer-policy bystander rule.** Chrome will not prerender a target whose referrer policy is stricter than the initiating page's (it would leak the referrer into a navigation that may never happen). If a link mysteriously never prerenders, check `Referrer-Policy` on both ends before blaming the selector.
4. **Vary-header mismatches.** A prerendered response that varies (e.g., `Vary: Cookie` for A/B or logged-in state) can mismatch the real activated navigation. Use `No-Vary-Search` (and stable cache keys) so the prerendered variant is reusable; otherwise Chrome re-fetches and your "instant" nav silently degrades to normal.
5. **Cost on metered connections.** Prerendering downloads the full page including subresources. `moderate`/`conservative` eagerness plus same-origin `where` filters keep speculation proportional to intent; `eager` on a link-heavy page can burn real user data for zero benefit.

## Related

- `prefetching-strategies.md` (app-level prefetch: React Query, Next.js Link)
- `html-performance-resource-hints.md`
- `offline-fallback-pages.md`
