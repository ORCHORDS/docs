# Bundle Size Analysis and Optimization for Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

`wrangler deploy` reports "Script startup exceeded CPU time limit" or your Worker is approaching Cloudflare's 10 MB compressed script size limit. You want to understand *which* imports are driving the size, enforce a size budget in CI, and systematically shrink the bundle without breaking functionality.

## Context

Cloudflare Workers enforces a **10 MB compressed** (after gzip) upload limit for Bundled plans and a **1 MB** limit on the Workers Free plan. Even well under the limit, large bundles increase cold-start time because the V8 isolate must parse and compile more JavaScript. The Workers runtime uses [V8's snapshot mechanism](https://v8.dev/blog/custom-startup-snapshots) for built-in globals but not for your code — every byte of your bundle is parsed on each cold start.

The primary tool for size analysis is esbuild's **metafile**: a JSON document that maps every input module to its output contribution in bytes.

## Solution

```typescript
// scripts/analyze-bundle.ts  — full analysis pipeline
import * as esbuild from 'esbuild';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as zlib from 'node:zlib';

const BUNDLE_PATH   = 'dist/index.js';
const METAFILE_PATH = 'dist/meta.json';

interface SizeReport {
  rawBytes:  number;
  gzipBytes: number;
  topModules: Array<{ path: string; bytes: number; percent: number }>;
}

async function buildWithMeta(): Promise<esbuild.Metafile> {
  const result = await esbuild.build({
    entryPoints: ['src/index.ts'],
    bundle:       true,
    outfile:      BUNDLE_PATH,
    format:       'esm',
    target:       'es2022',
    platform:     'browser',
    conditions:   ['workerd', 'worker', 'browser'],
    minify:       true,
    treeShaking:  true,
    metafile:     true,   // ← the key flag
  });

  fs.writeFileSync(METAFILE_PATH, JSON.stringify(result.metafile));
  return result.metafile!;
}

function gzipSizeSync(filePath: string): number {
  const raw        = fs.readFileSync(filePath);
  const compressed = zlib.gzipSync(raw, { level: 9 });
  return compressed.byteLength;
}

function analyzeMetafile(metafile: esbuild.Metafile): SizeReport {
  const output    = metafile.outputs[BUNDLE_PATH];
  const rawBytes  = output.bytes;
  const gzipBytes = gzipSizeSync(BUNDLE_PATH);

  // Flatten the input tree into a list sorted by byte contribution
  const modules: Array<{ path: string; bytes: number }> = [];
  for (const [inputPath, data] of Object.entries(metafile.inputs)) {
    modules.push({ path: inputPath, bytes: data.bytes });
  }
  modules.sort((a, b) => b.bytes - a.bytes);

  const topModules = modules.slice(0, 20).map((m) => ({
    path:    m.path,
    bytes:   m.bytes,
    percent: Math.round((m.bytes / rawBytes) * 100 * 10) / 10,
  }));

  return { rawBytes, gzipBytes, topModules };
}

function printReport(report: SizeReport): void {
  const KB = (n: number) => (n / 1024).toFixed(1) + ' KB';
  console.log(`\nBundle size report`);
  console.log(`  Raw:       ${KB(report.rawBytes)}`);
  console.log(`  Gzip:      ${KB(report.gzipBytes)}`);
  console.log(`\nTop modules by raw size:`);
  for (const m of report.topModules) {
    console.log(`  ${m.percent.toString().padStart(5)}%  ${KB(m.bytes).padStart(10)}  ${m.path}`);
  }
}

async function main(): Promise<void> {
  const metafile = await buildWithMeta();
  const report   = analyzeMetafile(metafile);
  printReport(report);

  // Print the esbuild tree-map analysis
  const text = await esbuild.analyzeMetafile(metafile, { verbose: true });
  console.log(text);
}

main().catch((e) => { console.error(e); process.exit(1); });
```

```typescript
// scripts/ci-size-check.ts  — enforce size budgets in CI
import * as zlib from 'node:zlib';
import * as fs from 'node:fs';

interface SizeBudget {
  maxRawKB:  number;   // uncompressed limit
  maxGzipKB: number;   // gzip limit (Cloudflare enforces gzip)
}

const BUDGETS: Record<string, SizeBudget> = {
  'dist/index.js':     { maxRawKB: 2048, maxGzipKB: 512 },
  'dist/auth.js':      { maxRawKB: 256,  maxGzipKB: 64  },
};

let failed = false;

for (const [filePath, budget] of Object.entries(BUDGETS)) {
  if (!fs.existsSync(filePath)) {
    console.error(`MISSING: ${filePath}`);
    failed = true;
    continue;
  }

  const raw        = fs.readFileSync(filePath);
  const compressed = zlib.gzipSync(raw, { level: 9 });
  const rawKB      = raw.byteLength / 1024;
  const gzipKB     = compressed.byteLength / 1024;

  const rawOk  = rawKB  <= budget.maxRawKB;
  const gzipOk = gzipKB <= budget.maxGzipKB;

  const status = rawOk && gzipOk ? 'OK  ' : 'FAIL';
  console.log(
    `[${status}] ${filePath}\n` +
    `       raw=${rawKB.toFixed(1)}KB (limit ${budget.maxRawKB}KB)` +
    `   gzip=${gzipKB.toFixed(1)}KB (limit ${budget.maxGzipKB}KB)`,
  );

  if (!rawOk || !gzipOk) failed = true;
}

process.exit(failed ? 1 : 0);
```

```typescript
// src/index.ts  — before: imports a heavy library
import { parseISO, format, addDays } from 'date-fns';   // 74 KB minified
import _ from 'lodash';                                  // 72 KB minified
import { marked } from 'marked';                        // 43 KB minified

export default {
  async fetch(request: Request): Promise<Response> {
    const date    = parseISO('2024-01-15');
    const fmtDate = format(addDays(date, 7), 'yyyy-MM-dd');
    const items   = _.uniq([1, 2, 2, 3]);
    const html    = marked('**Hello**');
    return Response.json({ fmtDate, items, html });
  },
};
```

```typescript
// src/index.ts  — after: replaced with lightweight alternatives
// date-fns (74 KB) → native Intl + manual arithmetic
function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setUTCDate(d.getUTCDate() + days);
  return d;
}
function formatDate(date: Date): string {
  return date.toISOString().slice(0, 10);   // yyyy-MM-dd
}

// lodash (72 KB) → one-liner native
function uniq<T>(arr: T[]): T[] {
  return [...new Set(arr)];
}

// marked (43 KB) → use a lightweight alternative or inline the logic
// If Markdown is static, pre-render at build time instead:
import prerenderedHtml from './static/hello.html.ts';   // generated by build step

export default {
  async fetch(request: Request): Promise<Response> {
    const date    = addDays(new Date('2024-01-15'), 7);
    const fmtDate = formatDate(date);
    const items   = uniq([1, 2, 2, 3]);
    return Response.json({ fmtDate, items, html: prerenderedHtml });
  },
};
// Net saving: ~189 KB raw / ~60 KB gzip
```

```typescript
// src/lazy-router.ts  — code splitting with dynamic import
// Workers supports top-level await but NOT dynamic import() at runtime.
// Use dynamic import at BUILD TIME to split into separate entrypoints
// deployed as separate Workers (service bindings), not lazy-loaded chunks.
// The correct pattern is separate entrypoints, not inline dynamic import().

// wrangler.toml for two entrypoints:
// main = "dist/api.js"            ← the primary Worker
// [services]
//   api_admin = { service = "admin-worker" }  ← heavy admin routes

// dist/api.ts  — lightweight public API
export default {
  async fetch(request: Request, env: AdminEnv): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/admin')) {
      // Delegate to the separate Admin Worker via service binding
      return env.api_admin.fetch(request);
    }
    return new Response('Hello from lightweight API');
  },
};
interface AdminEnv { api_admin: Fetcher; }
```

```bash
# package.json scripts for size management
# {
#   "scripts": {
#     "analyze":    "npx tsx scripts/analyze-bundle.ts",
#     "size-check": "npx tsx scripts/ci-size-check.ts",
#     "size-viz":   "npx esbuild-visualizer --metadata dist/meta.json --open"
#   }
# }

# wrangler dry-run: check upload size without deploying
wrangler deploy --dry-run --outdir .wrangler/output
ls -lh .wrangler/output/

# Use bundle-phobia to check a package's size before adding it
npx bundle-phobia <package-name>

# Check what esbuild tree-shook away
npx tsx scripts/analyze-bundle.ts 2>&1 | grep -E 'node_modules|KB'
```

## Implementation Details

**Reading the metafile.** `metafile.inputs` maps every resolved module path to `{ bytes, imports }`. `metafile.outputs` maps each output file to its total `bytes` and a `inputs` breakdown of which input files contributed. The `bytes` in `inputs` are the sizes of individual modules *before* minification; the output `bytes` is after minification. Use the output bytes for gzip estimation.

**`wrangler deploy --dry-run`.** This flag builds and packs the Worker (including source map) into the same `.zip` payload that would be uploaded, then writes it to `--outdir` and exits. Use `ls -lh` on the output directory to see the exact upload size before committing to a deploy.

**Tree-shaking effectiveness.** esbuild's tree-shaking is driven by ES module static analysis. CommonJS modules (`require`, `module.exports`) cannot be tree-shaken reliably. When a dependency ships only a CJS build, the entire module is included even if you use one function. Prefer ESM-first packages; check with `cat node_modules/<pkg>/package.json | jq '.module, .exports'`.

**Replacing heavy packages.** Common high-value swaps for Workers:
| Package | Size (min) | Replacement | Size |
|---------|-----------|-------------|------|
| `date-fns` | 74 KB | `Temporal` / native `Date` | 0 KB |
| `lodash` | 72 KB | Native ES2022 | 0 KB |
| `marked` | 43 KB | Pre-render at build time | 0 KB |
| `uuid` | 8 KB | `crypto.randomUUID()` | 0 KB |
| `axios` | 42 KB | `fetch()` | 0 KB |
| `joi` | 140 KB | `zod` (~13 KB) or manual | ~13 KB |

**CI budget enforcement.** Add `size-check` to your CI pipeline as a step that runs after the build but before `wrangler deploy`. A failing size check blocks the deploy and prints the offending file and its budget overage. Track budget history in a JSON file committed to the repo so regressions are visible in pull request diffs.

## Anti-patterns

- **Analyzing the un-minified bundle.** Always run `minify: true` before size analysis. The raw TypeScript source is misleading — minification and tree-shaking together often reduce size by 60–80%.
- **Adding `external: [...]` to shrink bundle size.** Marking a package as external removes it from the bundle but Workers has no module loader at runtime. The Worker will throw `Cannot find module` on the first import. `external` is valid only for packages that are built into the Workers runtime (e.g., the `cloudflare:*` namespace).
- **Using a single large Worker for all routes.** Splitting infrequently-used, heavy routes into separate Workers served via service bindings keeps the hot-path Worker small and reduces cold-start frequency for those routes.
- **Importing entire libraries for one function.** `import _ from 'lodash'` bundles all of lodash. Even `import { cloneDeep } from 'lodash'` pulls in the whole package via its CJS entry. Use `lodash-es` (ESM) or inline the function.

## Gotchas

- The 10 MB Cloudflare limit is measured on the *compressed* (gzip) payload, not the raw JS. A 25 MB raw bundle may compress to under 10 MB — but cold-start time scales with raw bytes, not compressed bytes, because V8 parses raw JS.
- `esbuild.analyzeMetafile` output is a formatted string for humans. For machine-readable data, parse `metafile.json` directly.
- `esbuild-visualizer` (generates a sunburst/treemap HTML) requires the metafile path as input: `npx esbuild-visualizer --metadata dist/meta.json`. Open the output HTML in a browser for an interactive breakdown.
- Dynamic `import()` at *runtime* is not supported in Workers (as of compat date 2024-09-23). All code splitting must be done at the architecture level (separate Workers) or at build time (separate entrypoints).

## Verification

```bash
# Step 1: build with metafile
npx tsx scripts/analyze-bundle.ts
# Outputs: bundle size table + top modules

# Step 2: dry-run to see exact Cloudflare upload size
wrangler deploy --dry-run --outdir .wrangler/output
du -sh .wrangler/output/*

# Step 3: CI budget gate
npx tsx scripts/ci-size-check.ts
echo "Exit code: $?"

# Step 4: visual treemap
npx esbuild-visualizer --metadata dist/meta.json --filename dist/bundle-viz.html
open dist/bundle-viz.html
```

## Related

- `documentation/docs/policies/devtools/workers-wrangler-custom-builds.md` — esbuild configuration that produces the metafile
- `documentation/docs/policies/devtools/workers-sourcemap-debugging.md` — source maps add to upload size; coordinate budgets
- `documentation/docs/policies/devtools/workers-workerd-local-dev.md` — profile cold-start performance once size is optimized

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#worker-size
- https://esbuild.github.io/api/#metafile
- https://esbuild.github.io/api/#analyze
- https://github.com/nicolo-ribaudo/esbuild-visualizer
- https://bundlephobia.com
