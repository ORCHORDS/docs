# Workers Bundle Analysis and Regression CI Gate

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A routine dependency upgrade silently inflates a Workers bundle from 480 KB to
1.2 MB, pushing it above the 1 MB compressed limit and causing all production
deploys to fail with `Script startup exceeded CPU time limit`. The regression
was not caught in review because no CI step tracked bundle size between PRs.

## Context

Cloudflare Workers enforces a 10 MB uncompressed / 3 MB gzip-compressed bundle
limit for paid plans (1 MB on free). Beyond the hard limit, large bundles
increase cold-start latency because the V8 isolate must parse more JavaScript
before serving the first request. Tracking bundle size as a CI metric — with
per-PR deltas and configurable thresholds — surfaces regressions before they
reach production. `wrangler deploy --dry-run` emits size data that can be
parsed without actually deploying; `esbuild-analyze` and `bundlesize` can
complement it with module-level breakdowns.

## Extracting Bundle Metrics from Wrangler

`wrangler deploy --dry-run --outdir dist` writes the compiled bundle to disk
and prints uncompressed size to stderr. Parse the output to produce a JSON
metrics artifact.

```typescript
// scripts/bundle-stats.ts
import { execSync } from "child_process";
import fs from "fs";
import path from "path";
import zlib from "zlib";

interface BundleStats {
  workerName: string;
  uncompressedBytes: number;
  gzipBytes: number;
  timestamp: string;
  gitSha: string;
}

function measureBundle(outdir: string): BundleStats {
  fs.mkdirSync(outdir, { recursive: true });

  const output = execSync(
    `npx wrangler deploy --env production --dry-run --outdir ${outdir} 2>&1`,
    { encoding: "utf8" }
  );

  // wrangler prints: "Total Upload: 487.23 KiB / gzip: 142.18 KiB"
  const match = output.match(
    /Total Upload:\s+([\d.]+)\s+(\w+)\s*\/\s*gzip:\s+([\d.]+)\s+(\w+)/
  );
  if (!match) throw new Error(`Could not parse wrangler output:\n${output}`);

  const toBytes = (val: string, unit: string) => {
    const n = parseFloat(val);
    if (unit === "KiB") return Math.round(n * 1024);
    if (unit === "MiB") return Math.round(n * 1024 * 1024);
    return Math.round(n);
  };

  return {
    workerName: "api-worker",
    uncompressedBytes: toBytes(match[1], match[2]),
    gzipBytes: toBytes(match[3], match[4]),
    timestamp: new Date().toISOString(),
    gitSha: execSync("git rev-parse HEAD", { encoding: "utf8" }).trim(),
  };
}

const stats = measureBundle("dist");
fs.writeFileSync("bundle-stats.json", JSON.stringify(stats, null, 2));
console.log(
  `Bundle: ${(stats.uncompressedBytes / 1024).toFixed(1)} KiB ` +
    `(gzip: ${(stats.gzipBytes / 1024).toFixed(1)} KiB)`
);
```

## CI Gate with Delta Comparison

Download the baseline from the `main` branch artifact store, compare against
the current PR build, and fail if gzip size grows by more than the threshold.

