# content-visibility auto-state work pausing

**Issue:** `content-visibility: auto` can skip layout and paint for irrelevant content, but application code may continue expensive canvas, animation, or polling work offscreen.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented — newly available; support older browsers safely

## Decision

Use `contentvisibilityautostatechange` as a performance hint to pause non-semantic rendering work while `event.skipped` is true. Never use it to stop correctness-critical data or semantic DOM updates.

## Controls

- Feature-detect the event and retain normal behavior without it.
- Make pause/resume idempotent.
- Cancel animation frames, timers, or rendering loops owned by the component.
- Keep accessible names, live data semantics, and essential state current.
- Resume from authoritative state rather than replaying every missed frame.
- Tear down listeners with component lifecycle.
- Avoid network reconnect storms when many sections become relevant.
- Measure saved CPU and regressions instead of assuming benefit.

## Verification

Test rapid scrolling, focus/navigation into skipped content, find-in-page, assistive technology, tab backgrounding, DOM removal, repeated events, and unsupported browsers. Assert no lost user state and no duplicate render loops after resume.

## Gotchas

“Skipped” describes rendering work, not semantic irrelevance. Browser relevance decisions are implementation-controlled. Pausing essential updates can create stale or inaccessible experiences.

## Sources

- [CSS Containment Level 2 auto-state event](https://www.w3.org/TR/css-contain-2/#content-visibility-auto-state-change)
- [MDN contentvisibilityautostatechange](https://developer.mozilla.org/en-US/docs/Web/API/Element/contentvisibilityautostatechange_event)
