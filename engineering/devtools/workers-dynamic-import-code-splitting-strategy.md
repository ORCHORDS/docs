# Workers Dynamic Import and Code Splitting Strategy

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Cloudflare Worker bundle has grown to 800 kB+ (well past the 1 MB compressed limit for free plans, or causing cold-start latency on paid plans). You want to split the bundle into smaller chunks, lazy-load infrequently used code paths, or share a runtime module between multiple Workers without bundling it into each. You are hitting esbuild `--bundle` defaults and do not know how Workers handle dynamic imports at runtime.

## Context

Cloudflare Workers support ES module dynamic `import()` with important restrictions: the imported module must be either (a) a module already in the same Worker bundle — esbuild must be configured to emit code-split chunks — or (b) a Workers Module Worker sibling deployed as a separate Worker accessed via a service binding. True runtime-lazy loading of external modules over the network is not supported. The Workers runtime resolves dynamic imports from the bundle's chunk manifest, not from the CDN. Understanding this constraint shapes the entire code-splitting strategy.

## 1. Understanding the Workers Module Format

Workers on the Cloudflare runtime use one of two module formats:

- **Service Worker format** (legacy): single script, no module syntax, no dynamic import support.
- **ES Module format** (current): `export default { fetch }`, supports static and dynamic `import()` within the bundle.

Confirm your Worker uses ES Module format in `wrangler.toml`:

```toml
# wrangler.toml
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

# ES module format is the default when main uses export default
# Explicit if needed:
# [build]
# command = "esbuild src/index.ts --format=esm --splitting --outdir=dist"
```

## 2. Enabling Code Splitting in esbuild / Wrangler

Wrangler uses esbuild internally. Enable code splitting via the `wrangler.toml` build configuration or a custom esbuild script:

```toml
# wrangler.toml — custom build with splitting
[build]
command = "node scripts/build.mjs"
```

```javascript
// scripts/build.mjs
import * as esbuild from 'esbuild'
import { readdir, rm } from 'fs/promises'

await rm('dist', { recursive: true, force: true })

const result = await esbuild.build({
  entryPoints: ['src/index.ts'],
  bundle: true,
  splitting: true,           // enable chunk generation
  format: 'esm',            // required for splitting
  outdir: 'dist',
  minify: true,
  sourcemap: 'linked',
  // Externals that come from bindings, not the bundle
  external: ['__STATIC_CONTENT_MANIFEST'],
  metafile: true,
})

// Log chunk sizes for monitoring
const sizes = Object.entries(result.metafile.outputs)
  .map(([file, meta]) => ({ file, bytes: meta.bytes }))
  .sort((a, b) => b.bytes - a.bytes)

console.table(sizes.map(({ file, bytes }) => ({
  file: file.replace('dist/', ''),
  kB: (bytes / 1024).toFixed(1),
})))
```

Update `wrangler.toml` to point at the built output:

```toml
[build]
command = "node scripts/build.mjs"

# After build, wrangler uploads dist/ directory
main = "dist/index.js"
```

## 3. Dynamic Import for Route-Based Code Splitting

Split large route handlers into separate chunks that are only parsed when that route is hit:

```typescript
// src/index.ts
import { Hono } from 'hono'

const app = new Hono()

// Lightweight routes — always bundled inline
app.get('/health', (c) => c.json({ ok: true }))

// Heavy route — dynamically imported, parsed only on first call
app.post('/export/csv', async (c) => {
  // Dynamic import resolved from bundle chunk, not network
  const { handleCsvExport } = await import('./routes/export-csv')
  return handleCsvExport(c)
})

app.post('/ai/summarize', async (c) => {
  const { handleAiSummarize } = await import('./routes/ai-summarize')
  return handleAiSummarize(c)
})

export default app
```

```typescript
// src/routes/export-csv.ts
import { stringify } from 'csv-stringify/sync'   // heavy dependency

export async function handleCsvExport(c: Context): Promise<Response> {
  const data = await c.env.DB.prepare('SELECT * FROM exports').all()
  const csv = stringify(data.results as Record<string, unknown>[], { header: true })
  return new Response(csv, {
    headers: { 'Content-Type': 'text/csv' },
  })
}
```

esbuild emits `export-csv` as a separate chunk; it is uploaded to the Workers runtime as part of the module bundle and is available synchronously on second call (cached in the isolate).

## 4. Shared Module Strategy via Service Bindings

For code shared across multiple Workers, deploy it as a standalone Worker and call it via a service binding instead of bundling it into each Worker:

```toml
# workers/shared-utils/wrangler.toml
name = "shared-utils"
main = "src/index.ts"
```

