# tailwind-responsive-design

**Issue:** Responsive breakpoints in Tailwind behave mobile-first but are often misused
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A developer applies md: classes expecting them to apply only on tablet and is surprised they override mobile styles.

## Pattern / Solution
```html
<!-- Mobile first: base is mobile, breakpoints add overrides -->
<div class="flex flex-col md:flex-row lg:gap-8">
  <aside class="w-full md:w-64">Sidebar</aside>
  <main class="flex-1">Content</main>
</div>
```

```js
// Custom breakpoints
module.exports = {
  theme: {
    screens: {
      sm: '640px',
      md: '768px',
      lg: '1024px',
      xl: '1280px',
      '2xl': '1536px',
    },
  },
};
```

## Gotchas
- Breakpoints are min-width by default; use max-md: for max-width (Tailwind v3.2+)
- Avoid too many breakpoint variants; prefer container queries for component-level responsiveness
- Purge will only keep breakpoint classes seen in source; avoid string interpolation

## Related
- `css-container-queries.md`
- `tailwind-component-patterns.md`
