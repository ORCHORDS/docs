# JavaScript Tree Shaking and Dead Code Elimination

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

The production bundle includes code from `lodash`, `date-fns`, or
an internal component library that is never called at runtime.
Bundle analysis shows entire sub-modules included even though only
one or two functions are imported. Initial JS parse time on mobile
is elevated and the bundle fails the size budget check in CI.

## Context

Tree shaking removes unreachable (dead) code from a JavaScript
bundle. Bundlers determine reachability by statically analyzing
the import/export graph of ES modules. Code that is never called
is omitted from the output.

**Requirement:** the module format must be ES modules (`import` /
`export`). CommonJS (`require` / `module.exports`) is dynamic;
the bundler cannot determine which exports are used at build time
so the entire module is included.

| Bundler   | Tree shaking | Key config                         |
|-----------|--------------|------------------------------------|
| Rollup    | Excellent    | `treeshake.moduleSideEffects`      |
| esbuild   | Excellent    | `--tree-shaking=true` in lib mode  |
| Webpack 5 | Good         | `usedExports: true` + terser       |

## ES Module Static Analysis

Bundlers parse the AST at build time. Dynamic patterns defeat
static analysis and force the entire module into the bundle:

```ts
// GOOD — statically analyzable
import { format } from 'date-fns';

// BAD — dynamic key; entire namespace is bundled
const utils = await import('date-fns');
const fn = utils[dynamicKey]();

// BAD — CommonJS; whole module bundled
const { format } = require('date-fns');
```

Use `lodash-es` (ESM build) rather than `lodash` (CJS). Most
major libraries now ship an `exports` map in `package.json` that
points bundlers at the ESM entry automatically.

## sideEffects Field in package.json

A module has a "side effect" if importing it causes changes
beyond its exports — writing to globals, patching prototypes,
injecting styles. Without the `"sideEffects"` field, bundlers
assume every module may have side effects and include it even if
no export is referenced.

```json
{
  "name": "@acme/ui",
  "sideEffects": ["*.css", "src/polyfills.ts"]
}
```

`"sideEffects": false` tells the bundler it is safe to drop any
module whose exports are unused. List CSS files explicitly —
otherwise they are dropped as dead code.

## Barrel Files Killing Tree Shaking

A barrel file (`index.ts`) re-exports everything from a folder.
If any transitive import carries a side effect, the entire
barrel and all its imports are included, even for a consumer
that imports only one export:

```ts
// src/components/index.ts — problematic barrel
export { Button }    from './Button';
export { DataTable } from './DataTable'; // pulls in ag-grid
export { DatePicker} from './DatePicker';// pulls in date-fns
```

```ts
// Consumer
import { Button } from '@acme/ui'; // silently bundles ag-grid
```

Fix options:
1. **Deep imports:** `import { Button } from '@acme/ui/Button'`
2. **exports map:** expose individual entry points in
   `package.json` `"exports"` so deep imports are public API.
3. Annotate pure HOC calls with `/*#__PURE__*/` to let bundlers
   prune them when the wrapped component is unused.

## Bundler Configuration

**Rollup:**
```js
export default {
  treeshake: { moduleSideEffects: false, preset: 'recommended' },
};
```

**Webpack 5:**
```js
module.exports = {
  mode: 'production',
  optimization: { usedExports: true, sideEffects: true },
};
```

**esbuild (library build):**
```bash
esbuild src/index.ts \
  --bundle --tree-shaking=true \
  --format=esm --outfile=dist/index.js
```

## Bundle Analyzer to Verify

Never ship a dependency change without verifying bundle impact:

```ts
// vite.config.ts
import { visualizer } from 'rollup-plugin-visualizer';

export default {
  plugins: [
    visualizer({ filename: 'dist/stats.html', gzipSize: true }),
  ],
};
```

Open `dist/stats.html` after build. Large unexpected rectangles
— `moment`, a full icon pack, `lodash` CJS — indicate missed
tree shaking. Run the analyzer in CI and compare across branches.

## Anti-patterns

- Importing from a CJS package (`lodash`) when an ESM equivalent
  exists (`lodash-es`).
- Publishing a library with barrel `index.ts` and no `exports`
  map or `"sideEffects"` field.
- Using `export * from './all-components'` in application code.
- Setting `"sideEffects": false` when the library registers a
  global or patches `Array.prototype`.
- Expecting tree shaking to remove `console.log` — use the
  minifier's `drop: ['console']` option instead.

## Gotchas

- A referenced export pulls in all of that module's
  non-shakeable code. Trace the full export graph, not just the
  entry point.
- Dynamic `import()` creates a separate chunk; tree shaking
  applies within each chunk but not across the boundary.
- TypeScript `import type` is always removed at compile time;
  it does not need tree-shaking treatment.
- Webpack requires `mode: 'production'` (or explicit terser
  config) to actually remove dead-code annotations from the
  output; `usedExports: true` alone only marks them.

## Verification

- **CI size budget:** fail the build when the gzip size of
  `dist/index.js` exceeds the configured threshold
  (`bundlesize` or `size-limit`).
- **Bundle diff:** post a PR comment with the size delta of
  affected chunks using the `size-limit` GitHub Action.
- **Import Cost:** VS Code extension shows inline byte cost as
  you write import statements.

## Related

- `performance/dead-code-elimination.md`
- `performance/bundle-size-budgets.md`
- `performance/bundle-analysis-workflows.md`
- `frontend/rollup-library-bundling.md`

## Source URLs (verified 2026-08-17)

- https://rollupjs.org/configuration-options/#treeshake
- https://webpack.js.org/guides/tree-shaking/
- https://esbuild.github.io/api/#tree-shaking
- https://webpack.js.org/configuration/optimization/#optimizationsideeffects
- https://bundlephobia.com/
