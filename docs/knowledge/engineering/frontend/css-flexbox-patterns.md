# css-flexbox-patterns

**Issue:** Common flexbox alignment gotchas and layout patterns
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Items don't align as expected; flex children overflow their container; baseline alignment is off.

## Pattern / Solution
```css
/* Centering */
.center { display: flex; align-items: center; justify-content: center; }

/* Sticky footer */
.page { display: flex; flex-direction: column; min-height: 100vh; }
.main { flex: 1; }

/* Equal-width columns */
.cols > * { flex: 1; min-width: 0; } /* min-width:0 prevents overflow */

/* Space between with wrapping */
.tags { display: flex; flex-wrap: wrap; gap: 8px; }

/* Baseline alignment for mixed font sizes */
.label-input { display: flex; align-items: baseline; gap: 8px; }
```

## Gotchas
- min-width: 0 on flex children is required to allow text truncation with overflow:hidden
- flex: 1 shorthand sets flex-grow:1 flex-shrink:1 flex-basis:0%; not the same as flex: 1 1 auto
- align-content only applies when flex-wrap: wrap causes multiple lines

## Related
- `css-grid-layouts.md`
- `tailwind-responsive-design.md`
