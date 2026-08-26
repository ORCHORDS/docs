# Bundle Size Optimization and Tree Shaking for Workers with esbuild

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Wrangler deploy fails with `Error: Script size of X MB exceeds the maximum size of 1 MB (compressed)`, or deploys succeed but cold-start latency is high. You suspect heavy npm dependencies are inflating the bundle but are unsure which ones.

## Context

Cloudflare Workers has a **1 MB compressed bundle limit** (the uncompressed limit is 10 MB on the Free plan; on Paid/Enterprise plans it is higher, but the compressed limit is the practical constraint). The Worker bundle is compiled and uploaded as a single ESM module by Wrangler, which uses esbuild internally.

Because Workers run in V8 isolates without a Node.js runtime, many npm packages import large chunks of code that are never called (e.g. Node.js compatibility shims, polyfills, entire utility libraries). Tree shaking — the process of removing unused exports at bundle time — is your primary tool for keeping bundles lean.

Key concepts:
- **Tree shaking** works only on ES module exports (`export function foo`). CommonJS (`module.exports`) is opaque to esbuild's dead-code elimination.
- **Named imports** (`import { format } from 'date-fns'`) enable tree shaking; **namespace imports** (`import * as _ from 'lodash'`) often do not.
- **`minify = true`** in `wrangler.toml` enables esbuild's minifier (identifier renaming + whitespace removal), which typically reduces bundle size by an additional 20–40 %.

## Analysing and Optimising the Bundle

```typescript
// ─── BEFORE: anti-patterns that inflate bundle size ───────────────────────────

// Bad: imports the entire lodash library (~70 KB minified)
import _ from 'lodash';
const sorted = _.sortBy(items, 'name');

// Bad: imports all date-fns (~200 KB+)
import { format, parseISO, addDays, differenceInDays } from 'date-fns';

// Bad: default import from a CJS-first package — tree shaking is disabled
import moment from 'moment'; // ~300 KB

// ─── AFTER: native equivalents and surgical imports ───────────────────────────

// Replace _.sortBy with Array.prototype.sort (zero bundle cost)
const sorted = [...items].sort((a, b) => a.name.localeCompare(b.name));

// Replace _.pick / _.omit with object destructuring
const { unwanted: _drop, ...kept } = record;

// Replace _.debounce with a hand-rolled version for Workers context
// (Workers have no DOM; if you need debounce, write the 5-line version)

// Replace moment with native Intl + temporal arithmetic
const formatted = new Intl.DateTimeFormat('en-US', {
  year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC',
}).format(new Date(isoString));

// For date-fns: prefer date-fns/esm named imports if you must use the library
import { format } from 'date-fns/format'; // single-function deep import

// ─── wrangler.toml settings ───────────────────────────────────────────────────
//
// [build]
// minify = true           # enables esbuild --minify
//
// [build.upload]
// format = "modules"      # required for tree shaking (ESM output)

// ─── Analyse the bundle with esbuild-bundle-analyzer ─────────────────────────
//
// Step 1: produce the bundle without uploading
//   npx wrangler deploy --dry-run --outdir=dist
//
// Step 2: generate the metafile (esbuild's structured build report)
//   npx esbuild dist/index.js --bundle --minify --outfile=/dev/null \
//     --metafile=dist/meta.json --format=esm --platform=browser
//
// Step 3: visualise at https://esbuild.github.io/analyze/ (paste meta.json)
//   OR use the CLI analyzer:
//   npx esbuild-bundle-analyzer dist/meta.json

// ─── Practical replacement table ──────────────────────────────────────────────
//
// Package         → Native/lean replacement
// lodash (~70 KB) → native Array/Object methods + hand-rolled utils
// moment (~300 KB)→ Intl.DateTimeFormat + Temporal (when available)
// axios (~50 KB)  → global fetch() (built into Workers runtime)
// uuid (~10 KB)   → crypto.randomUUID() (built into Workers runtime)
// qs (~10 KB)     → URLSearchParams (built into Workers runtime)
// chalk (~15 KB)  → not needed (Workers have no terminal colour output)

export default {
  async fetch(request: Request): Promise<Response> {
    // Show bundle size info in a debug endpoint
    if (new URL(request.url).pathname === '/_bundle-debug') {
      return Response.json({
        // These values are injected at build time via wrangler.toml [vars]
        // or a build plugin; shown here for illustration.
        bundle_hint: 'Check CF-Ray header; see Wrangler output for compressed size.',
      });
    }
    return new Response('OK');
  },
};
```

