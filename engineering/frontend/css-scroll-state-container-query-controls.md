# CSS Scroll-State Container Query Controls

**Issue:** JavaScript scroll listeners used only for visual state add main-thread work and can mis-handle sticky, snapped, or logical-direction behavior.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Declare the relevant element with `container-type:scroll-state` and optionally a stable container name. Use `@container ... scroll-state()` to style descendants based on:

- `scrollable`: more content is reachable in a direction;
- `scrolled`: the most recent scroll direction;
- `snapped`: a snap target is being selected;
- `stuck`: a sticky element is attached to an edge.

Prefer logical directions such as block-start and inline-end. Keep essential information visible without the query; use it for enhancement, not authorization, loading, or the only indication of state. Note that container queries style descendants, so add a wrapper when the container itself needs an apparent state.

## Verification

Test keyboard, wheel, touch, scrollbar drag, programmatic scroll, RTL, vertical writing, nested scrollers, overscroll, snap interruption, sticky boundaries, zoom/text expansion, reduced motion, and unsupported browsers. Confirm no visual flicker and no loss of accessible state.

## Gotchas

Scrollable means user-initiated scrolling is available in that direction, not simply that overflow exists. Snapped evaluation relates to snap events. A `none` stuck query can match a non-sticky element, so scope selectors carefully.

## Sources

- [MDN scroll-state queries](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Conditional_rules/Container_scroll-state_queries)
- [MDN @container](https://developer.mozilla.org/en-US/docs/Web/CSS/@container)
- [CSS Conditional Rules Level 5](https://drafts.csswg.org/css-conditional-5/)
