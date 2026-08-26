# Workers Bundle Analysis with esbuild Metafile

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare Workers have a 1 MB (uncompressed) script size limit for free plans and 10 MB for paid plans. As a project grows, third-party dependencies silently inflate the bundle. Using the esbuild metafile produced by `wrangler deploy --dry-run` lets you identify the largest contributors, visualise the bundle as a treemap with `bundle-buddy`, and enforce a size budget in CI with a pass/fail gate comparing against a KV-stored baseline.

---

## Context

Wrangler uses esbuild internally to bundle TypeScript Workers. When you pass `--dry-run --outdir dist`, wrangler runs the full build pipeline and writes the output files to `dist/` without uploading anything. Adding `--metafile` causes wrangler to emit `dist/metafile.json` — the standard esbuild metafile format. The `esbuild.analyzeMetafile()` API (included in the `esbuild` npm package) parses this file and produces a human-readable report sorted by input size. `bundle-buddy` consumes the same metafile and renders an interactive treemap in the browser. The CI step reads the previous baseline from a Cloudflare KV namespace (via the REST API), compares the new total, and fails the build on regression beyond a configurable threshold.

---

## Config / Setup

```toml
# wrangler.toml
name = "my-worker"
compatibility_date = "2024-09-23"
main = "src/index.ts"

# KV namespace used to store the bundle-size baseline
[[kv_namespaces]]
binding  = "BUNDLE_BASELINE"
id       = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
preview_id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
```

```jsonc
// package.json
{
  "scripts": {
    "build:dry"    : "wrangler deploy --dry-run --outdir dist",
    "bundle:analyze": "npm run build:dry && node scripts/analyze-bundle.mjs",
    "bundle:treemap": "npm run build:dry && npx bundle-buddy dist/metafile.json"
  },
  "devDependencies": {
    "esbuild"     : "^0.23.0",
    "bundle-buddy" : "^0.3.0"
  }
}
```

---

## Implementation — Bundle Analyser Script

```typescript
// scripts/analyze-bundle.mjs
// Run after: wrangler deploy --dry-run --outdir dist
import { readFileSync, statSync, writeFileSync } from 'node:fs';
import { resolve }                               from 'node:path';
import esbuild                                   from 'esbuild';

const ROOT        = resolve(import.meta.dirname, '..');
const METAFILE    = resolve(ROOT, 'dist', 'metafile.json');
const REPORT_OUT  = resolve(ROOT, 'dist', 'bundle-report.txt');
const SIZE_LIMIT  = parseInt(process.env.BUNDLE_SIZE_LIMIT ?? String(1 * 1024 * 1024), 10); // 1 MB default

// --- Parse metafile -----------------------------------------------------
const metafileRaw  = readFileSync(METAFILE, 'utf8');
const metafile     = JSON.parse(metafileRaw);

// --- esbuild text report ------------------------------------------------
const report = await esbuild.analyzeMetafile(metafile, {
  verbose: false,   // set true for per-export breakdown
});
console.log(report);
writeFileSync(REPORT_OUT, report, 'utf8');
console.log(`[analyze] Report written to ${REPORT_OUT}`);

// --- Total bundle size --------------------------------------------------
const outputFiles = Object.entries(metafile.outputs);
let totalBytes    = 0;
for (const [outPath] of outputFiles) {
  try {
    totalBytes += statSync(resolve(ROOT, outPath)).size;
  } catch {
    // Some virtual outputs may not be on disk
  }
}

const totalKB = (totalBytes / 1024).toFixed(1);
console.log(`\n[analyze] Total bundle size: ${totalKB} KB (limit: ${(SIZE_LIMIT / 1024).toFixed(0)} KB)`);

// --- Top 10 inputs by size ---------------------------------------------
const inputs = Object.entries(metafile.inputs as Record<string, { bytes: number }>)
  .map(([id, meta]) => ({ id, bytes: meta.bytes }))
  .sort((a, b) => b.bytes - a.bytes)
  .slice(0, 10);

console.log('\n[analyze] Top 10 input files by size:');
for (const { id, bytes } of inputs) {
  console.log(`  ${(bytes / 1024).toFixed(1).padStart(7)} KB  ${id}`);
}

// --- Size-limit gate ---------------------------------------------------
if (totalBytes > SIZE_LIMIT) {
  console.error(
    `\n[analyze] FAIL: bundle size ${totalKB} KB exceeds limit ` +
    `${(SIZE_LIMIT / 1024).toFixed(0)} KB`
  );
  process.exit(1);
}
```

