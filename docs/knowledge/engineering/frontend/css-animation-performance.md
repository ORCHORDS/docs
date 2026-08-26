# css-animation-performance

**Issue:** CSS animations that trigger layout or paint cause jank
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Animating width and height causes continuous layout recalculations; scrolling is janky at 30fps.

## Pattern / Solution
```css
/* Compositor-only properties - no layout, no paint */
.slide-in {
  transform: translateX(-100%);
  opacity: 0;
  transition: transform 300ms ease, opacity 300ms ease;
  will-change: transform, opacity;
}
.slide-in.active {
  transform: translateX(0);
  opacity: 1;
}

/* Use scale instead of width/height */
.expand {
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform 200ms ease;
}

/* content-visibility for off-screen sections */
.below-fold { content-visibility: auto; }
```

## Gotchas
- will-change: transform promotes the element to its own compositor layer; use sparingly
- Animating top/left triggers layout; use transform: translate instead
- Prefer @keyframes over JS-driven animation for simple sequences

## Related
- `css-view-transitions-api.md`
- `browser-performance-api.md`
