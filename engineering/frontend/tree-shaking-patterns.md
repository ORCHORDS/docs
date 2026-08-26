# tree-shaking-patterns

**Issue:** Importing a single utility from a large library bundles the entire library
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
import { merge } from 'lodash' pulls in 72 KB of lodash even though only one function is needed.

## Pattern / Solution
```ts
// BAD: imports entire library
import { merge } from 'lodash';

// GOOD: named import from ESM build
import merge from 'lodash-es/merge';

// GOOD: individual package
import merge from 'lodash.merge';

// Library authors: enable tree-shaking
// package.json
{
  "sideEffects": false,
  "exports": {
    ".": { "import": "./dist/index.js", "require": "./dist/index.cjs" }
  }
}
```

## Gotchas
- Tree-shaking only works with ESM (import/export); CJS (require) cannot be analysed statically
- sideEffects: false tells bundlers that no module has side effects; safe to drop unused exports
- Barrel files (index.ts that re-exports everything) defeat tree-shaking; use direct imports

## Related
- `bundle-analysis-webpack-bundle-analyzer.md`
- `rollup-library-bundling.md`