```typescript
// scripts/update-baseline.mjs
// Stores the current bundle size in Cloudflare KV via the REST API.
// Run after a successful deploy to main.
import { readFileSync, statSync } from 'node:fs';
import { resolve }                from 'node:path';

const CF_ACCOUNT_ID    = process.env.CF_ACCOUNT_ID;
const CF_API_TOKEN     = process.env.CF_API_TOKEN;
const KV_NAMESPACE_ID  = process.env.KV_NAMESPACE_ID;
const METAFILE         = resolve(import.meta.dirname, '..', 'dist', 'metafile.json');

if (!CF_ACCOUNT_ID || !CF_API_TOKEN || !KV_NAMESPACE_ID) {
  console.error('[baseline] Missing required env vars: CF_ACCOUNT_ID, CF_API_TOKEN, KV_NAMESPACE_ID');
  process.exit(1);
}

// Compute total size
const metafile    = JSON.parse(readFileSync(METAFILE, 'utf8'));
let   totalBytes  = 0;
for (const outPath of Object.keys(metafile.outputs)) {
  try { totalBytes += statSync(resolve('..', outPath)).size; } catch { /* skip */ }
}

const payload = JSON.stringify({ totalBytes, updatedAt: new Date().toISOString() });
const url     = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${KV_NAMESPACE_ID}/values/bundle-size-baseline`;

const resp = await fetch(url, {
  method  : 'PUT',
  headers : { 'Authorization': `Bearer ${CF_API_TOKEN}`, 'Content-Type': 'text/plain' },
  body    : payload,
});

if (!resp.ok) {
  const body = await resp.text();
  console.error(`[baseline] KV write failed: ${resp.status} ${body}`);
  process.exit(1);
}
console.log(`[baseline] Stored baseline: ${(totalBytes / 1024).toFixed(1)} KB`);
```

```typescript
// scripts/check-baseline.mjs
// Compares current bundle size against the KV baseline.
// Fails if the increase exceeds REGRESSION_THRESHOLD_KB.
import { readFileSync, statSync } from 'node:fs';
import { resolve }                from 'node:path';

const CF_ACCOUNT_ID       = process.env.CF_ACCOUNT_ID;
const CF_API_TOKEN        = process.env.CF_API_TOKEN;
const KV_NAMESPACE_ID     = process.env.KV_NAMESPACE_ID;
const REGRESSION_KB       = parseFloat(process.env.REGRESSION_THRESHOLD_KB ?? '50');
const METAFILE            = resolve(import.meta.dirname, '..', 'dist', 'metafile.json');

// Read current size
const metafile  = JSON.parse(readFileSync(METAFILE, 'utf8'));
let   curBytes  = 0;
for (const p of Object.keys(metafile.outputs)) {
  try { curBytes += statSync(resolve('..', p)).size; } catch { /* skip */ }
}

// Fetch baseline from KV
const url      = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${KV_NAMESPACE_ID}/values/bundle-size-baseline`;
const resp     = await fetch(url, { headers: { 'Authorization': `Bearer ${CF_API_TOKEN}` } });

if (resp.status === 404) {
  console.log('[check-baseline] No baseline yet — skipping regression check.');
  process.exit(0);
}
if (!resp.ok) {
  console.error(`[check-baseline] Could not fetch baseline: ${resp.status}`);
  process.exit(1);
}

const baseline      = JSON.parse(await resp.text()) as { totalBytes: number; updatedAt: string };
const deltaKB       = (curBytes - baseline.totalBytes) / 1024;
const baselineKB    = (baseline.totalBytes / 1024).toFixed(1);
const curKB         = (curBytes / 1024).toFixed(1);

console.log(`[check-baseline] Baseline: ${baselineKB} KB  Current: ${curKB} KB  Delta: ${deltaKB.toFixed(1)} KB`);

if (deltaKB > REGRESSION_KB) {
  console.error(
    `[check-baseline] FAIL: bundle grew by ${deltaKB.toFixed(1)} KB ` +
    `(threshold: ${REGRESSION_KB} KB). Baseline from ${baseline.updatedAt}.`
  );
  process.exit(1);
}
console.log('[check-baseline] OK — within threshold.');
```

