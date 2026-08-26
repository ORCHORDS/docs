# long-animation-frames-loaf

**Issue:** INP regressions are investigated with the Long Tasks API, which only reports that "a task over 50ms happened" with no reliable way to attribute it to a script, and misses long frames caused by style/layout/paint work that follows a short task. Teams waste days bisecting code that the API cannot name. The Long Animation Frames API (LoAF) fixes this: it reports whole slow frames with per-script attribution and a rendering-phase breakdown, turning INP debugging from guesswork into a lookup.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why LoAF Supersedes Long Tasks

1. **Frames, not tasks.** A long animation frame is the full unit of jank the user sees: input handling, script execution, style recalc, layout, and paint. The Long Tasks API only surfaced the task portion, so 40ms of script followed by 80ms of layout was invisible to it while still dropping the frame.
2. **Per-script attribution.** Each LoAF entry carries a `scripts` array where every script reports its `name`, `invoker`, `invokerType` (event listener, Promise reaction, script parsing), `sourceURL`, `sourceFunctionLocation`, and `sourceCharLocation`. This is the difference between "something was slow" and "line 412 of vendor-chat-widget.js was slow".
3. **Render-phase breakdown.** `renderStart`, `styleAndLayoutStart`, and `forcedStyleAndLayoutCount` (forced reflow count) expose layout thrashing inside the frame. A frame that is fast in script but slow in style/layout points to CSS/DOM problems, not JS problems — a completely different fix path.
4. **Interaction awareness.** Entries include `firstUIEventTimestamp` and `blockingDuration`, letting you distinguish frames that overlapped a user interaction (INP-relevant) from background churn (annoying but not scored).

## Observing LoAF in Production

1. **Basic observer.** `new PerformanceObserver(cb).observe({ type: 'long-animation-frame', buffered: true })` with a 50ms default threshold; entries are `PerformanceLongAnimationFrameTiming` objects. Always feature-detect — Safari/Firefox lag Chromium here.
2. **Buffering and late subscription.** The `buffered: true` flag replays frames that occurred before your observer registered (during hydration, for example). Without it you silently miss the worst window of the page lifecycle.
3. **Sampling and rate limiting.** RUM integration should cap LoAF reporting (for example, top 10 frames per page view, or frames over 150ms only) because a pathological page can emit hundreds of entries, inflating beacon payloads.
4. **Correlate with INP interactions.** Join LoAF entries to `event` entries by startTime/endTime overlap; the frames containing the slowest interaction's input processing and its next rendered frame are your INP culprits. DebugBear and SpeedCurve both ship this correlation in their RUM products.
5. **Report attribution, not just duration.** Log `invokerType`, source host (first-party vs third-party split on `sourceURL`), and `forcedStyleAndLayoutCount` alongside duration — duration alone reproduces the Long Tasks dead end.

## INP Debugging Workflow

1. **Reproduce with DevTools first.** Chrome DevTools Performance panel shows long frames with script attribution natively; confirm locally before trusting field data, since one user's slow device can dominate a local-only analysis.
2. **Split by invoker type.** `invokerType: 'event-listener'` points at a handler (split it with `scheduler.yield()` or move work to idle); `'promise'` reactions point at chain waterfalls; script-parsing entries point at oversized bundles being compiled on the main thread.
3. **Check the style/layout tail.** If `renderStart` is late relative to script end and `forcedStyleAndLayoutCount` is high, the fix is layout containment or batching DOM reads/writes, not JS optimization.
4. **Attribute third-party frames.** Group LoAF script entries by `sourceURL` registrable domain and hand marketing a ranked list (chat widget: 210ms/frame average) — vendor conversations need numbers.

## Gotchas

1. **Browser support is Chromium-first.** Chrome and Edge support LoAF; treat it as a Chromium-weighted diagnostic signal, not a complete field picture. The web-platform-tests interop effort pushed adoption during 2025, but verify current status before depending on attribution fields.
2. **Threshold is fixed at 50ms.** You cannot raise or lower the reporting threshold; filter client-side if you only care about 100ms+ frames.
3. **A long frame is not always a long task.** Teams porting Long Tasks alerting to LoAF see "new" slow frames that were always there — hidden render time — and mistake them for regressions. Rebaseline before alerting.
4. **Source locations can be minified.** `sourceURL`/`sourceCharLocation` are only useful when production builds ship source maps; upload maps to your error-tracking/RUM vendor or attribution resolves to `foo.aff4c.js:1:48211`.

## Related

long-task-detection, web-vitals-inp-2026, inp-optimization, scheduler-yield-api, third-party-script-impact
