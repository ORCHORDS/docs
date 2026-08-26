# CSS light-dark system color contract

**Issue:** A component switches themes with duplicated media-query rules and produces unreadable combinations when embedded under a different color scheme.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** progressive enhancement

CSS Color defines `light-dark()`, selected according to the used color scheme. Declare supported schemes and centralize semantic color tokens rather than scattering theme-specific declarations.

**Sources:** [CSS Color Level 5 — light-dark()](https://drafts.csswg.org/css-color-5/#light-dark) · [CSS Color Adjustment — color-scheme](https://drafts.csswg.org/css-color-adjust-1/#color-scheme-prop)

## Controls

- declare `color-scheme` at the appropriate root/component;
- pair foreground, background, border, focus, and disabled tokens;
- allow forced colors and user-agent controls to adapt;
- provide fallback declarations before `light-dark()`;
- never encode status solely by color.

## Verification

Test light, dark, forced colors, unsupported engines, nested scheme overrides, form controls, focus, visited links, print, and contrast at zoom. Ensure hydration does not flash an unreadable theme.

## Gotchas

`prefers-color-scheme` reports preference; `color-scheme` establishes rendering context. A dark background alone does not make a dark scheme. Contrast must be verified in both branches.