## Wrangler Configuration for Minimum Bundle Size

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[build]
minify = true          # esbuild --minify: identifier shortening + whitespace removal

# If you use Node.js compat, be selective:
# compatibility_flags = ["nodejs_compat_v2"]   # adds ~50 KB of shims — only if needed
```

`minify = true` is the single highest-impact configuration change for bundle size. For a typical Worker that has accumulated unnecessary dependencies, this alone can reduce size by 30–50 KB.

## What Happens When You Exceed 1 MB (Compressed)

Wrangler reports the error at upload time:

```
Error: Script size of 1.24 MB exceeds the maximum size of 1 MB.
```

The deploy is rejected — the previous version of the Worker continues to serve traffic. The limit applies to the **gzip-compressed** bundle. In practice:
- An unminified 3 MB bundle compresses to ~900 KB — under the limit.
- An unminified 4 MB bundle compresses to ~1.2 MB — over the limit.
- Minification typically improves the compression ratio further.

If you genuinely need > 1 MB after all optimisations, consider:
- **Code splitting** — use Workers Service Bindings to offload discrete functionality to a separate Worker.
- **Dynamic imports** — not supported in Workers (no runtime code loading); the solution is Service Bindings.
- **Large assets** — move static files to R2 or KV and fetch them at runtime rather than bundling them.

## Identifying the Heaviest Dependencies

```bash
# 1. Dry-run deploy to get the bundle without uploading
npx wrangler deploy --dry-run --outdir=dist

# 2. Generate esbuild metafile
npx esbuild dist/*.js \
  --bundle=false \
  --metafile=dist/meta.json \
  --outfile=/dev/null

# 3. Quick CLI size report — top 20 inputs by size
npx esbuild-bundle-analyzer dist/meta.json --top 20

# 4. Check compressed size manually
gzip -k dist/*.js && ls -lh dist/*.js.gz

# 5. Inspect which lodash functions are actually used in your code
grep -r 'from .lodash' src/ | sort -u
```

## Anti-patterns

- **`import * as utils from './utils'`** when `utils` re-exports dozens of functions — even if you use one, esbuild may include all of them if the module has side effects.
- **Importing a library for a single function** that has a 3-line native equivalent (e.g. `import { isEmpty } from 'lodash'` instead of `value.length === 0`).
- **`compatibility_flags = ["nodejs_compat_v2"]`** when your Worker does not actually use any Node.js APIs — this flag adds Node.js polyfill shims to the bundle.
- **Bundling large JSON files** (e.g. timezone databases, i18n dictionaries) — store in KV and fetch at runtime.

## Gotchas

- `--dry-run --outdir=dist` produces the bundled file but does not apply the same compression Cloudflare uses for the limit check. Use `gzip -k` locally to get a rough equivalent, but the actual limit is checked server-side.
- Tree shaking requires that the imported module is **side-effect-free** (or declares `"sideEffects": false` in its `package.json`). Many npm packages do not declare this, causing esbuild to include them in full even if you import only one function.
- TypeScript type imports (`import type { Foo } from './foo'`) are zero-cost — they are erased at compile time. Only value imports contribute to bundle size.
- `minify = true` can occasionally break code that relies on function `.name` properties (e.g. some DI frameworks). Test thoroughly after enabling.

## Verification

```bash
# Verify compressed size before deploy
npx wrangler deploy --dry-run --outdir=dist 2>&1 | grep -E 'Total|kB|MB'
gzip -k dist/*.js && ls -lh dist/*.js.gz

# Deploy and check the Wrangler output for the final size line
npx wrangler deploy 2>&1 | grep -E 'Uploaded|compressed'
# Expected: "Uploaded my-worker (X.XX KB compressed)"

# Confirm the Worker responds after optimisation
curl -si https://my-worker.example.com/ | head -5
```

## Related

- `d1-batch-insert-performance-tuning.md`
- `workers-cache-api-advanced-custom-keys.md`
- [Workers Limits — Cloudflare Docs](https://developers.cloudflare.com/workers/platform/limits/)
- [esbuild Bundle Analysis](https://esbuild.github.io/analyze/)

## Sources

- Cloudflare Workers platform limits documentation (2025)
- esbuild documentation — tree shaking and metafile analysis
- Wrangler configuration reference — `[build]` section (2025)
