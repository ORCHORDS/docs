# Workers Bundle Size Optimisation with esbuild

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Worker cold-start latency creeps up as the codebase grows. `wrangler deploy` reports a bundle over 1 MB (compressed), and local `wrangler dev` is noticeably slower. Profiling shows large third-party libraries pulled in via `import` that are only partially used. A CI pipeline has no guard against future regressions.

## Context

Cloudflare Workers have a **1 MB compressed bundle size limit** for the Free plan and **10 MB** for paid plans (as of 2024). More importantly, V8 must parse and compile the entire module graph on cold start. Larger bundles mean longer cold starts, increased memory pressure, and slower first-request latency in regions where the Worker is not resident.

Wrangler uses esbuild internally. Understanding esbuild's knobs — and where Wrangler's defaults leave room for improvement — lets you shrink bundles dramatically without changing runtime behaviour.

Key levers:
- **Tree-shaking** — esbuild eliminates dead code across module boundaries when `format: 'esm'` and no side-effect ambiguity exists.
- **`external`** — marking packages external prevents bundling them; valid only for packages available in the Workers runtime (e.g. `node:*` compatibility shims).
- **`minify`** — identifier renaming + whitespace removal typically cuts 20–40%.
- **Dynamic `import()`** — Workers support ES module dynamic imports, enabling code splitting.
- **Bundle analysis** — esbuild's metafile + third-party visualisers reveal the largest contributors.

## Solution

### 1 — Enable full minification in `wrangler.toml`

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[build.upload]
format = "modules"

[minify]
js = true
```

Or via a custom esbuild script when you need finer control:

```typescript
// scripts/build.ts
import * as esbuild from 'esbuild';
import { writeFileSync } from 'fs';

const result = await esbuild.build({
  entryPoints: ['src/index.ts'],
  bundle: true,
  format: 'esm',
  target: 'es2022',
  outfile: 'dist/worker.js',

  // Full minification.
  minify: true,
  minifyIdentifiers: true,
  minifySyntax: true,
  minifyWhitespace: true,

  // Tree-shaking is on by default for ESM; make it explicit.
  treeShaking: true,

  // Packages available in the Workers runtime — do NOT bundle these.
  external: [
    'node:async_hooks',
    'node:buffer',
    'node:crypto',
    'node:events',
    'node:path',
    'node:process',
    'node:stream',
    'node:util',
    'cloudflare:workers',
    'cloudflare:sockets',
  ],

  // Produce a metafile for bundle analysis.
  metafile: true,

  // Suppress warnings for packages with known side-effect quirks.
  logLevel: 'warning',

  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
  },
});

// Write metafile for analysis.
writeFileSync('dist/meta.json', JSON.stringify(result.metafile));

const sizeBytes = result.outputFiles?.[0]?.contents.byteLength ?? 0;
console.log(`Bundle: ${(sizeBytes / 1024).toFixed(1)} KB`);
```

### 2 — Analyse the bundle

```bash
# Option A: esbuild's own analyser (CLI)
npx esbuild src/index.ts --bundle --metafile=meta.json --format=esm >/dev/null
npx esbuild-bundle-analyzer meta.json

# Option B: Bundlephobia-style web visualiser
npx esbuild src/index.ts --bundle --metafile=meta.json --format=esm >/dev/null
npx --yes source-map-explorer dist/worker.js --html dist/bundle-report.html
open dist/bundle-report.html

# Option C: Quick text summary sorted by size
cat dist/meta.json | node -e "
  const m = JSON.parse(require('fs').readFileSync('/dev/stdin', 'utf8'));
  const inputs = Object.entries(m.inputs)
    .map(([k, v]) => ({ k, size: v.bytes }))
    .sort((a, b) => b.size - a.size)
    .slice(0, 20);
  inputs.forEach(({ k, size }) =>
    console.log(String(size).padStart(10), k)
  );
"
```

### 3 — Tree-shaking large utility libraries

```typescript
// BAD — imports the entire lodash bundle (~72 KB min+gzip)
import _ from 'lodash';
const chunks = _.chunk(array, 3);

// GOOD — import only the function needed (esbuild tree-shakes the rest)
import chunk from 'lodash-es/chunk.js';
const chunks = chunk(array, 3);

// BETTER — use a native equivalent and eliminate the dependency entirely
const chunks = Array.from(
  { length: Math.ceil(array.length / 3) },
  (_, i) => array.slice(i * 3, i * 3 + 3)
);
```

```typescript
// BAD — zod pulls in 12 KB+ for simple object validation
import { z } from 'zod';
const schema = z.object({ id: z.string() });

