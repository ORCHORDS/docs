# CSS corner-shape progressive enhancement

**Issue:** CSS Borders Level 4 drafts `corner-shape` for bevel, notch, scoop, and superellipse-like corners. It changes painted geometry but cannot be assumed to change semantics, hit testing, focus visibility, or clipping consistently across evolving implementations.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** experimental

## Controls and implementation
Use it only as decoration behind `@supports`, with ordinary `border-radius` fallback. Keep interactive hit areas and focus rings inside the stable box; pair deliberate clipping with `overflow`/clip-path tests rather than assuming the corner shape clips descendants. Use logical design tokens and bound extreme superellipse values.

## Verification
Test unsupported engines, zoom, forced colors, focus, shadows, backgrounds, overflow, nested radii, animation, print, RTL, and pointer hits at shaped corners. Content and controls must remain usable without the feature.

## Gotchas
The syntax is draft and may change. Painted shape, overflow clip, outline, and pointer region are separate concepts.

## Sources
- W3C CSSWG, [CSS Borders and Box Decorations Level 4](https://www.w3.org/TR/css-borders-4/)
- W3C, [WCAG 2.2 Focus Appearance](https://www.w3.org/TR/WCAG22/#focus-appearance)
