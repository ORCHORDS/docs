# css-container-queries

**Issue:** Component styling based on viewport width breaks when the component is in a narrow column
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A card component switches to a horizontal layout at md: breakpoint, but when placed in a sidebar it still uses the narrow layout despite having sufficient space.

## Pattern / Solution
```css
/* Define a containment context */
.card-wrapper {
  container-type: inline-size;
  container-name: card;
}

/* Query the container, not the viewport */
@container card (min-width: 400px) {
  .card { flex-direction: row; }
  .card__image { width: 120px; flex-shrink: 0; }
}

/* Size units relative to container */
.card__title { font-size: 5cqi; } /* 5% of container inline size */
```

## Gotchas
- container-type: inline-size is sufficient for width queries; size adds block-axis containment
- The element queried is the nearest ancestor with a containment context
- Supported in all modern browsers since 2023; no polyfill available

## Related
- `css-grid-layouts.md`
- `tailwind-responsive-design.md`
