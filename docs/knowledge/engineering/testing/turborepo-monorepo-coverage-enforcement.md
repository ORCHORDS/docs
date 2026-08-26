# Test Coverage Enforcement in Monorepo with Turborepo Pipelines

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You run a Turborepo monorepo that spans multiple Cloudflare Workers, a Next.js front-end on
Cloudflare Pages, and shared utility packages. CI passes even when a new package ships with 0%
coverage because each workspace enforces its own threshold locally and Turborepo caches the
`test` task output — a previously green result is replayed without re-running the suite. You
need aggregate and per-package coverage gates that cannot be bypassed by the cache, that fail
fast on the right workspace, and that surface a unified report upstream.

## Context

Turborepo's task graph executes `test` per-package in dependency order. By default the result of
each task is cached keyed by its inputs (source files, config, lock-file hash). Coverage data
lives in `coverage/` directories that are **outputs** of the test task, so the cache stores them.
When a downstream pipeline step tries to aggregate coverage it may see stale files from a cache
hit — or no files at all if `outputs` is not declared correctly.

Coverage enforcement therefore has two layers:

1. **Per-package threshold** — each workspace owns a vitest/jest config with a `coverageThreshold`
   that causes that workspace's `test` script to exit non-zero on failure.
2. **Aggregate gate** — a dedicated Turborepo task (or a CI step that depends on all `test` tasks)
   merges LCOV files and checks a project-wide threshold.

Stack: Turborepo 2.x, Vitest 2.x (or Jest 30), `c8`/`istanbul`, GitHub Actions.

---

## Configuring Per-Package Thresholds

### vitest.config.ts (per workspace)

```ts
// packages/workers-api/vitest.config.ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'miniflare',
    environmentOptions: {
      modules: true,
      kvNamespaces: ['TEST_KV'],
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'json-summary'],
      // lcov.info lands at coverage/lcov.info by default
      reportsDirectory: './coverage',
      thresholds: {
        lines: 80,
        branches: 75,
        functions: 80,
        statements: 80,
        // Fail the task if below threshold
        perFile: false,
        autoUpdate: false,
      },
      // Do not count generated types or migration files
      exclude: [
        'src/**/*.d.ts',
        'src/db/migrations/**',
        'src/generated/**',
        'vitest.config.ts',
      ],
    },
  },
});
```

### package.json test script (per workspace)

```json
{
  "scripts": {
    "test": "vitest run --coverage",
    "test:watch": "vitest --coverage"
  }
}
```

Vitest exits non-zero when any threshold is violated, so Turborepo marks the task as failed and
stops dependents.

---

## Turborepo Pipeline Configuration

### turbo.json

```jsonc
{
  "$schema": "https://turbo.build/schema.json",
  "pipeline": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": [".next/**", "dist/**", ".worker/**"]
    },
    "test": {
      "dependsOn": ["^build"],
      // Declare coverage/ as an output so it is cached and can be
      // consumed by the coverage-merge task even on cache hits.
      "outputs": ["coverage/**"],
      // Include test files and vitest config in the cache key.
      "inputs": [
        "src/**",
        "test/**",
        "vitest.config.*",
        "jest.config.*",
        "tsconfig.json"
      ],
      "cache": true
    },
    "coverage:merge": {
      // Must run after every workspace's test task finishes.
      "dependsOn": ["^test", "test"],
      // Never cache — always re-aggregate from fresh coverage outputs.
      "cache": false,
      "outputs": ["coverage-merged/**"]
    }
  }
}
```

Key insight: declaring `"outputs": ["coverage/**"]` in the `test` pipeline entry tells Turborepo
to restore that directory from cache on a hit. Without this, the coverage directory is absent when
the cache is replayed and the merge step silently produces a partial aggregate.

---

## Aggregate Coverage Gate

### Root-level package.json

```json
{
  "scripts": {
    "test": "turbo run test",
    "coverage:merge": "turbo run coverage:merge",
    "ci:coverage": "turbo run test && node scripts/merge-coverage.mjs"
  }
}
```

### scripts/merge-coverage.mjs

```js
#!/usr/bin/env node
/**
 * Merges per-package lcov.info files into one and enforces an aggregate
 * threshold using @lcov-viewer/cli (pure JS, no native deps).
 *
 * Install: pnpm add -Dw @lcov-viewer/cli
 */
import { execSync } from 'node:child_process';
import { globSync } from 'glob';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const AGGREGATE_THRESHOLD = 78; // percent lines covered across all packages

const lcovFiles = globSync('packages/*/coverage/lcov.info', {
  cwd: process.cwd(),
  absolute: true,
});

if (lcovFiles.length === 0) {
  console.error('No lcov.info files found. Did all test tasks run with --coverage?');
  process.exit(1);
}

// Concatenate — lcov format is simply line-delimited records, safe to cat.
const merged = lcovFiles.map(f => readFileSync(f, 'utf8')).join('\n');

mkdirSync('coverage-merged', { recursive: true });
writeFileSync('coverage-merged/lcov.info', merged);

console.log(`Merged ${lcovFiles.length} coverage files → coverage-merged/lcov.info`);

// Use lcov's genhtml or a JS equivalent to compute summary.
// Here we use a simple line-counting approach for CI speed.
const linesFound = [...merged.matchAll(/^LF:(\d+)/gm)].reduce(
  (sum, m) => sum + Number(m[1]), 0,
);
const linesHit = [...merged.matchAll(/^LH:(\d+)/gm)].reduce(
  (sum, m) => sum + Number(m[1]), 0,
);

if (linesFound === 0) {
  console.error('Merged coverage reports 0 lines found. Check output paths.');
  process.exit(1);
}

const pct = ((linesHit / linesFound) * 100).toFixed(2);
console.log(`Aggregate line coverage: ${pct}% (${linesHit}/${linesFound})`);

if (Number(pct) < AGGREGATE_THRESHOLD) {
  console.error(
    `FAIL: aggregate coverage ${pct}% is below threshold ${AGGREGATE_THRESHOLD}%`,
  );
  process.exit(1);
}

console.log(`PASS: aggregate coverage ${pct}% >= ${AGGREGATE_THRESHOLD}%`);
```

