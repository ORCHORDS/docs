# Resource Timing Render-Blocking Status Audit

**Issue:** Teams often guess which scripts, styles, and fonts delayed first render, causing ineffective preloads or unsafe deferral.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Collect buffered `resource` entries and inspect `PerformanceResourceTiming.renderBlockingStatus` after feature detection. Correlate blocking status with initiator type, start/response timing, transfer size, delivery type, LCP, and render milestones. Treat it as evidence a resource could block, not proof it dominated the critical path.

For owned resources, test removal, defer/async/module strategy, stylesheet splitting, font behavior, or a precisely matching preload. Retain dependency and correctness ordering. Avoid broad preloads; every preload competes for bandwidth and must match the eventual request's URL, type, CORS, and media.

Aggregate sanitized origins/path classes rather than sensitive URLs. Resource Timing visibility for cross-origin details requires the server's Timing-Allow-Origin policy.

## Verification

Compare before/after traces on cold cache, warm cache, slow network/CPU, page variants, and unsupported browsers. Confirm no duplicate preload, FOUC, hydration race, font regression, or CSP/SRI breakage. Measure real LCP/paint change rather than only status counts.

## Gotchas

The property is not Baseline. `blocking` means potentially render blocking, not that deferral is safe. Dynamically inserted resources and browser heuristics can differ from static assumptions.

## Sources

- [MDN renderBlockingStatus](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceResourceTiming/renderBlockingStatus)
- [MDN Resource Timing](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceResourceTiming)
- [W3C Resource Timing](https://w3c.github.io/resource-timing/)
