# GitHub Actions Test Sharding with Vitest for Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Cloudflare Workers monorepo with hundreds of unit and integration tests runs all tests
sequentially in a single CI job, taking 12+ minutes per pull request. Developers wait too
long for a green check before merging. Vitest's built-in shard flag combined with a GitHub
Actions matrix strategy distributes tests across parallel jobs, reducing wall-clock time
proportionally to the number of shards.

## Context

Vitest (≥ 1.0) supports a `--shard` flag in the form `--shard=<index>/<total>` that splits
the test suite into equal buckets by file. Each shard runs independently and reports its own
results. In a GitHub Actions matrix this means N jobs run in parallel, each responsible for
1/N of the test files. Workers tests that use `@cloudflare/vitest-pool-workers` run inside
the workerd runtime via the Vitest pool plugin, which is compatible with sharding as long as
the pool initialisation is deterministic. The matrix job strategy also requires a merge job
that waits on all shards before reporting overall status to branch protection required checks.

## Setting Up the Shard Matrix

Define the total shard count as a matrix variable so it is easy to tune without editing
multiple `--shard` arguments. The `shard` matrix value carries the 1-based index.

```yaml
# .github/workflows/test.yml
name: Test

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    name: Test shard ${{ matrix.shard }}/${{ matrix.total }}
    runs-on: ubuntu-24.04
    permissions:
      contents: read

    strategy:
      fail-fast: false
      matrix:
        shard: [1, 2, 3, 4]
        total: [4]

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Run Vitest shard
        run: >-
          pnpm vitest run
          --reporter=verbose
          --reporter=json
          --outputFile=test-results-${{ matrix.shard }}.json
          --shard=${{ matrix.shard }}/${{ matrix.total }}
        env:
          VITEST_POOL_WORKERS_FORCE_BUNDLING: "1"

      - name: Upload shard results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results-${{ matrix.shard }}
          path: test-results-${{ matrix.shard }}.json
          retention-days: 3

  # Required status check target for branch protection
  all-tests-pass:
    name: All tests pass
    runs-on: ubuntu-24.04
    needs: test
    if: always()
    steps:
      - name: Fail if any shard failed
        run: |
          if [[ "${{ needs.test.result }}" != "success" ]]; then
            echo "One or more test shards failed."
            exit 1
          fi
          echo "All shards passed."
```

## Vitest Pool Workers Configuration

Configure the workerd pool in `vitest.config.ts`. The pool workers plugin must be installed
(`@cloudflare/vitest-pool-workers`) and the worker entry point must be resolvable from each
shard since shards operate on the same config.

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    // Pool workers automatically uses workerd for isolation
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          // Ensure deterministic initialisation across shards
          compatibilityDate: "2025-01-01",
        },
      },
    },
    // Reporter JSON output is set via CLI --outputFile; keep this minimal
    reporters: process.env.CI ? ["verbose"] : ["default"],
    // Sharding works on the file list; ensure coverage is per-shard
    coverage: {
      enabled: false, // Merge coverage separately after all shards
      provider: "istanbul",
    },
  },
});
```

## Merging Coverage Reports After Sharding

When coverage is required, each shard must emit a partial coverage JSON and a post-shard
merge job combines them with `nyc merge` or `vitest --coverage.mergeReports`.

```yaml
  merge-coverage:
    name: Merge coverage
    runs-on: ubuntu-24.04
    needs: test
    if: always() && needs.test.result == 'success'
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile

      - name: Download all shard results
        uses: actions/download-artifact@v4
        with:
          pattern: test-results-*
          merge-multiple: true
          path: shard-results/

      - name: Merge and report coverage
        run: pnpm vitest --coverage --coverage.mergeReports=shard-results/
```

## Anti-patterns

- Registering each shard job as a separate required status check — branch protection rules
  would need updating every time the shard count changes; use the `all-tests-pass` merge job
  as the single required check instead.
- Setting `fail-fast: true` in the matrix — a single flaky test cancels all parallel shards,
  losing the results from passing shards and making failure diagnosis harder.
- Running shards without `--reporter=json --outputFile` — shard results are lost when the job
  container exits and cannot be aggregated or uploaded as artifacts.

## Gotchas

- The shard index is 1-based in Vitest (`--shard=1/4`), not 0-based; off-by-one errors cause
  one shard to receive all tests and others to receive zero.
- `@cloudflare/vitest-pool-workers` spins up a miniflare instance per worker isolation group;
  with 4 shards on a 2-core runner the CPU contention can make sharding slower, not faster —
  use `ubuntu-24.04-4core` or larger runners for parallelism gains.
- Sharding by file is not the same as sharding by test count; if one file has 80% of the
  tests the last shard may still be much slower than others.

## Verification

```bash
# Run a local shard to verify the configuration
pnpm vitest run --shard=1/4 --reporter=verbose

# Confirm all 4 shards together cover 100% of test files
for i in 1 2 3 4; do
  pnpm vitest run --shard=$i/4 --reporter=json --outputFile=results-$i.json 2>/dev/null
  jq '.testResults | length' results-$i.json
done

# Total files should equal running with no shard flag
pnpm vitest run --reporter=json --outputFile=results-all.json 2>/dev/null
jq '.testResults | length' results-all.json
```

## Related

- `github/github-required-status-checks.md`
- `github/github-actions-matrix-strategy-workers.md`
- `github/github-actions-dynamic-matrix-and-fail-fast.md`

## Sources

- https://vitest.dev/guide/cli.html#shard
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/using-a-matrix-for-your-jobs