// BETTER for Workers — use a lightweight alternative
import * as v from 'valibot'; // ~1 KB per schema
import { object, string, parse } from 'valibot';
const schema = object({ id: string() });
const data = parse(schema, input);
```

### 4 — Dynamic import for code splitting

```typescript
// src/index.ts — only load heavy route handlers on demand
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname.startsWith('/admin')) {
      // This chunk is only loaded when /admin is requested.
      // V8 compiles it lazily — cold-start for other routes is unaffected.
      const { handleAdmin } = await import('./routes/admin');
      return handleAdmin(request, env);
    }

    if (pathname.startsWith('/webhooks')) {
      const { handleWebhook } = await import('./routes/webhooks');
      return handleWebhook(request, env);
    }

    return fetch(request); // default pass-through
  },
};
```

esbuild splits dynamic imports into separate output chunks when `splitting: true`:

```typescript
await esbuild.build({
  entryPoints: ['src/index.ts'],
  bundle: true,
  format: 'esm',
  splitting: true,       // Enables dynamic import chunking.
  outdir: 'dist',        // Required when splitting is enabled.
  chunkNames: 'chunks/[name]-[hash]',
  // ... rest of options
});
```

### 5 — CI bundle size budget gate

```yaml
# .github/workflows/bundle-size.yml
name: Bundle size gate

on: [push, pull_request]

jobs:
  bundle-size:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - run: npm ci

      - name: Build
        run: node scripts/build.ts

      - name: Check bundle size
        run: |
          SIZE=$(wc -c < dist/worker.js)
          # Gzip the bundle and check compressed size.
          GZIP_SIZE=$(gzip -c dist/worker.js | wc -c)
          echo "Raw: ${SIZE} bytes | Gzip: ${GZIP_SIZE} bytes"

          # Fail if gzipped size exceeds 512 KB (half the 1 MB limit).
          LIMIT=$((512 * 1024))
          if [ "$GZIP_SIZE" -gt "$LIMIT" ]; then
            echo "Bundle size $GZIP_SIZE exceeds budget $LIMIT"
            exit 1
          fi
```

For PR-level diffing:

```typescript
// scripts/size-report.ts — post bundle size diff as a PR comment
import { execSync } from 'child_process';

const currentSize = statSync('dist/worker.js').size;
const baseSize = parseInt(process.env.BASE_BUNDLE_SIZE ?? '0');
const delta = currentSize - baseSize;
const sign = delta >= 0 ? '+' : '';

console.log(
  `Bundle: ${currentSize} B (${sign}${delta} B vs base)`
);

if (Math.abs(delta) > 10_240) { // > 10 KB change — alert
  process.exitCode = 1;
}
```

## Implementation Details

**Side-effect annotations.** Tree-shaking works only when esbuild can prove a module is side-effect-free. Add `"sideEffects": false` to your `package.json` (or to individual packages via `package.json` in `node_modules` patches / `pnpm.overrides`). Without this annotation esbuild conservatively keeps entire modules.

**`external` vs `ignore`.** Marking a package `external` means it must exist in the runtime environment. Workers do not expose arbitrary npm packages at runtime — only Node.js compat shims (`node:*`) and `cloudflare:*` namespaces are available. Marking an npm package external without a runtime equivalent causes a runtime `Cannot find module` error.

**Source maps.** Enable `sourcemap: 'linked'` during development but strip source maps from production builds. A source map can double the upload size.

## Anti-patterns

- **`import * as X from 'pkg'`** — namespace imports prevent tree-shaking because esbuild cannot statically know which exports are used.
- **Re-exporting everything from an index barrel file** (`export * from './moduleA'`) — forces esbuild to include all transitive exports. Prefer direct imports.
- **`require()` inside conditional branches** — CJS dynamic `require` is opaque to tree-shaking. Convert to ESM `import()` to allow splitting.
- **Committing `dist/` to source control** — bundle regressions go undetected without a CI gate comparing against a known-good baseline.

## Gotchas

- `wrangler deploy` re-runs esbuild internally even if you provide a pre-built file via `wrangler deploy dist/worker.js`. Use `wrangler deploy --no-bundle` to skip Wrangler's esbuild pass and use your pre-built file as-is.
- Dynamic `import()` in Workers requires `compatibility_date >= 2024-09-23` and the module format must be `esm`.
- esbuild's `metafile` reports uncompressed bytes. Cloudflare enforces the **compressed** (gzip) limit. Always gzip the output before comparing to the 1 MB limit.
- `minifyIdentifiers` renames variables, which can break code that uses `Function.name` or relies on class names for reflection. Test thoroughly after enabling.

## Verification

```bash
# Build and print size:
node scripts/build.ts
ls -lh dist/worker.js
gzip -c dist/worker.js | wc -c

# Deploy with no-bundle (use your optimised build):
wrangler deploy dist/worker.js --no-bundle

# Measure cold-start improvement:
for i in {1..10}; do
  curl -o /dev/null -s -w "%{time_total}\n" https://your-worker.example.com/
done | awk '{sum+=$1} END {print "avg", sum/NR, "s"}'

# Confirm dynamic chunks are served:
curl -si https://your-worker.example.com/admin | grep 'x-worker-chunk'
```

Expect cold-start latency to drop by 30–60% when bundle size is halved.

## Related

- `workers-streaming-response-time-to-first-byte.md` — smaller bundles amplify streaming TTFB gains.
- `workers-cache-api-fine-grained-control.md` — cache static assets to avoid repeated Worker invocations.
- `workers-connection-keep-alive-upstream.md` — after reducing bundle size, upstream latency becomes the next bottleneck.

## Sources

- https://developers.cloudflare.com/workers/platform/limits/
- https://esbuild.github.io/api/
- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://esbuild.github.io/api/#tree-shaking
