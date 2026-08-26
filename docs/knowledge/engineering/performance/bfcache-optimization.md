# bfcache-optimization

**Issue:** The back/forward cache (bfcache) lets browsers restore a page instantly on back/forward navigation from an in-memory snapshot, with zero network requests and near-zero script re-execution. It is one of the largest free wins in web performance — often hundreds of milliseconds to multiple seconds on mid-range mobile devices — and it is frequently thrown away by preventable mistakes: an unload listener here, a blanket Cache-Control: no-store there. Because Chrome began ignoring no-store for bfcache eligibility in some cases and the unload event is being deprecated specifically because it blocks bfcache, teams that audit this now get compounding returns. This article covers eligibility blockers, production monitoring via notRestoredReasons, and the remediation playbook.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why bfcache matters

1. **Restores are nearly free.** A bfcache restore skips DNS, TCP, TLS, request, and render — the page is already painted in memory. On a cold 4G connection that is routinely 1-3 seconds saved per back navigation, and back/forward traffic is a large share of navigations on content sites.
2. **It is a Core Web Vitals lever.** Restored pages report instant LCP and CLS values in CrUX and RUM, lifting field percentiles at zero engineering cost once eligibility blockers are removed. Sites with high restore rates visibly outperform their non-cached selves in field data.
3. **The ecosystem is converging.** All major engines implement some form of bfcache, the notRestoredReasons API gives cross-browser-ish diagnostics, and standards work (deprecating unload, evolving guidance on no-store, discussions around more predictable eviction through cooperative caching approaches) keeps pushing eligibility rates up for sites that follow current guidance.

## Blockers and eviction reasons

1. **unload handlers.** The historical killer. Pages with a legacy unload listener are ineligible in Chrome because unload's semantics (fire reliably at page death) conflict with a page that never dies. Migrate to pagehide and visibilitychange; permission and deprecation trials for unload exist but are a countdown, not a solution.
2. **Cache-Control: no-store.** Long treated as a hard bfcache blocker (reason code response-cache-control-no-store), it is still applied far too broadly — often to pages with no genuinely sensitive content. Chrome has started granting bfcache to some no-store pages anyway, which means the header harms you without even buying the behavior people assume it does. Restrict no-store to truly sensitive screens; prefer no-cache plus proper validation elsewhere.
3. **Related-state entanglement.** Open WebSockets or WebRTC connections, locked IndexedDB handles, in-flight fetches, and dedicated workers can block entry. Close or release them in pagehide; reopen lazily on pageshow rather than eagerly in module scope.
4. **Cross-origin iframes and headers.** Frames with their own blockers (or COOP/COEP mismatches in older behavior) can disqualify the top-level page; reason codes distinguish whether the blocker is in your frame or a third party's, which determines whose fix it is.
5. **Page budget and memory pressure.** Even eligible pages get evicted under memory pressure or when too many tabs compete; this is normal and should not be chased — optimize what you control.

## Monitoring with notRestoredReasons

1. **Read the API in RUM.** PerformanceNavigationTiming exposes notRestoredReasons, an object with src (your frame or an iframe), dest, and reasons[] covering why a back navigation did not restore. Log the reason list with your web-vitals beacon, keyed by route.
2. **The presence of reasons is the signal.** Per the spec discussion, the old blocked/prevented booleans are gone; treat any non-empty reasons array as actionable and dedupe counts by reason code, not by raw events.
3. **Distinguish yours versus third-party.** If src identifies an iframe, the fix belongs to that vendor; track these separately so a chat widget's WebSocket does not get triaged as your bug — and file it with the vendor instead.
4. **Watch restore rate, not just reasons.** Compute navigations.type === 'back_forward' with a non-null notRestoredReasons versus restores without reasons. A rising blocked rate after a release is a regression signal exactly like a rising error rate.

## Remediation playbook

1. **Grep for unload.** Audit the codebase and every third-party snippet for window unload and beforeunload listeners beforeunload is allowed but still discourage reflexive use; each removal directly restores eligibility on those routes.
2. **Centralize lifecycle.** Route all "on page close" logic through one helper that binds pagehide (and visibilitychange for app-lifecycle concerns), so no future PR can reintroduce an unload listener silently. Enforce with a lint rule.
3. **Re-validate freshness on restore.** Bfcache can serve a stale snapshot for minutes. Listen for pageshow with persisted === true, then decide: revalidate critical data (session, unseen-badge counts) in the background, and for time-sensitive screens consider a lightweight staleness banner rather than blocking the restore.
4. **Snapshot-aware UI.** Animations, countdowns, and live regions resume mid-state after restore; reset or resync them in pageshow instead of assuming a fresh load path ran.
5. **Test bfcache locally.** Chrome DevTools has a back-forward cache checkbox in the Application panel that forces eligibility checking; Lighthouse's bfcache audit surfaces top blockers in CI so regressions are caught before field data shows them.

## Edge cases worth knowing

1. **Bfcache restores do not run your bundle.** No re-download, no re-parse, no re-hydration — which also means load-time side effects (analytics "page load" pings) will not fire; use the pageshow persisted flag for view tracking or your metrics undercount back/forward traffic.
2. **Media and timers.** Audio/video elements and pending setTimeout chains are frozen at entry and resumed at restore; pause or clear them deliberately if that is wrong for your UX.
3. **SPAs are not exempt.** History-API navigations inside a single document do not use bfcache (the page never unloads), but users leaving to an external page and coming back do — so the same blockers apply to your shell even if routing is client-side.
