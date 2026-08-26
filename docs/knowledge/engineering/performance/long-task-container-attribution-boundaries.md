# Long Task Container Attribution Boundaries

**Issue:** A long-task duration identifies blocked main-thread time but teams can wrongly blame a script when attribution only identifies a browsing-context container.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Observe buffered `longtask` entries and inspect their attribution records. Use `containerType`, `containerName`, `containerId`, and `containerSrc` only to classify the responsible top-level window or iframe context. Strip URL queries/fragments and cap cardinality before telemetry.

Correlate a long task with Event Timing, Long Animation Frames, route state, and a sampled performance trace. For same-origin owned contexts, profile actual functions. For cross-origin frames, use vendor controls, loading strategy, and contractual performance budgets; do not infer unavailable internal code.

Sample and batch records so instrumentation does not add main-thread pressure. Track total blocking contribution and user impact, not merely task count.

## Verification

Create owned top-level work, same-origin iframe work, cross-origin iframe work, worker activity, and browser-extension interference. Confirm expected attribution or privacy-limited labels. Test iframe renaming/removal, URL redaction, buffered startup entries, and browsers without the API.

## Gotchas

Attribution is container-level, not a stack trace. Worker work is not main-thread long-task attribution. Cross-origin privacy restrictions deliberately limit detail. A 49 ms task can still contribute to poor interactions in aggregate.

## Sources

- [MDN PerformanceLongTaskTiming](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceLongTaskTiming)
- [MDN TaskAttributionTiming](https://developer.mozilla.org/en-US/docs/Web/API/TaskAttributionTiming)
- [W3C Long Tasks API](https://w3c.github.io/longtasks/)
