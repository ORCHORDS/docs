# jest-esm-transform-config

**Issue:** Jest fails to run ESM modules without the correct transform configuration, throwing `SyntaxError: Cannot use import statement in a module`
**Date:** 2026-08-11
**Status:** documented

## Symptom
`SyntaxError: Cannot use import statement outside a module` when running Jest tests that import an ESM-only package or use top-level `import` syntax.

## Root cause
Jest runs in CommonJS mode by default and uses `babel-jest` or `ts-jest` to transform files. ESM packages in `node_modules` are not transformed by default (`transformIgnorePatterns` excludes `node_modules`). When an untransformed ESM file is required, Node's CJS loader throws.

## Fix
```js
// jest.config.js
export default {
  extensionsToTreatAsEsm: ['.ts'],
  transform: {
    '^.+\\.tsx?$': ['ts-jest', { useESM: true }],
  },
  transformIgnorePatterns: [
    // Allow transforming ESM-only packages
    'node_modules/(?!(esm-only-package|another-esm-pkg)/)',
  ],
  moduleNameMapper: {
    '^(\\.{1,2}/.*)\\.js$': '$1', // strip .js for TypeScript imports
  },
};
```
Or migrate to Vitest, which supports ESM natively.

## Detection
```
grep -rn "transformIgnorePatterns" jest.config.*
```
If the list is empty or only `node_modules`, ESM packages will fail.

## Related
- `vitest-module-mock-hoisting.md`
- `esm-cjs-interop-gotcha.md`
