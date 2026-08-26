# CSS scrollbar-gutter and layout stability

**Issue:** Content width shifts when overflow introduces a classic scrollbar, moving controls and causing avoidable layout instability.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented with platform-dependent scrollbar behavior

CSS Overflow defines `scrollbar-gutter` to reserve space for classic scrollbars. Apply it to the actual scroll container when stable geometry matters, while accepting that overlay scrollbars consume no gutter.

**Source:** [CSS Overflow Level 3 — scrollbar-gutter](https://drafts.csswg.org/css-overflow-3/#scrollbar-gutter-property)

## Controls

- use `stable` only on intentional scroll containers;
- consider `both-edges` when symmetric centering is required;
- use logical layout so gutter placement follows writing direction;
- avoid forcing scrollbars merely to reserve space;
- test nested containers and viewport/root propagation.

## Verification

Cover short/long content, classic/overlay scrollbars, RTL, vertical writing, zoom, OS preference changes, and modal scroll locking. Measure CLS and verify reserved space does not create unwanted asymmetry.

## Gotchas

Scrollbar width is user-agent/platform controlled. Overlay systems may show no visible reservation. This does not solve shifts caused by content, fonts, or viewport-unit changes.
