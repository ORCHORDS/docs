# Event Timing Interaction-ID Attribution

**Issue:** A single click or key press generates several DOM events, so treating each Event Timing entry independently can double-count interactions and misidentify the source of poor responsiveness.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Observe buffered `event` performance entries after feature detection. Group entries whose nonzero `interactionId` matches; pointerdown, pointerup, and click from one interaction can share the identifier, as can keydown and keyup. Compute the interaction latency from the relevant grouped entries rather than summing event durations.

Use `performance.interactionCount` when supported to apply the INP outlier rule correctly for long-lived pages. Sample and aggregate by coarse interaction target or product action, never raw user text or sensitive DOM paths. Correlate slow groups with Long Animation Frames or a sampled trace to identify script/render work.

## Verification

Generate clicks, drags, keyboard input, scrolling, synthetic events, nested frames, and long handlers. Confirm zero IDs are excluded, grouped sequences count once, and 50+ interactions exercise percentile behavior. Test route changes in long-lived apps, unsupported browsers, and telemetry limits.

## Gotchas

Scroll is not assigned an interaction ID. IDs are meaningful within the page lifecycle, not stable user identifiers. Event duration is quantized for privacy and includes time through next paint; it is not simply handler CPU time.

## Sources

- [MDN PerformanceEventTiming.interactionId](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceEventTiming/interactionId)
- [MDN performance.interactionCount](https://developer.mozilla.org/en-US/docs/Web/API/Performance/interactionCount)
- [W3C Event Timing](https://w3c.github.io/event-timing/)
