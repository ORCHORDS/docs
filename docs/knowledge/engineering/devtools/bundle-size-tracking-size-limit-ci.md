# Bundle Size Tracking with size-limit in CI

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A component library or npm package that started at 8 KB has grown to 120 KB over 18 months. No
single PR looked alarming, but dozens of "small" additions compounded into a size regression that
affects every consumer's bundle. Nobody noticed because there was no automated gate. You need a
way to set a hard size budget and fail PRs that exceed it — ideally with a PR comment showing the
size delta.

## Context

`size-limit` (by Andrey Sitnik / Evil Martians) measures the real-world cost of your JavaScript
by running it through Webpack or esbuild, gzipping the output, and comparing the result against
configured limits. Unlike `bundlesize` (unmaintained) or manual `wc -c` checks, `size-limit` uses
a full bundler pipeline so it accounts for tree-shaking, and it reports the gzip size that
end users actually download.

Key properties:
- Supports esbuild (fast, default for libraries) and Webpack (for apps with complex chunking)
- Measures gzip and brotli sizes
- Produces a PR comment with size delta via `andresz1/size-limit-action` GitHub Action
- Works with any package type: npm libraries, Workers scripts, browser bundles
- Configured in `package.json` or a `.size-limit.json` / `.size-limit.ts` file

## Installation

```bash
# In a library package
pnpm add -D size-limit @size-limit/esbuild

# For apps using Webpack
pnpm add -D size-limit @size-limit/webpack
```

For a Cloudflare Workers script (measures the raw Worker bundle, not gzipped, since Workers has
its own size limits):

```bash
pnpm add -D size-limit @size-limit/esbuild @size-limit/file
```

## Basic Configuration (Library)

Add a `size-limit` array to the library package's `package.json`:

```json
{
  "name": "@repo/ui",
  "size-limit": [
    {
      "name": "Full library (ESM)",
      "path": "dist/index.mjs",
      "limit": "30 kB",
      "gzip": true
    },
    {
      "name": "Button only (tree-shaken)",
      "path": "dist/index.mjs",
      "import": "{ Button }",
      "limit": "5 kB",
      "gzip": true
    }
  ]
}
```

The `import` field tells `size-limit` to bundle only the named export, simulating a tree-shaken
consumer import. This catches re-export of large transitive dependencies.

## Configuration File (Monorepo Root)

In a monorepo, centralise checks in a root `.size-limit.json`:

```json
[
  {
    "name": "UI: full bundle",
    "path": "packages/ui/dist/index.mjs",
    "limit": "30 kB"
  },
  {
    "name": "UI: Button",
    "path": "packages/ui/dist/index.mjs",
    "import": "{ Button }",
    "limit": "4 kB"
  },
  {
    "name": "API client",
    "path": "packages/api-client/dist/index.mjs",
    "import": "{ createClient }",
    "limit": "8 kB"
  },
  {
    "name": "Worker bundle",
    "path": "apps/worker/dist/index.js",
    "limit": "500 kB",
    "gzip": false,
    "brotli": false
  }
]
```

The Worker entry uses `gzip: false` because the Cloudflare Workers compressed size limit
(1 MB uncompressed, 10 MB with assets) is measured differently than browser bundle gzip budgets.

## TypeScript Config

For teams using TypeScript everywhere:

```typescript
// .size-limit.ts
import type { SizeLimitConfig } from 'size-limit';

module.exports = [
  {
    name: 'UI library',
    path: 'packages/ui/dist/index.mjs',
    limit: '30 kB',
    gzip: true,
  },
] satisfies SizeLimitConfig;
```

## Scripts

```json
{
  "scripts": {
    "size": "size-limit",
    "size:why": "size-limit --why"
  }
}
```

`--why` runs Webpack Bundle Analyzer (when using the webpack preset) and opens an interactive
treemap. With the esbuild preset, it prints a module-by-module breakdown to the terminal.

Run locally:

```bash
pnpm build   # build before measuring
pnpm size
```

Example output:

```
  Package              Size    Limit   Status
  UI: full bundle      28 kB   30 kB   ✓
  UI: Button            3.7 kB  4 kB   ✓
  API client            7.9 kB  8 kB   ✓
  Worker bundle       312 kB  500 kB   ✓
```

## GitHub Actions — Check Only (Self-Hosted)

