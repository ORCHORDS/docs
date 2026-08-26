# Workers Bundle Size Headroom Monitoring and CI Gate

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare Workers have a hard **1 MB compressed / 5 MB uncompressed** bundle size
limit (Free plan: 1 MB uncompressed; Paid: 5 MB uncompressed). On a large TypeScript
monorepo like example project, adding a new dependency or a heavy polyfill can silently push the
bundle toward the limit. Deploys fail in CI with an opaque "Script too large" error
only after the bundle has already exceeded the cap.

This article implements a CI gate that fails the pull-request build when the gzip-
compressed bundle exceeds a configurable headroom threshold (default: 80% of limit),
tracks historical bundle sizes in Analytics Engine, and surfaces trends in a dashboard.

---

## Context

example project builds its Workers with `wrangler build` which outputs to `.wrangler/tmp/`. The
compressed size is available after build and before deploy. By measuring it in CI and
comparing against a per-Worker baseline stored in a KV namespace, the gate can also
detect unexpected regressions (a single PR adding > 50 KB compressed) independently
of the absolute limit.

Limits (as of mid-2026):
- **Free** Workers: 1 MB uncompressed script.
- **Paid** Workers: 5 MB uncompressed, effectively ~1.5 MB gzip-compressed for the
  dense TypeScript bundles example project produces.

The gate targets gzip-compressed size because that is what Cloudflare measures for
the upload quota.

---

## Bundle Size Measurement Script

```typescript
// scripts/measure-bundle-size.ts
// Run after `wrangler build` in CI.
// Usage: npx ts-node scripts/measure-bundle-size.ts --worker example project-api --limit 1500000

import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { promisify } from 'node:util';

const gzip = promisify(zlib.gzip);

interface Options {
  worker: string;
  limitBytes: number;    // gzip-compressed limit
  thresholdPct: number;  // fail if size > limit * thresholdPct / 100
  baselineFile?: string; // JSON file with { [worker]: number } baseline sizes
  regressionKb: number;  // fail if size grew by more than this vs baseline
}

async function measureBundle(opts: Options): Promise<void> {
  const buildDir = path.join(process.cwd(), '.wrangler', 'tmp');
  const entries = fs.readdirSync(buildDir).filter((f) => f.endsWith('.js'));

  if (entries.length === 0) {
    console.error('No build output found in .wrangler/tmp/');
    process.exit(1);
  }

  // Sum all JS chunks (some Workers produce multiple chunks)
  let totalUncompressed = 0;
  let totalCompressed = 0;

  for (const entry of entries) {
    const buf = fs.readFileSync(path.join(buildDir, entry));
    totalUncompressed += buf.length;
    const compressed = await gzip(buf, { level: 9 });
    totalCompressed += compressed.length;
  }

  const headroomLimit = Math.floor(opts.limitBytes * opts.thresholdPct / 100);
  const pct = ((totalCompressed / opts.limitBytes) * 100).toFixed(1);

  console.log(`Worker: ${opts.worker}`);
  console.log(`  Uncompressed : ${(totalUncompressed / 1024).toFixed(1)} KB`);
  console.log(`  Gzip         : ${(totalCompressed / 1024).toFixed(1)} KB`);
  console.log(`  Limit        : ${(opts.limitBytes / 1024).toFixed(1)} KB`);
  console.log(`  Usage        : ${pct}%`);

  let failed = false;

  if (totalCompressed > headroomLimit) {
    console.error(
      `FAIL: bundle ${(totalCompressed / 1024).toFixed(1)} KB exceeds ` +
      `${opts.thresholdPct}% headroom (${(headroomLimit / 1024).toFixed(1)} KB)`,
    );
    failed = true;
  }

  if (opts.baselineFile && fs.existsSync(opts.baselineFile)) {
    const baseline = JSON.parse(fs.readFileSync(opts.baselineFile, 'utf-8')) as Record<string, number>;
    const baselineSize = baseline[opts.worker];
    if (baselineSize) {
      const deltaKb = (totalCompressed - baselineSize) / 1024;
      if (deltaKb > opts.regressionKb) {
        console.error(
          `FAIL: bundle grew ${deltaKb.toFixed(1)} KB vs baseline ` +
          `(limit: ${opts.regressionKb} KB)`,
        );
        failed = true;
      } else {
        console.log(`  Delta vs baseline: ${deltaKb > 0 ? '+' : ''}${deltaKb.toFixed(1)} KB`);
      }
    }
  }

  // Emit JSON for CI summary annotation
  const output = {
    worker: opts.worker,
    uncompressedBytes: totalUncompressed,
    gzipBytes: totalCompressed,
    limitBytes: opts.limitBytes,
    usagePct: parseFloat(pct),
    passed: !failed,
  };
  fs.writeFileSync('bundle-size-report.json', JSON.stringify(output, null, 2));

  if (failed) process.exit(1);
}

// Parse CLI args
const args = process.argv.slice(2);
const get = (flag: string, def: string) => {
  const i = args.indexOf(flag);
  return i >= 0 ? args[i + 1] : def;
};

measureBundle({
  worker: get('--worker', 'unknown'),
  limitBytes: parseInt(get('--limit', '1500000'), 10),
  thresholdPct: parseInt(get('--threshold', '80'), 10),
  baselineFile: get('--baseline', ''),
  regressionKb: parseInt(get('--regression-kb', '50'), 10),
});
```

