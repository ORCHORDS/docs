# bfcache Not-Restored Reasons Field Diagnostics

**Issue:** Back/forward navigations that miss the back-forward cache feel like full reloads, but aggregate timing alone does not identify which frame or API blocked restoration.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

On a history navigation, inspect `PerformanceNavigationTiming.notRestoredReasons` when supported. Preserve its frame tree and reason codes so a blocker in a same-origin iframe is not incorrectly blamed on the top document. Distinguish three states: an object with reasons, `null` when not applicable or unavailable for that navigation, and `undefined` when the property is unsupported.

Collect only an allowlisted, privacy-reviewed subset. Hash or classify URLs and frame identifiers rather than exporting sensitive paths. Correlate reasons with navigation type, release, browser version, and bfcache outcome. Prioritize fixable recurring blockers such as unload handlers or cache-control choices; never remove security or correctness behavior merely to raise hit rate.

## Verification

Automate A→B→Back flows for clean pages and fixtures containing each owned blocker. Confirm restored pages receive `pageshow` with `persisted=true`, timers/network connections resume correctly, and stale authenticated state is revalidated. Test nested frames, same- and cross-origin frames, duplicated tabs, process restart, memory pressure, and browsers without the API.

## Gotchas

Not every reason is actionable or disclosed, particularly for cross-origin frames. A `back_forward` navigation type does not prove a bfcache hit. Lab eligibility is not a field hit rate because browser resource pressure can evict entries.

## Sources

- [MDN notRestoredReasons](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceNavigationTiming/notRestoredReasons)
- [MDN monitoring bfcache blocking reasons](https://developer.mozilla.org/en-US/docs/Web/API/Performance_API/Monitoring_bfcache_blocking_reasons)
- [Navigation Timing Level 2](https://w3c.github.io/navigation-timing/)
