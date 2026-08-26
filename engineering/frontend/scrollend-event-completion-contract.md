# Scrollend event completion contract

**Issue:** An interface infers that scrolling stopped from a fixed debounce timer. Slow input, snap animation, programmatic scrolling, zoomed visual-viewport motion, or an interrupted gesture makes the timer fire too early or too late, so expensive work and focus changes occur while the page is still moving.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

CSSOM View defines scrollend for Document, Element, and VisualViewport targets. It represents completion of a scroll operation after scrolling and related input updates have ended. It is useful for state synchronization that truly belongs after motion, such as committing a snapped item or issuing a low-priority measurement.

Do not move ordinary scroll-linked visuals to scrollend; they need continuous or declarative scroll-driven behavior. Do not use completion as permission to surprise the user with focus, navigation, or layout changes.

## Controls and implementation

1. Attach the listener to the object that actually scrolls. A nested element, the document viewport, and the visual viewport are separate targets and can finish at different times.
2. Feature-detect the event on the relevant target. Keep a bounded debounce fallback for unsupported engines and label fallback telemetry separately because its semantics are approximate.
3. Treat scrollend as a notification, not a unique transaction identifier. Multiple scroll operations can coalesce, be interrupted, or complete with a different final position than first requested.
4. On receipt, read the current scroll position and current application state. Reject stale work by comparing a generation or target identifier rather than assuming the originally requested destination won.
5. Use passive scroll listeners for any continuous observation and keep both scroll and scrollend handlers small. Schedule nonessential network or analytics work independently from UI correctness.
6. Account for scroll snap, smooth programmatic scrolls, touch gestures, keyboard input, scrollbar manipulation, and visual-viewport changes caused by pinch zoom or on-screen keyboards.
7. Avoid interpreting lack of an event as proof that the page is still scrolling. A request that caused no position change need not produce the same sequence as an actual scroll.

## Verification

Exercise document and nested scrollers, horizontal and RTL scrolling, snap points, instant and smooth scrollTo, wheel, touch, keyboard, scrollbar drag, pinch zoom, dynamic content, overscroll, interrupted animations, hidden tabs, and removed targets.

Assert post-scroll actions read the final position, fire at most once per application generation, and do not steal focus. Compare native and fallback cohorts on supported browsers without claiming identical timing.

## Gotchas

- scrollend is about completed scrolling, not a generic idle signal.
- A zero-distance request and a clamped boundary may not create a meaningful scroll.
- VisualViewport motion can differ from layout-viewport motion on mobile.
- Debounce duration is a heuristic and must remain a fallback, not the normative contract.

## Official sources

- [CSSOM View Module — scrollend](https://w3c.github.io/csswg-drafts/cssom-view/#eventdef-document-scrollend)
- [CSSOM View Module — Scrolling events](https://w3c.github.io/csswg-drafts/cssom-view/#scrolling-events)
