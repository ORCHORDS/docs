# CSS contrast-color fallback policy

**Issue:** CSS Color Level 6 drafts `contrast-color()` to choose a contrasting color, but browser support and the algorithm's available palette do not guarantee a product's required WCAG contrast.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** experimental

## Controls and implementation

Use it only behind exact feature detection with a precomputed accessible fallback. Keep brand palettes bounded, test every state/background, and never use automatic contrast as the only indicator of state. Recompute fallback tokens in the build from measured color pairs.

## Verification

Test light/dark themes, transparency, gradients, forced colors, visited/disabled/focus states, unsupported engines, and zoom. Automated ratios need visual and forced-colors review.

## Gotchas

The draft algorithm and syntax may change; composited backgrounds can make a syntactically valid result insufficient.

## Sources

- W3C CSSWG, [CSS Color Level 6](https://www.w3.org/TR/css-color-6/)
