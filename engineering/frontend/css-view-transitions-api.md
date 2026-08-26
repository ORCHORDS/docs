# css-view-transitions-api

**Issue:** Animated page transitions require complex JS orchestration
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Route changes hard-cut with no transition; adding animated transitions requires managing two DOM trees simultaneously.

## Pattern / Solution
```ts
// Trigger a view transition
document.startViewTransition(async () => {
  await navigateTo('/new-page'); // update the DOM
});
```

```css
/* Default cross-fade override */
::view-transition-old(root) {
  animation: 200ms ease both fade-out;
}
::view-transition-new(root) {
  animation: 200ms ease both fade-in;
}

/* Named element transition */
.hero-image {
  view-transition-name: hero;
}
::view-transition-old(hero),
::view-transition-new(hero) {
  object-fit: cover;
}
```

## Gotchas
- Only supported in Chrome 111+; wrap in if (document.startViewTransition) check
- Next.js App Router integration uses the experimental viewTransition flag
- view-transition-name must be unique across the page during transition

## Related
- `css-animation-performance.md`
- `next-js-app-router-patterns.md`
