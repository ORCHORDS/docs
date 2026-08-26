# Long Animation Frame Script Attribution

**Issue:** Long tasks show main-thread blocking but can miss the user-visible frame context and do not directly reveal which script activity dominated a slow animation frame.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Observe `long-animation-frame` entries with `PerformanceObserver` after feature detection. Record duration, blocking duration, render start, and a bounded list of script attribution fields. Aggregate by owned script URL and entry-point function; avoid shipping unbounded raw entries or query-bearing URLs.

Use Long Animation Frames to select traces and reproduce user interactions, not as a complete profiler. Attribution covers main-thread scripts including same-origin frames, but not cross-origin frames, workers, service workers, or extensions. The reported function is an entry point, not necessarily the deepest slow function.

Set sampling and payload limits, strip sensitive URL components, and align timestamps with INP and interaction telemetry. Fix by reducing synchronous work, yielding/chunking, avoiding layout thrash, and limiting third-party execution—then remeasure correctness and responsiveness.

## Verification

Create controlled slow event handlers, render work, same-origin iframe work, cross-origin iframe work, and worker load. Confirm expected visibility and attribution gaps. Test observer buffered behavior, route changes, sampling, URL redaction, and unsupported browsers. Compare entries with a DevTools performance trace before assigning ownership.

## Gotchas

The API is experimental and not Baseline. Absence of script attribution does not mean script was uninvolved. Instrumentation and serialization must remain lightweight or monitoring can worsen responsiveness.

## Sources

- [MDN Long Animation Frame timing](https://developer.mozilla.org/en-US/docs/Web/API/Performance_API/Long_animation_frame_timing)
- [MDN script attribution](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceLongAnimationFrameTiming/scripts)
- [W3C Long Animation Frames](https://w3c.github.io/long-animation-frames/)
