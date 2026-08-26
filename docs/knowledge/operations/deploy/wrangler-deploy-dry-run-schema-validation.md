# Pre-deploy Validation Pipeline for Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to catch configuration errors, TypeScript type failures, D1 migration conflicts, and oversized bundles before any code reaches the Cloudflare network. Running a structured pre-deploy validation pipeline in CI gates every push on correctness, so broken Workers never make it to production and rollback pressure is eliminated at the source.

---

## Context

Wrangler's `--dry-run` flag compiles the Worker and writes the output to a local directory without uploading anything, making it the ideal first stage of a validation pipeline. Combined with a TypeScript type-check pass, a D1 migration dry-run, and a bundle-size assertion, you get a four-stage gate that runs entirely offline. The dry-run output directory (`--outdir dist`) contains the bundled JS and a `bundle-analysis.txt` that reports module sizes; parsing this file lets CI fail fast if the Worker exceeds Cloudflare's 10 MB script size limit or a self-imposed 1 MB budget for cold-start performance. D1's `--dry-run` flag for `migrations apply` validates SQL syntax and detects schema conflicts against the current remote schema without executing any statements. Together these four checks add under 30 seconds to a typical CI run while eliminating the most common classes of deploy-time failures.

---

## Section 1 — wrangler.toml and tsconfig

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "my-d1-database"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
migrations_dir = "migrations"

[version_metadata]
binding = "VERSION"

[build]
command = "npm run build:worker"
```

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "bundler",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noImplicitReturns": true,
    "exactOptionalPropertyTypes": true,
    "outDir": "dist",
    "rootDir": "src"
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "scripts"]
}
```

---

## Section 2 — Bundle Size Check Script

```typescript
// scripts/check-bundle-size.ts
import { readFile, stat } from 'fs/promises';
import { join } from 'path';

const MAX_BUNDLE_BYTES = 1 * 1024 * 1024; // 1 MB self-imposed limit
const CF_HARD_LIMIT_BYTES = 10 * 1024 * 1024; // 10 MB Cloudflare hard limit
const OUTDIR = process.argv[2] ?? './dist';

interface CheckResult {
  file: string;
  bytes: number;
  kb: string;
  status: 'ok' | 'warn' | 'fail';
}

async function checkBundleSize(): Promise<void> {
  const results: CheckResult[] = [];

  // Primary Worker entry bundle
  const workerPath = join(OUTDIR, 'index.js');
  try {
    const stats = await stat(workerPath);
    const bytes = stats.size;
    const status = bytes > CF_HARD_LIMIT_BYTES ? 'fail' : bytes > MAX_BUNDLE_BYTES ? 'warn' : 'ok';
    results.push({ file: 'index.js', bytes, kb: (bytes / 1024).toFixed(1), status });
  } catch {
    console.error(`ERROR: ${workerPath} not found — did wrangler dry-run complete?`);
    process.exit(1);
  }

  // Parse bundle analysis for chunk sizes
  const analysisPath = join(OUTDIR, 'bundle-analysis.txt');
  try {
    const raw = await readFile(analysisPath, 'utf8');
    const lines = raw.split('\n').filter((l) => l.includes('KiB') || l.includes('MiB'));
    console.log('\n=== Bundle Analysis ===');
    lines.forEach((l) => console.log(l));
  } catch {
    // bundle-analysis.txt is optional
  }

  // Report
  console.log('\n=== Size Gate Results ===');
  let failed = false;
  for (const r of results) {
    const icon = r.status === 'ok' ? 'PASS' : r.status === 'warn' ? 'WARN' : 'FAIL';
    console.log(`[${icon}] ${r.file}: ${r.kb} KB (limit: ${(MAX_BUNDLE_BYTES / 1024).toFixed(0)} KB)`);
    if (r.status === 'fail') failed = true;
  }

  if (failed) {
    console.error('\nBundle size exceeds Cloudflare hard limit. Deploy aborted.');
    process.exit(1);
  }

  const warned = results.some((r) => r.status === 'warn');
  if (warned) {
    console.warn('\nBundle exceeds 1 MB budget. Consider code-splitting or lazy imports.');
    // Warn only — do not fail CI for the soft limit
  }
}

checkBundleSize().catch((err) => { console.error(err); process.exit(1); });
```