---

## CI Integration

```yaml
# .github/workflows/bundle-size.yml
name: Bundle size check
on: [push, pull_request]

jobs:
  bundle:
    runs-on: ubuntu-latest
    env:
      CF_ACCOUNT_ID    : ${{ secrets.CF_ACCOUNT_ID }}
      CF_API_TOKEN     : ${{ secrets.CF_API_TOKEN }}
      KV_NAMESPACE_ID  : ${{ secrets.BUNDLE_KV_NAMESPACE_ID }}
      REGRESSION_THRESHOLD_KB: '50'
      BUNDLE_SIZE_LIMIT: '1048576'   # 1 MB in bytes

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - run: npm ci

      - name: Dry-run build (generate metafile)
        run: npm run build:dry

      - name: Analyse bundle and enforce size limit
        run: node scripts/analyze-bundle.mjs

      - name: Check regression against KV baseline
        run: node scripts/check-baseline.mjs

      - name: Upload bundle report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: bundle-report
          path: |
            dist/bundle-report.txt
            dist/metafile.json

      - name: Update KV baseline (main branch only)
        if: github.ref == 'refs/heads/main' && success()
        run: node scripts/update-baseline.mjs
```

---

## Anti-patterns

- **Running `wrangler deploy` (without `--dry-run`) just to get the metafile** — this deploys potentially broken code to production; always use `--dry-run` for analysis.
- **Setting an absolute size limit without a relative regression check** — a project already near the limit will keep failing CI even with no regression; combine both gates.
- **Storing the baseline in a file committed to the repo** — baselines committed to git cause noisy diffs and merge conflicts; KV or a CI-cached artifact is the right store.
- **Ignoring node_modules paths in the metafile** — the biggest wins almost always come from third-party packages; filter *to* `node_modules` entries, not away from them.
- **Using `esbuild.analyzeMetafile()` synchronously** — it returns a `Promise`; always `await` it or you will print `[object Promise]`.

---

## Gotchas

- `wrangler deploy --dry-run --outdir dist` does not emit `metafile.json` by default in all wrangler versions; if the file is missing, check that your wrangler version is ≥ 3.70 and try adding `--metafile` explicitly.
- The `statSync` approach to compute total bundle bytes works for standard output files but misses inline source maps embedded inside the JS. Use `Buffer.byteLength(readFileSync(p))` for byte-accurate counts.
- `bundle-buddy` expects the metafile at a URL or local path and opens a browser tab; in CI, rely on `esbuild.analyzeMetafile()` instead.
- KV `PUT` via REST API requires the `Workers KV Storage Write` permission on the API token; the same token used for `wrangler deploy` usually has it, but verify in the Cloudflare dashboard.
- The `REGRESSION_THRESHOLD_KB` env var should be tuned per project; 50 KB is generous for small Workers but may be too tight for a Worker that legitimately bundles a large data file.

---

## Verification

```bash
# 1. Dry-run build
npm run build:dry
ls -lh dist/

# 2. Verify metafile exists
jq 'keys' dist/metafile.json

# 3. Analyse and print report
node scripts/analyze-bundle.mjs

# 4. Open treemap in browser (local only)
npx bundle-buddy dist/metafile.json

# 5. Simulate regression check (with fake baseline 10 MB to force pass)
KV_NAMESPACE_ID=fake CF_ACCOUNT_ID=fake CF_API_TOKEN=fake \
  REGRESSION_THRESHOLD_KB=999999 node scripts/check-baseline.mjs || true
```

---

## Related

- `eslint-workers-compatibility-lint-rules.md`
- `wrangler-tail-structured-log-parsing.md`

---

## Sources

- esbuild analyzeMetafile API — https://esbuild.github.io/api/#analyze
- Wrangler deploy --dry-run — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- bundle-buddy npm — https://www.npmjs.com/package/bundle-buddy
- Cloudflare KV REST API — https://developers.cloudflare.com/api/operations/workers-kv-namespace-write-key-value-pair-with-metadata
- Cloudflare Workers size limits — https://developers.cloudflare.com/workers/platform/limits/#worker-size