---

## GitHub Actions Integration

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # needed for turbo --filter=...[HEAD^1]

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      # Turborepo remote cache (optional but recommended)
      - name: Restore Turborepo cache
        uses: actions/cache@v4
        with:
          path: .turbo
          key: turbo-${{ runner.os }}-${{ hashFiles('pnpm-lock.yaml') }}-${{ github.sha }}
          restore-keys: |
            turbo-${{ runner.os }}-${{ hashFiles('pnpm-lock.yaml') }}-

      # Run tests for all packages; each exits non-zero if its threshold fails.
      - name: Run tests with coverage
        run: pnpm turbo run test --cache-dir=.turbo

      # Aggregate gate runs even if individual packages all pass.
      - name: Check aggregate coverage
        run: node scripts/merge-coverage.mjs

      # Upload merged LCOV for GitHub PR annotation.
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          files: coverage-merged/lcov.info
          flags: monorepo
          fail_ci_if_error: true
        env:
          CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}

      # Persist merged report as artifact for download.
      - name: Upload coverage artifact
        uses: actions/upload-artifact@v4
        with:
          name: coverage-merged
          path: coverage-merged/
          retention-days: 14
```

---

## Anti-patterns

**Omitting `outputs: ["coverage/**"]` from turbo.json `test` task.**
The coverage directory is not restored from cache on a hit. The merge step then either
aggregates empty data or silently skips packages that had cache hits, producing a falsely
elevated aggregate percentage.

**Running the merge script before `turbo run test` completes.**
Turborepo runs tasks in parallel across packages; if the merge is a separate CI step that does
not `dependsOn` all `test` tasks, it can start before slow packages finish. Always either (a)
use a Turborepo task that declares `dependsOn: ["^test"]`, or (b) sequence the steps in CI so
the merge only starts after `turbo run test` exits.

**Setting per-package thresholds too low to avoid fixing coverage, then relying on the
aggregate gate.**
This hides completely untested packages behind a healthy overall average. Enforce a minimum
per-package threshold (e.g. 60%) in addition to the aggregate gate.

**Using `--filter=...[HEAD^1]` (affected packages only) for coverage gates on PRs.**
Affected-only runs skip packages that were not changed. A PR that deletes tests in package A
while adding code to package B will only run B's tests; A's degraded coverage is invisible.
Run full coverage on every PR, or use remote caching so unchanged packages replay from cache
instantly and cost almost no time.

---

## Gotchas

- **`pnpm -r run test` vs `turbo run test`** — `pnpm -r` runs scripts serially or with
  `--parallel` in topological order but does not cache. Always use `turbo run test` in CI to
  get caching and proper dependency ordering.

- **c8 vs istanbul provider** — Vitest's `v8` provider instruments at the V8 engine level and
  does not require source maps for Workers code; `istanbul` instruments at the AST level and
  needs source maps. For Cloudflare Workers built with esbuild, `v8` is simpler and more
  accurate.

- **Workspace root test task** — if the monorepo root has no `test` script, `turbo run test`
  still runs correctly; Turborepo skips packages that do not declare the task. Add
  `"test": "echo 'no root tests'"` to the root `package.json` only if a linter requires it.

- **lcov concatenation vs proper merging** — simple concatenation is correct for non-overlapping
  source files across packages. If two packages share source (e.g. a symlinked utility), use
  `lcov --add-tracefile` to merge properly and avoid double-counting.

---

## Verification

```bash
# 1. Confirm each package's coverage directory is present after a cold run.
pnpm turbo run test --cache-dir=.turbo --force
ls packages/*/coverage/lcov.info

# 2. Trigger a cache hit for one package (touch a non-source file, rerun).
touch packages/workers-api/README.md
pnpm turbo run test --cache-dir=.turbo
# workers-api should show "cache hit", coverage/ should still exist.

# 3. Run the aggregate gate.
node scripts/merge-coverage.mjs

# 4. Simulate a threshold failure: temporarily lower a package threshold to 99.
# Edit vitest.config.ts → thresholds.lines: 99, rerun — task should fail.

# 5. Confirm CI workflow: push to a feature branch and inspect the Actions run.
```

---

## Related

- `jest-coverage-thresholds.md`
- `ci-test-parallelization.md`
- `test-coverage-meaningful-metrics.md`
- `vitest-coverage-v8.md`
- `node-test-coverage-threshold-unloaded-files.md`

## Sources

- Turborepo docs — Task outputs and caching: https://turbo.build/repo/docs/crafting-your-repository/caching
- Turborepo docs — Running tasks: https://turbo.build/repo/docs/crafting-your-repository/running-tasks
- Vitest coverage documentation: https://vitest.dev/guide/coverage
- Codecov GitHub Action: https://github.com/codecov/codecov-action