---

## GitHub Actions CI Gate

```yaml
# .github/workflows/bundle-size.yml
name: Workers Bundle Size Gate

on:
  pull_request:
    paths:
      - 'src/**'
      - 'package.json'
      - 'package-lock.json'
      - 'wrangler.toml'

jobs:
  bundle-size:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        worker: [example project-api, example project-auth, example project-webhooks]
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'

      - run: npm ci

      - name: Build ${{ matrix.worker }}
        run: npx wrangler build --name ${{ matrix.worker }}

      - name: Check bundle size
        run: |
          npx ts-node scripts/measure-bundle-size.ts \
            --worker ${{ matrix.worker }} \
            --limit 1500000 \
            --threshold 80 \
            --baseline .bundle-baselines.json \
            --regression-kb 50

      - name: Annotate PR with size report
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = JSON.parse(fs.readFileSync('bundle-size-report.json', 'utf-8'));
            const icon = report.passed ? '✅' : '❌';
            const body = `${icon} **${{ matrix.worker }}** bundle size: ` +
              `${(report.gzipBytes / 1024).toFixed(1)} KB gzip ` +
              `(${report.usagePct}% of ${(report.limitBytes / 1024).toFixed(0)} KB limit)`;
            await github.rest.issues.createComment({
              ...context.repo,
              issue_number: context.issue.number,
              body,
            });
```

---

## Emit Size to Analytics Engine on Deploy

```typescript
// src/workers/deploy-hook.ts
// Called by a post-deploy GitHub Actions step to record the final deployed size.

interface Env {
  AE: AnalyticsEngineDataset;
  DEPLOY_TOKEN: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.headers.get('Authorization') !== `Bearer ${env.DEPLOY_TOKEN}`) {
      return new Response('Forbidden', { status: 403 });
    }

    const {
      worker,
      gzipBytes,
      uncompressedBytes,
      gitSha,
      branch,
    } = await request.json<{
      worker: string;
      gzipBytes: number;
      uncompressedBytes: number;
      gitSha: string;
      branch: string;
    }>();

    env.AE.writeDataPoint({
      blobs: [worker, branch, gitSha.slice(0, 8)],
      doubles: [gzipBytes, uncompressedBytes],
      indexes: [worker],
    });

    return new Response('OK');
  },
} satisfies ExportedHandler<Env>;
```

---

## Analytics Engine Trend Queries

