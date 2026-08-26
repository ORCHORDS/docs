# import-cycle-detection

**Issue:** Circular imports cause module values to be `undefined` at the point they are first accessed, producing cryptic runtime errors
**Date:** 2026-08-11
**Status:** documented

## Symptom
A class or function imported from another module is `undefined` at runtime even though TypeScript compiles without errors. The import works in isolation but fails when module A imports module B and B imports module A.

## Root cause
ESM and CommonJS both handle circular imports by returning the partially-initialized module. If module A imports from B while B is still being evaluated, B's exports may not yet be defined. TypeScript's type checker resolves types statically and does not detect the runtime `undefined`.

## Fix
1. Extract the shared dependency into a third module (C) that neither A nor B imports from.
2. Move the import inside the function body to defer it until after both modules are initialized.
3. Use dependency injection to break the cycle.

## Detection
```bash
npx madge --circular src/
```
Or use eslint-plugin-import rule `import/no-cycle`.

## Related
- `barrel-file-performance.md`
- `esm-cjs-interop-gotcha.md`