```typescript
// workers/shared-utils/src/index.ts
export interface SharedUtilsEnv {}

export default {
  async fetch(request: Request): Promise<Response> {
    const { pathname } = new URL(request.url)
    if (pathname === '/parse-markdown') {
      const { parseMarkdown } = await import('./markdown')
      return parseMarkdown(request)
    }
    return new Response('Not Found', { status: 404 })
  },
}
```

Consumer Workers call it via the service binding — no duplication:

```toml
# workers/api/wrangler.toml
[[services]]
binding = "UTILS"
service = "shared-utils"
```

```typescript
// workers/api/src/index.ts
const html = await c.env.UTILS.fetch(
  new Request('http://shared-utils/parse-markdown', {
    method: 'POST',
    body: markdownText,
  })
).then((r) => r.text())
```

## 5. Bundle Size Analysis and Monitoring

After splitting, analyze which chunks remain large:

```bash
# Generate metafile and visualize in esbuild analyzer
node scripts/build.mjs
# Open https://esbuild.github.io/analyze/ and paste metafile.json

# Or use the bundle-size-limit check in CI
npx size-limit
```

```json
// .size-limit.json
[
  {
    "name": "Worker entry chunk",
    "path": "dist/index.js",
    "limit": "50 kB"
  },
  {
    "name": "CSV export chunk",
    "path": "dist/routes/export-csv.js",
    "limit": "200 kB"
  }
]
```

Track total bundle size across all chunks:

```bash
# Sum all chunk sizes
du -sh dist/
# Workers free plan: 1 MB compressed total for all chunks
# Workers paid plan: 10 MB
```

## 6. Lazy Loading JSON Data and WASM

Dynamic import also works for JSON and WASM modules in Workers:

```typescript
// Lazy-load a large locale file
async function getTranslations(locale: string) {
  const mod = await import(`./locales/${locale}.json`, {
    assert: { type: 'json' },
  })
  return mod.default
}

// Lazy-load WASM
async function runWasm(input: Uint8Array): Promise<Uint8Array> {
  const wasmModule = await import('./lib/processor.wasm')
  const instance = await WebAssembly.instantiate(wasmModule.default)
  return (instance.exports.process as CallableFunction)(input) as Uint8Array
}
```

WASM files must be listed in `wrangler.toml` under `[[rules]]`:

```toml
[[rules]]
type = "CompiledWasm"
globs = ["**/*.wasm"]
fallthrough = true
```

## Anti-patterns

- **Using `import()` with a fully dynamic string like `import(variable)`.** esbuild cannot statically analyze this and will not include the target in the bundle. The import will fail at runtime with a module-not-found error.
- **Expecting dynamic imports to fetch from the internet.** Workers block outbound module resolution. `import('https://cdn.skypack.dev/lodash')` will throw at runtime, not at build time.
- **Splitting every route handler into its own chunk.** Each chunk has a fixed overhead (~1 kB). For small handlers (< 5 kB), the chunk overhead exceeds the savings. Only split modules that are genuinely large or infrequently needed.
- **Enabling `splitting: true` without `format: 'esm'`.** esbuild requires ESM format for code splitting; mixing formats produces an error.

## Gotchas

- Dynamic imports in Workers are resolved from the bundle manifest at startup, not lazily over the network. The first call to a dynamic import is synchronous after the first parse (the isolate caches the module); there is no cold-start penalty per-import after the Worker is warm.
- The Workers runtime does NOT support `import.meta.glob` (a Vite-ism). Use explicit import paths.
- When using `--minify`, esbuild renames chunk files with hashes. Update `wrangler.toml` or use a post-build script to set `main` to the correct hashed entry file.
- Service Worker format (`addEventListener('fetch', ...)`) does not support `import()`. Migrating to ES Module format requires updating the handler signature.

## Verification

```bash
# Check total bundle size
ls -lh dist/*.js | awk '{sum += $5} END {print "Total:", sum/1024 "kB"}'

# Verify splitting produced multiple chunks
ls dist/ | wc -l   # should be > 1

# Test that dynamic imports resolve correctly in miniflare
pnpm --filter @example project/api vitest run

# Upload and verify with wrangler dry-run
pnpm --filter @example project/api wrangler deploy --dry-run --outdir /tmp/worker-dry-run
du -sh /tmp/worker-dry-run/
```

## Related

- `esbuild-metafile-bundle-analysis-workers.md`
- `esbuild-workers-plugins-custom-transforms.md`
- `bundle-size-tracking-size-limit-ci.md`
- `wrangler-service-bindings-multi-worker-local-dev.md`
- `production-source-maps-strategy.md`

## Sources

- https://developers.cloudflare.com/workers/reference/migrate-to-module-workers/
- https://esbuild.github.io/api/#splitting
- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- https://developers.cloudflare.com/workers/configuration/bundling/
