# CSS intrinsic-size keyword animation

**Issue:** Expanding UI animates between a fixed length and `auto` by measuring DOM geometry in JavaScript, producing races and forced layout.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** progressive enhancement; newer CSS feature

CSS Values and Sizing define `interpolate-size` and `calc-size()` for transitions involving intrinsic sizing keywords. Use them as an enhancement around a correct open/closed state, with a nonanimated fallback.

**Sources:** [CSS Values Level 5 — interpolate-size](https://drafts.csswg.org/css-values-5/#interpolate-size) · [CSS Values Level 5 — calc-size()](https://drafts.csswg.org/css-values-5/#calc-size)

## Controls

- opt in at the narrowest component scope;
- animate one dimension with bounded overflow and stable surrounding layout;
- preserve DOM state, focus, and ARIA semantics independently of animation;
- honor `prefers-reduced-motion`;
- avoid mixing JS geometry writes with the CSS transition.

## Verification

Test dynamic content during transition, font loading, nested disclosures, reverse mid-animation, writing modes, reduced motion, and unsupported browsers. Profile layout and paint rather than assuming native interpolation is free.

## Gotchas

Intrinsic endpoints can change while content loads. A visually collapsed element may remain focusable. Draft syntax/support can change; feature-detect and recheck compatibility.
