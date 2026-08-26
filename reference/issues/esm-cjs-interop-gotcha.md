# esm-cjs-interop-gotcha

**Issue:** Mixing ESM and CommonJS modules causes `__dirname is not defined`, `require is not a function`, or default import wrapping issues
**Date:** 2026-08-11
**Status:** documented

## Symptom
`ReferenceError: __dirname is not defined in ES module scope` when migrating to `"type": "module"`. Or `import foo from 'cjs-package'` imports `{ default: { default: ... } }` — double-wrapped default.

## Root cause
ESM does not have `__dirname`, `__filename`, or `require`. When a CJS package is imported into ESM, bundlers and Node.js add a synthetic `default` export wrapping the `module.exports` object. Some older bundler versions double-wrap it.

## Fix
```ts
// Replace __dirname in ESM
import { fileURLToPath } from 'url';
import { dirname } from 'path';
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Fix double-default import
import _foo from 'cjs-package';
const foo = (_foo as any).default ?? _foo;
```
In `tsconfig.json`, set `"esModuleInterop": true` and `"module": "NodeNext"` for correct interop.

## Detection
```
grep -rn "__dirname\|__filename\|require(" src/ --include="*.ts" | grep -v "// cjs"
```

## Related
- `import-cycle-detection.md`
- `vite-env-types-conflict.md`
