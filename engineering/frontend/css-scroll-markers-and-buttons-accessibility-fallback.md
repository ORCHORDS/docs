# CSS scroll markers and buttons accessibility fallback

**Issue:** Script-built carousel controls frequently lose disabled state, focus order, writing-mode behavior, or synchronization with the current scroll target. CSS Overflow Level 5 proposes generated controls but remains a draft.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** experimental First Public Working Draft — progressive enhancement only

## Decision

Retain semantic links or buttons as the production baseline. Evaluate `::scroll-marker`, `::scroll-marker-group`, `:target-current`, and `::scroll-button()` only as an optional layer with a tested fallback.

## Controls

- Preserve meaningful content and navigation without generated pseudo-elements.
- Use flow-relative directions and test writing modes.
- Provide accessible labels and visible focus indicators.
- Do not create duplicate tab stops when native and fallback controls coexist.
- Respect reduced motion and user scrolling preferences.
- Ensure offscreen or virtualized targets remain reachable.
- Treat disabled/end-of-range state as browser-controlled only when support is proven.
- Keep an experiment kill switch.

## Verification

Test keyboard, touch, screen reader, zoom, RTL/vertical writing, smooth scrolling, reduced motion, nested scrollers, target removal, and unsupported browsers. Confirm focus moves toward relevant content after activation and all items remain reachable with CSS disabled.

## Gotchas

The specification is a draft and details may change. Generated controls are not DOM elements available to every automation strategy. Carousel usability still requires sensible content structure and sizing.

## Sources

- [W3C CSS Overflow Module Level 5](https://www.w3.org/TR/css-overflow-5/)
- [CSSWG Editor’s Draft: Scroll navigation controls](https://drafts.csswg.org/css-overflow-5/#scroll-controls)
