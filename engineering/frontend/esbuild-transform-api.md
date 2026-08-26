# esbuild-transform-api

**Issue:** Running TypeScript or JSX transforms without a full bundler
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A CLI tool needs to execute user-provided TypeScript files at runtime without a build step.

## Pattern / Solution
```ts
import { transform, build } from 'esbuild';

// Single-file transform (no bundling)
const result = await transform(typescriptSource, {
  loader: 'tsx',
  target: 'node18',
  format: 'esm',
});
const code = result.code;

// Bundle with tree-shaking
await build({
  entryPoints: ['src/index.ts'],
  bundle: true,
  minify: true,
  format: 'esm',
  outfile: 'dist/index.js',
  external: ['react'],
});
```

## Gotchas
- esbuild strips types but does not type-check; run tsc --noEmit separately
- target: 'node18' enables modern APIs; use 'es2017' for broad browser support
- esbuild does not support all TypeScript features (e.g., const enum)

## Related
- `vite-config-patterns.md`
- `rollup-library-bundling.md`
