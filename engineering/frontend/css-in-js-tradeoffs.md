# css-in-js-tradeoffs

**Issue:** Runtime CSS-in-JS adds bundle size and hydration cost; zero-runtime options have constraints
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
styled-components adds 15 KB and causes a flash of unstyled content during SSR hydration.

## Pattern / Solution
```
Runtime (styled-components, Emotion):
  + Dynamic styles based on props at runtime
  - Adds bundle size (~15-20 KB)
  - Serializes styles on every render
  - SSR hydration mismatch risk

Zero-runtime (vanilla-extract, Linaria, Panda CSS):
  + Static CSS extraction at build time
  + No runtime overhead
  - Props-based styles require pre-generated variants (recipe pattern)
  - Build step required
```

```ts
// vanilla-extract example
import { style } from '@vanilla-extract/css';
export const button = style({ padding: '8px 16px', borderRadius: 4 });
```

## Gotchas
- Emotion has a babel plugin for zero-runtime mode
- Panda CSS generates utility classes like Tailwind but from typed recipes
- For Server Components, runtime CSS-in-JS is incompatible without a client boundary

## Related
- `css-modules-patterns.md`
- `tailwind-component-patterns.md`
