# css-cascade-layers

**Issue:** Third-party CSS specificity wars with application styles require !important hacks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A UI library's button styles override application overrides despite lower specificity selectors.

## Pattern / Solution
```css
/* Declare layer order at top of stylesheet */
@layer reset, base, components, utilities;

@layer reset {
  *, *::before, *::after { box-sizing: border-box; }
}

@layer base {
  a { color: inherit; }
}

@layer components {
  .button { padding: 8px 16px; background: blue; }
}

/* Later layers win regardless of specificity */
@layer utilities {
  .mt-4 { margin-top: 1rem !important; } /* rarely needed */
}

/* Import third-party into a layer to contain it */
@import url('library.css') layer(vendor);
```

## Gotchas
- Unlayered styles always win over layered styles regardless of order
- Layer order is determined by first @layer declaration, not definition
- Supported in all modern browsers since 2022

## Related
- `css-custom-properties-theming.md`
- `css-in-js-tradeoffs.md`
