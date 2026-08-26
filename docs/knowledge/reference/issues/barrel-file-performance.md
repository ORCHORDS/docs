# barrel-file-performance

**Issue:** Barrel files (`index.ts` that re-exports everything) cause slow TypeScript compilation and large bundle sizes due to importing entire modules when only one export is needed
**Date:** 2026-08-11
**Status:** documented

## Symptom
`tsc` is slow. Bundle size is larger than expected. Importing a single utility from `@/utils` pulls in the entire utils module tree. Tree-shaking fails because side effects in re-exported modules prevent elimination.

## Root cause
A barrel `export * from './a'; export * from './b'; export * from './c'` causes TypeScript to load and type-check all three modules transitively, even if only one export is used. Bundlers may tree-shake successfully but TypeScript's language server still processes all files.

## Fix
1. Import directly from the source file: `import { fn } from '@/utils/fn'` instead of `import { fn } from '@/utils'`.
2. Use `verbatimModuleSyntax` in `tsconfig.json` to enable better tree-shaking.
3. If barrels are needed, mark side-effect-free files in `package.json`: `"sideEffects": false`.
4. Audit barrels with `@typescript-eslint/no-restricted-imports` to ban deep barrel re-exports.

## Detection
```
grep -rn "export \*" src/ --include="*.ts"
```
Each `export *` in an `index.ts` is a potential barrel.

## Related
- `import-cycle-detection.md`
- `typescript-template-literal-union-too-wide.md`