---

## Section 3 — GitHub Actions Validation Pipeline

```yaml
# .github/workflows/validate-worker.yml
name: Validate Worker

on:
  push:
    branches: ['**']
  pull_request:
    types: [opened, synchronize, reopened]

env:
  CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
  CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm

      - name: Install dependencies
        run: npm ci

      # Stage 1 — TypeScript type-check (no emit)
      - name: TypeScript type-check
        run: npx tsc --noEmit

      # Stage 2 — Wrangler dry-run (compile without upload)
      - name: Wrangler dry-run
        run: |
          npx wrangler deploy --dry-run --outdir ./dist
          ls -lh ./dist/

      # Stage 3 — Bundle size gate
      - name: Check bundle size
        run: npx tsx scripts/check-bundle-size.ts ./dist

      # Stage 4 — D1 migration dry-run (requires API token for schema introspection)
      - name: D1 migration dry-run
        run: |
          npx wrangler d1 migrations apply my-d1-database \
            --dry-run \
            --remote

  deploy:
    needs: validate
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm
      - run: npm ci
      - name: Deploy to production
        run: npx wrangler deploy --tag "$(git rev-parse --short HEAD)"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

```bash
#!/usr/bin/env bash
# scripts/validate-local.sh — run the full pipeline locally before pushing
set -euo pipefail

echo "==> [1/4] TypeScript type-check"
npx tsc --noEmit
echo "PASS"

echo "==> [2/4] Wrangler dry-run"
npx wrangler deploy --dry-run --outdir ./dist
echo "PASS"

echo "==> [3/4] Bundle size gate"
npx tsx scripts/check-bundle-size.ts ./dist
echo "PASS"

echo "==> [4/4] D1 migration dry-run"
npx wrangler d1 migrations apply my-d1-database --dry-run --remote
echo "PASS"

echo ""
echo "All validation stages passed. Safe to push."
```

---

## Anti-patterns
- **Running `wrangler deploy` directly without a prior dry-run** — skipping compilation validation means syntax errors surface as live failures.
- **Setting the bundle size limit above 3 MB** — Workers above 3 MB see measurably higher cold-start latency; the 1 MB budget is a performance guardrail, not just a size concern.
- **Treating `--dry-run` as a no-op in CI** — `--dry-run` still reads `wrangler.toml` and validates binding declarations; a missing D1 database ID fails here, not silently at upload time.
- **Skipping the D1 dry-run on branches that change migrations** — migration files in branches are often reviewed only in code review; the dry-run catches SQL errors that code review misses.
- **Using `tsc --build` instead of `tsc --noEmit` in CI** — the `--build` flag writes `.js` files that can shadow the Wrangler output in `dist`, causing confusing size mismatches.

---

## Gotchas
- `wrangler deploy --dry-run` outputs the bundle to `--outdir` but does not create a `bundle-analysis.txt` in all Wrangler versions; check your version with `npx wrangler --version` (requires ≥ 3.60 for the analysis file).
- The D1 `--dry-run` flag requires a live API token and account ID even though no changes are applied; it reads the remote schema to detect conflicts.
- `npx wrangler deploy --dry-run` exits 0 even if `wrangler.toml` has unknown binding types; always pair it with the TypeScript check to catch type-level binding mismatches.
- If your Worker uses dynamic imports, the `index.js` size in `dist` does not include the chunk files; sum all `.js` file sizes for an accurate total.

---

## Verification

```bash
# Full local validation
bash scripts/validate-local.sh

# Manual dry-run and inspect output
npx wrangler deploy --dry-run --outdir ./dist
ls -lh ./dist/
wc -c ./dist/index.js

# D1 migration dry-run alone
npx wrangler d1 migrations apply my-d1-database --dry-run --remote

# TypeScript check alone
npx tsc --noEmit 2>&1 | head -30
```

---

## Related
- `workers-version-metadata-binding-deploy.md`
- `workers-assets-static-site-deploy.md`

---

## Sources
- Wrangler deploy --dry-run — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- D1 migrations apply — https://developers.cloudflare.com/d1/reference/migrations/
- Workers bundle size limits — https://developers.cloudflare.com/workers/platform/limits/#worker-size
- TypeScript with Workers — https://developers.cloudflare.com/workers/languages/typescript/
