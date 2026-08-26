# vite-env-types-conflict

**Issue:** Vite's `import.meta.env` types conflict with TypeScript's `lib.dom.d.ts` or `@types/node`, causing type errors or missing type completions
**Date:** 2026-08-11
**Status:** documented

## Symptom
`Property 'env' does not exist on type 'ImportMeta'` or `import.meta.env.VITE_API_URL` is typed as `any`. Adding a custom env variable to `env.d.ts` is ignored or causes duplicate identifier errors.

## Root cause
Vite augments `ImportMeta` via its own type definitions in `vite/client`. If `/// <reference types="vite/client" />` is missing from `env.d.ts` or `tsconfig.json` doesn't include it, the augmentation doesn't apply. Alternatively, `@types/node` ships an `ImportMeta` definition that conflicts.

## Fix
In `src/env.d.ts`:
```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_FEATURE_FLAG: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```
Ensure `tsconfig.json` includes `src/env.d.ts` and does NOT set `"types": ["node"]` globally (use per-file triple-slash references for node types instead).

## Detection
```
grep -rn "import.meta.env" src/ --include="*.ts"
```
Check that `env.d.ts` exists and contains the `/// <reference types="vite/client" />` directive.

## Related
- `pages-build-env-vars-vs-runtime.md`
- `esm-cjs-interop-gotcha.md`
