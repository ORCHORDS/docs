# dynamic-import-patterns

**Issue:** Features load upfront instead of on demand
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Dynamic import() returns a Promise, allowing code to load asynchronously at runtime. It's the foundation of code splitting in modern bundlers.

## Pattern / Solution
1. Basic: const module = await import('./heavy-feature.js').\n2. React: const Chart = React.lazy(() => import('./Chart')) wrapped in Suspense.\n3. Prefetch on hover: attach import('./module') to mouseenter for predictive loading.\n4. Route-level: use framework conventions (Next.js dynamic(), React Router lazy routes).\n5. Use magic comments: import(/* webpackChunkName: chart */ './Chart') for readable chunk names.

## Gotchas
- Dynamic imports are async; handle loading and error states explicitly.\n- Bundlers cannot tree-shake inside dynamic imports if you use import * as foo.\n- SSR frameworks need special handling to avoid hydration mismatches with lazy components.

## Related
code-splitting-strategies, react-memo-patterns, module-federation