```yaml
# .github/workflows/size.yml
name: Bundle size

on:
  pull_request:
    paths:
      - 'packages/**'
      - 'apps/**'
      - '.size-limit.json'
      - 'pnpm-lock.yaml'

jobs:
  size:
    name: Bundle size check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Build packages
        run: pnpm build

      - name: Check bundle size
        run: pnpm size
```

This job fails when any limit is exceeded, blocking the PR merge.

## GitHub Actions — PR Comment with Delta

Use `andresz1/size-limit-action` to post a comment showing how the PR affects size:

```yaml
# .github/workflows/size-limit.yml
name: Bundle size

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  size:
    runs-on: ubuntu-latest
    env:
      CI_JOB_NUMBER: 1
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - uses: andresz1/size-limit-action@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          build_script: pnpm build
          package_manager: pnpm
```

The action checks out both the PR branch and `main`, builds both, runs `size-limit` on each,
and posts a PR comment like:

```
| Package         | Size    | Change    |
|-----------------|---------|-----------|
| UI: full bundle | 29.1 kB | +1.1 kB ↑ |
| UI: Button      |  3.7 kB |  0 B      |
```

A red ✗ appears if the limit is breached; the job also exits with a non-zero status code.

## Integrating with Turborepo

Add a `size` task in `turbo.json`:

```json
{
  "tasks": {
    "size": {
      "dependsOn": ["build"],
      "cache": false
    }
  }
}
```

Run from the root:

```bash
pnpm turbo size
```

Turborepo runs `build` first (from cache if unchanged) then `size` in each package.

## Tracking Trends Over Time

`size-limit` by itself measures a single commit. For trend tracking:

- **Statosaurus / Codechecks** — historical size dashboards (third-party SaaS)
- **Custom solution**: store JSON output in a branch or GitHub release asset

```bash
# Store size report as JSON
pnpm size --json > size-report.json

# Upload as a GitHub Actions artifact
- uses: actions/upload-artifact@v4
  with:
    name: size-report
    path: size-report.json
```

Parse the JSON in a separate job to compare against the baseline stored on the `main` branch.

## Anti-patterns

**Measuring minified size without gzip** — raw minified bytes do not reflect download cost.
Always use `gzip: true` (the default) for browser bundles. The gzip size is what users download.

**Setting limits too loosely** — a limit of `"500 kB"` for a utility library defeats the purpose.
Set the limit at 110–120% of the current size, then tighten it after deliberate reductions.

**Not building before measuring** — `size-limit` measures what's on disk. Running it before
`build` measures stale artefacts. Wire `build` as a dependency in the CI step or Turborepo task.

**Ignoring the `import` field for libraries** — measuring the full bundle entry is useful but
does not catch unexpectedly large individual exports. Add named-import checks for core exports.

**Patching size-limit output in CI** — some teams add `|| true` to the size-limit command to
prevent CI failures. This defeats the entire purpose of setting limits.

## Gotchas

- `size-limit` with the esbuild preset does not produce a `--why` treemap; install `@size-limit/webpack`
  and run with that preset locally to get the module breakdown when debugging a regression.
- Size checks require a completed build. In monorepos where packages depend on each other, run
  the full `build` pipeline (not just the root package build) before `size-limit`.
- The `andresz1/size-limit-action` requires `GITHUB_TOKEN` permissions `pull-requests: write`
  and `contents: read`. Add these to the workflow permissions block in restricted repos.
- On first run against a package with no prior size data, the action posts "N/A" for the delta
  rather than absolute numbers. The baseline is established from the `main` branch.

## Verification

```bash
# Build the project
pnpm build

# Run size-limit
pnpm size

# Run with breakdown (requires @size-limit/webpack or prints esbuild breakdown)
pnpm size --why

# Intentionally breach a limit to confirm CI failure
# Temporarily change a limit to 1 B and verify the exit code is non-zero
pnpm size; echo "Exit: $?"
```

## Related

- `turborepo-cloudflare-workers-pipeline.md` — wiring size checks into Turborepo pipelines
- `lighthouse-ci-performance-budget-github-actions.md` — performance budgets for browser apps
- `node-cpu-flame-graph-profiling.md` — profiling runtime cost (complementary to bundle size)
- `production-source-maps-strategy.md` — understanding what's in the bundle via source maps

## Sources

- `size-limit` GitHub repository: github.com/ai/size-limit
- `andresz1/size-limit-action` README (2024)
- Evil Martians blog: "Shrinking the bundle" (2023)
- Cloudflare Workers: "Worker size limits" documentation