```typescript
// scripts/bundle-gate.ts
import fs from "fs";

const GZIP_LIMIT_BYTES = 3 * 1024 * 1024;   // 3 MiB hard limit
const REGRESSION_THRESHOLD = 0.05;            // fail if gzip grows > 5%
const ABSOLUTE_ALERT_BYTES = 50 * 1024;       // also fail if delta > 50 KiB

interface BundleStats {
  uncompressedBytes: number;
  gzipBytes: number;
  gitSha: string;
}

function loadStats(filePath: string): BundleStats {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

async function gate() {
  const current = loadStats("bundle-stats.json");

  if (!fs.existsSync("baseline-stats.json")) {
    console.log("No baseline found — skipping delta check (first run).");
    if (current.gzipBytes > GZIP_LIMIT_BYTES) {
      console.error(
        `FAIL: bundle ${(current.gzipBytes / 1024 / 1024).toFixed(2)} MiB ` +
          `exceeds hard limit of 3 MiB`
      );
      process.exit(1);
    }
    return;
  }

  const baseline = loadStats("baseline-stats.json");
  const deltaBytes = current.gzipBytes - baseline.gzipBytes;
  const deltaPercent = deltaBytes / baseline.gzipBytes;

  console.log(`Baseline gzip : ${(baseline.gzipBytes / 1024).toFixed(1)} KiB`);
  console.log(`Current  gzip : ${(current.gzipBytes / 1024).toFixed(1)} KiB`);
  console.log(
    `Delta         : ${deltaBytes > 0 ? "+" : ""}${(deltaBytes / 1024).toFixed(1)} KiB` +
      ` (${(deltaPercent * 100).toFixed(1)}%)`
  );

  const failures: string[] = [];

  if (current.gzipBytes > GZIP_LIMIT_BYTES) {
    failures.push(
      `gzip size ${(current.gzipBytes / 1024 / 1024).toFixed(2)} MiB exceeds 3 MiB limit`
    );
  }
  if (deltaPercent > REGRESSION_THRESHOLD) {
    failures.push(
      `gzip grew by ${(deltaPercent * 100).toFixed(1)}% (threshold: ${REGRESSION_THRESHOLD * 100}%)`
    );
  }
  if (deltaBytes > ABSOLUTE_ALERT_BYTES) {
    failures.push(
      `gzip grew by ${(deltaBytes / 1024).toFixed(0)} KiB (threshold: ${ABSOLUTE_ALERT_BYTES / 1024} KiB)`
    );
  }

  if (failures.length > 0) {
    console.error("BUNDLE REGRESSION DETECTED:");
    failures.forEach((f) => console.error(`  - ${f}`));
    process.exit(1);
  }

  console.log("Bundle gate passed.");
}

gate();
```

## GitHub Actions Integration

```yaml
# .github/workflows/bundle-gate.yml
name: Bundle Size Gate
on:
  pull_request:
    branches: [main]

jobs:
  bundle-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with: { node-version: "22" }

      - run: npm ci

      # Build current PR bundle
      - run: npx tsx scripts/bundle-stats.ts
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}

      # Download baseline from last successful main build
      - uses: dawidd6/action-download-artifact@v6
        continue-on-error: true
        with:
          name: bundle-stats
          branch: main
          workflow: bundle-gate.yml
          path: .
          rename_to: baseline-stats.json

      # Enforce size gate
      - run: npx tsx scripts/bundle-gate.ts

      # Upload this build's stats as the new baseline candidate
      - uses: actions/upload-artifact@v4
        if: github.ref == 'refs/heads/main'
        with:
          name: bundle-stats
          path: bundle-stats.json
          retention-days: 90
```

## Anti-patterns

- Relying on `wrangler deploy` to fail at the upload step to catch size
  regressions; the failure is opaque and happens after the deployment has
  partially processed.
- Setting a single absolute byte threshold without a percentage gate;
  a 50 KiB addition is irrelevant at 200 KiB but catastrophic at 950 KiB.
- Measuring uncompressed size only — Cloudflare enforces the gzip limit,
  and a bundle full of repetitive strings may compress much better than the
  raw bytes suggest.

## Gotchas

- `wrangler deploy --dry-run` still contacts Cloudflare to resolve bindings
  and account limits; the `CLOUDFLARE_API_TOKEN` must have Workers read
  permissions even for dry runs.
- Workers with multiple entrypoints (e.g., a main Worker + Durable Object
  class) each have separate size accounting; measure them individually.

## Verification

```bash
# Manual bundle measurement without CI
npx tsx scripts/bundle-stats.ts
cat bundle-stats.json | jq '{gzipKiB: (.gzipBytes/1024 | round)}'

# Check current live worker size via API
curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/scripts/api-worker" \
  | jq '.result.size'
```

## Related

- `deploy/deploy-artifact-build-parity-ci-gate.md`
- `deploy/merged-is-not-deployed-bundle-verification.md`
- `deploy/cloudflare-worker-cpu-time-limits-optimization.md`

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#worker-size
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://esbuild.github.io/analyze/
