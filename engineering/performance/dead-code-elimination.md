# dead-code-elimination

**Issue:** Unused code paths inflate bundle size
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Dead code (unreachable branches, unused variables, deprecated feature flags) bloats bundles. Minifiers and tree shakers remove some automatically; the rest requires manual cleanup.

## Pattern / Solution
1. Remove feature-flagged code paths that are permanently enabled.\n2. Use ts-prune or eslint-plugin-unused-imports to surface dead TypeScript exports.\n3. Delete deprecated API wrappers once callers are migrated.\n4. Audit with Lighthouse Remove unused JavaScript and Remove unused CSS.\n5. Establish a sunset process for losing A/B test variants.

## Gotchas
- Minifiers can only eliminate provably unreachable code; dynamic patterns confuse them.\n- process.env.NODE_ENV replacements enable dead code elimination; ensure your bundler sets it.\n- A/B test code accumulates -- establish a sunset process for losing variants.

## Related
tree-shaking-optimization, javascript-bundle-size, lighthouse-scoring
