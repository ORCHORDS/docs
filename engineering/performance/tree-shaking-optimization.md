# tree-shaking-optimization

**Issue:** Dead exports from modules are bundled into production
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tree shaking removes unused ES module exports at build time. It requires ES modules (not CommonJS) and correct sideEffects configuration.

## Pattern / Solution
1. Use named imports: import { debounce } from 'lodash-es' not import _ from 'lodash'.\n2. Mark side-effect-free packages in package.json: sideEffects: false.\n3. Ensure your own code uses ES module syntax.\n4. Use Rollup or esbuild for library builds; Webpack for apps.\n5. Verify with bundle analyzer that unused exports are absent.

## Gotchas
- CommonJS (require) is not tree-shakeable; prefer ESM versions of libraries.\n- CSS-in-JS and polyfill files often have side effects; whitelist them in sideEffects array.\n- TypeScript's enum compiles to CJS-like code; use const enum or string unions instead.

## Related
javascript-bundle-size, dead-code-elimination, module-federation
