# css-performance-containment

**Issue:** Browser recalculates layout and paint for the whole page on local changes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CSS Containment (contain property) tells the browser that a subtree is independent from the rest of the document, allowing it to skip layout/paint/style recalculations outside the contained element.

## Pattern / Solution
1. contain: layout -- changes inside don't affect external layout.\n2. contain: paint -- contents don't display outside the element; enables paint isolation.\n3. contain: strict -- equivalent to layout paint style size.\n4. content-visibility: auto -- skips rendering off-screen elements entirely.\n5. Use on repeated elements: cards, list items, widgets.

## Gotchas
- contain: size requires explicit dimensions; without it the element collapses.\n- content-visibility: auto causes CLS on first scroll if element heights are unknown; add contain-intrinsic-size.\n- Containment breaks position: fixed children from escaping the container.

## Related
layout-thrashing-prevention, css-will-change-property, dom-manipulation-performance
