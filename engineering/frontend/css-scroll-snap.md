# css-scroll-snap

**Issue:** Custom carousel and scroll-paging implementations require complex JS scroll event tracking
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A horizontal product carousel implemented with JavaScript scroll listeners is janky and breaks on touch devices.

## Pattern / Solution
```css
/* Scroll snap container */
.carousel {
  display: flex;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
  gap: 1rem;
  padding: 1rem;
}

/* Snap each item */
.carousel__item {
  flex: 0 0 80%;
  scroll-snap-align: center;
  scroll-snap-stop: always; /* prevent skipping items */
}

/* Vertical full-page scroll */
.pages {
  height: 100vh;
  overflow-y: scroll;
  scroll-snap-type: y mandatory;
}
.page {
  height: 100vh;
  scroll-snap-align: start;
}
```

## Gotchas
- scroll-snap-type: mandatory forces snapping even when the user barely scrolls; proximity is gentler
- scroll-snap-stop: always prevents fast swipes from skipping multiple items
- Hiding scrollbars while keeping scroll functionality: scrollbar-width: none (Firefox), ::-webkit-scrollbar { display: none } (Chrome)
- Programmatic scrolling: use scrollIntoView({ behavior: 'smooth', block: 'nearest' })

## Related
- `css-flexbox-patterns.md`
- `react-virtual-list.md`
