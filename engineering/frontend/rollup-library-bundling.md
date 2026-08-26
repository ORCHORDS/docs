# rollup-library-bundling

**Issue:** Building a reusable library that works in both ESM and CJS environments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A component library published to npm does not tree-shake in consumer projects.

## Pattern / Solution
```js
// rollup.config.js
import { defineConfig } from 'rollup';
import typescript from '@rollup/plugin-typescript';

export default defineConfig({
  input: 'src/index.ts',
  external: ['react', 'react-dom'],
  output: [
    { file: 'dist/index.cjs', format: 'cjs', exports: 'named' },
    { file: 'dist/index.js', format: 'esm' },
  ],
  plugins: [typescript()],
});
```

```json
// package.json
{
  "main": "dist/index.cjs",
  "module": "dist/index.js",
  "exports": {
    ".": { "import": "./dist/index.js", "require": "./dist/index.cjs" }
  },
  "sideEffects": false
}
```

## Gotchas
- sideEffects: false enables tree-shaking in consumer bundlers
- Mark peer dependencies as external to avoid bundling them
- preserveModules: true for per-file output; better tree-shaking for component libraries

## Related
- `vite-plugin-development.md`
- `tree-shaking-patterns.md`