```sql
-- Bundle size trend over last 30 deploys per worker
SELECT
  timestamp,
  blob1                       AS worker,
  blob2                       AS branch,
  blob3                       AS git_sha,
  double1 / 1024              AS gzip_kb,
  double2 / 1024              AS uncompressed_kb
FROM example project_BUNDLE_SIZES
WHERE blob2 = 'main'
ORDER BY timestamp DESC
LIMIT 30;

-- Week-over-week size change per worker
WITH weekly AS (
  SELECT
    blob1                                       AS worker,
    toStartOfWeek(timestamp)                    AS wk,
    AVG(double1)                                AS avg_gzip_bytes
  FROM example project_BUNDLE_SIZES
  WHERE timestamp >= NOW() - INTERVAL '14' DAY
  GROUP BY worker, wk
)
SELECT
  a.worker,
  a.avg_gzip_bytes / 1024                      AS this_week_kb,
  b.avg_gzip_bytes / 1024                      AS last_week_kb,
  (a.avg_gzip_bytes - b.avg_gzip_bytes) / 1024 AS delta_kb
FROM weekly a
JOIN weekly b ON a.worker = b.worker AND a.wk > b.wk
ORDER BY delta_kb DESC;
```

---

## Updating the Baseline File

```bash
# After a deliberate size increase is approved, regenerate the baseline:
node -e "
const sizes = {};
['example project-api','example project-auth','example project-webhooks'].forEach(w => {
  const report = JSON.parse(require('fs').readFileSync(\`bundle-size-\${w}.json\`,'utf-8'));
  sizes[w] = report.gzipBytes;
});
require('fs').writeFileSync('.bundle-baselines.json', JSON.stringify(sizes, null, 2));
"
git add .bundle-baselines.json
git commit -m "chore: update bundle size baselines after dependency upgrade"
```

---

## Anti-patterns

- **Measuring uncompressed size for the limit check** — Cloudflare enforces the
  compressed size for the upload quota; always gzip before comparing.
- **Single global baseline for all branches** — feature branches legitimately grow;
  compare against the `main` branch baseline, not a shared file committed per-PR.
- **Failing the gate on any growth** — trivial one-liner additions grow the bundle by
  a few hundred bytes; use an absolute regression threshold (e.g. 50 KB).
- **Omitting the wasm chunk from measurement** — `wrangler build` may emit a `.wasm`
  file alongside the JS; include all build artefacts in the size sum.

---

## Gotchas

- `wrangler build` output lives in `.wrangler/tmp/` by default but the path can change
  with `--outdir`. Confirm the path in your `wrangler.toml` or pass `--outdir` explicitly.
- Tree-shaking effectiveness varies by import style; `import * as foo from 'pkg'`
  typically produces larger bundles than named imports.
- Source maps are NOT uploaded to Cloudflare and must NOT be included in the size
  measurement; filter for `.js` and `.wasm` files only.
- The gzip level used by Cloudflare at upload time may differ from `zlib.Z_BEST_COMPRESSION`;
  a small discrepancy (< 2%) between CI measurement and actual deployed size is normal.

---

## Verification

```bash
# Build locally and check size
npx wrangler build --name example project-api
ls -lh .wrangler/tmp/*.js | awk '{print $5, $9}'

# Confirm Analytics Engine is receiving deploy size events
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT blob1, double1/1024 AS gzip_kb FROM example project_BUNDLE_SIZES ORDER BY timestamp DESC LIMIT 10"}' \
  | jq '.data'
```

---

## Related

- `workers-subrequest-limit-headroom-monitoring.md`
- `performance-regression-ci-workers-baseline.md`
- `d1-explain-query-plan-slow-query-automation.md`
- `cloudflare-workers-analytics.md`
- `monitoring-as-code.md`

---

## Sources

- Workers limits: https://developers.cloudflare.com/workers/platform/limits/
- wrangler build docs: https://developers.cloudflare.com/workers/wrangler/commands/#build
- Analytics Engine worker binding: https://developers.cloudflare.com/analytics/analytics-engine/worker-binding/
- Node.js zlib API: https://nodejs.org/api/zlib.html
