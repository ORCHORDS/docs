# c8/v8 Coverage Reporting for Workers Unit Tests

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You have a Cloudflare Workers project with a Vitest test suite and want to generate code
coverage reports that your CI pipeline can enforce with thresholds, publish as HTML, and
diff against a baseline. Istanbul (the default Vitest provider) instruments source files
via AST transformation, but it does not work cleanly when the test environment is the
Workers runtime (V8 isolates) because the Workers pool bypasses Node's module system.

Switching to the V8 native coverage provider (`provider: "v8"`) solves this because V8
emits raw coverage data directly from the engine that runs your Worker code, with no AST
instrumentation required. This produces accurate branch and statement coverage even for
dynamic module patterns common in Workers (conditional exports, `env`-based routing).

## Context

Vitest ships two coverage providers: `istanbul` and `v8`. The `v8` provider uses
`NODE_V8_COVERAGE` or the V8 inspector protocol to collect coverage at the engine level,
then post-processes it with the `c8` library (`c8` was historically a separate CLI; in
Vitest 1.x+ it is integrated directly).

The `@cloudflare/vitest-pool-workers` package runs tests inside a real `workerd` V8
isolate. Coverage data from this pool must be extracted from the isolate's coverage API
rather than from Node's runtime. As of `@cloudflare/vitest-pool-workers` v0.5+, the
package exposes coverage support when Vitest's `provider` is set to `v8`.

Coverage reports are emitted as LCOV, JSON, HTML, and text formats, compatible with
`codecov`, `coveralls`, and GitHub Actions summary annotations.

## Vitest Configuration for v8 Coverage

```typescript
// vitest.config.ts (Workers project)
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    globals: true,
    // Point to the pool workers provider
    pool: "@cloudflare/vitest-pool-workers",
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          compatibilityDate: "2025-01-01",
          compatibilityFlags: ["nodejs_compat"],
        },
      },
    },
    // Coverage configuration
    coverage: {
      provider: "v8",           // <-- native V8 coverage, not Istanbul
      enabled: false,           // enable via --coverage CLI flag
      include: ["src/**/*.ts"],
      exclude: [
        "src/**/*.test.ts",
        "src/**/*.spec.ts",
        "src/types/**",
        "src/generated/**",
      ],
      reportsDirectory: "./coverage",
      reporter: ["text", "lcov", "html", "json-summary"],
      // Thresholds — CI fails if coverage drops below these
      thresholds: {
        statements: 80,
        branches: 75,
        functions: 85,
        lines: 80,
      },
      // Clean stale coverage between runs
      clean: true,
      cleanOnRerun: true,
      // Ignore patterns inside source files
      ignoreEmptyLines: true,
      skipFull: false,
    },
  },
});
```

Run with:

```bash
# Generate coverage report
pnpm vitest run --coverage

# Watch mode with coverage (slower but useful during TDD)
pnpm vitest --coverage

# Coverage for a specific file pattern
pnpm vitest run --coverage --reporter=verbose src/handlers/
```

## Reading the Coverage Output

The `text` reporter prints a summary table to stdout. The `html` reporter writes an
interactive HTML report to `coverage/index.html`. The `lcov` reporter writes
`coverage/lcov.info` for CI upload tools.

```
----------------------------|---------|----------|---------|---------|
File                        | % Stmts | % Branch | % Funcs | % Lines |
----------------------------|---------|----------|---------|---------|
All files                   |   82.14 |    76.92 |   90.00 |   82.14 |
 src/                       |         |          |         |         |
  index.ts                  |   91.67 |    87.50 |  100.00 |   91.67 |
  router.ts                 |   78.95 |    71.43 |   85.71 |   78.95 |
 src/handlers/              |         |          |         |         |
  payments.ts               |   80.00 |    66.67 |   88.89 |   80.00 |
  webhooks.ts               |   72.73 |    60.00 |   80.00 |   72.73 |
----------------------------|---------|----------|---------|---------|
```

Uncovered lines are flagged in the HTML report and in the `json-summary` output:

```json
// coverage/coverage-summary.json
{
  "total": {
    "statements": { "total": 112, "covered": 92, "skipped": 0, "pct": 82.14 },
    "branches":   { "total": 26,  "covered": 20, "skipped": 0, "pct": 76.92 },
    "functions":  { "total": 20,  "covered": 18, "skipped": 0, "pct": 90.0  },
    "lines":      { "total": 112, "covered": 92, "skipped": 0, "pct": 82.14 }
  }
}
```

## Source Map Integration

The Workers bundle is compiled from TypeScript before the isolate runs it. Without source
maps, V8 coverage maps to the compiled JS, not the original TypeScript. Enable source maps
in the test environment:

```toml
# wrangler.toml
[build]
command = "tsc"  # or esbuild, etc.

# Enable source maps for Workers builds (dev/test only)
[env.test]
[env.test.build]
# Wrangler passes --source-map to esbuild when this is set
```

```typescript
// vitest.config.ts additions
export default defineWorkersConfig({
  test: {
    coverage: {
      provider: "v8",
      // Tell c8 to remap V8 coverage back through source maps
      // (Vitest handles this automatically when sourcemap: true in esbuild)
      all: true,   // include files with zero coverage in the report
    },
  },
  // Enable source maps in the test build
  esbuild: {
    sourcemap: "inline",
  },
});
```

Without inline source maps, branch coverage in particular will report lower than actual
because the compiled JS may merge branches that TypeScript expanded.

## CI Pipeline Integration

```yaml
# .github/workflows/test.yml
name: Test and Coverage

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v3
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Run tests with coverage
        run: pnpm vitest run --coverage
        env:
          # Vitest pool workers may need access to wrangler state
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage/lcov.info
          flags: workers-unit
          fail_ci_if_error: true
        env:
          CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}

      - name: Post coverage summary to GitHub Step Summary
        run: |
          echo "## Coverage Summary" >> $GITHUB_STEP_SUMMARY
          cat coverage/coverage-summary.json \
            | node -e "
              const s=require('fs').readFileSync('/dev/stdin','utf8');
              const j=JSON.parse(s).total;
              console.log('| Metric | % |');
              console.log('|--------|---|');
              for(const k of ['statements','branches','functions','lines'])
                console.log(\`| \${k} | \${j[k].pct} |\`);
            " >> $GITHUB_STEP_SUMMARY
```

## Coverage Boundary: What v8 Coverage Does Not Cover

V8 native coverage has some limitations in the Workers context:

| Scenario | Coverage Support |
|---|---|
| Regular Worker handler code | Full statement, branch, function |
| Durable Object methods | Full (DO class runs in same isolate) |
| Queue consumer handlers | Full |
| Scheduled cron handlers | Full |
| Cloudflare binding side effects (D1 query) | Not tracked (native code) |
| Module worker `init` code (top-level await) | Partial — depends on isolate lifecycle |
| `wrangler.toml`-defined middleware (beta) | Not tracked |

Code inside `try/catch` blocks that only execute on real Cloudflare errors (rate limits,
binding failures) cannot be covered by unit tests backed by Miniflare stubs — mark these
with `/* c8 ignore next */` comments to avoid false coverage drops.

```typescript
// src/handlers/d1.ts
export async function queryUsers(env: Env): Promise<User[]> {
  try {
    const result = await env.DB.prepare("SELECT * FROM users").all<User>();
    return result.results;
  } catch (err) {
    /* c8 ignore next 3 */
    console.error("D1 query failed", err);
    return [];
  }
}
```

## Anti-patterns

- Using `provider: "istanbul"` with `@cloudflare/vitest-pool-workers` — Istanbul requires
  AST instrumentation that conflicts with the Workers module bundling; use `v8` instead.
- Setting thresholds to 100 % across all metrics — unreachable error-handling branches
  will permanently block CI; use per-file overrides for error-path-heavy files.
- Running `pnpm vitest --coverage` in watch mode during CI — watch mode never exits;
  always use `vitest run --coverage` in CI.
- Omitting `clean: true` — stale `.v8-coverage/` files from previous runs can pollute
  the report, making coverage appear artificially high.
- Including generated files (e.g. `src/generated/` from `wrangler types`) in coverage
  include globs — these inflate total file counts and skew percentages.

## Gotchas

- `@cloudflare/vitest-pool-workers` must be at v0.5.0 or later for V8 coverage support.
  Earlier versions silently fall back to no coverage. Check `package.json`.
- The `all: true` coverage option includes source files that are never imported by any
  test. This is correct for measuring true coverage but may surface files you forgot to
  test at all.
- On monorepos, run coverage per-package (`vitest run --coverage` inside each package)
  rather than from the root — the root `coverage/` directory will merge all packages'
  reports into one, which obscures per-package thresholds.
- Inline source maps (`sourcemap: "inline"`) increase bundle size during test runs. Do not
  enable them for production builds; scope them to `NODE_ENV === "test"` or the Vitest
  config only.

## Verification

```bash
# 1. Run coverage for the first time
pnpm vitest run --coverage --reporter=verbose

# 2. Confirm report files exist
ls coverage/
# Expected: index.html  lcov.info  coverage-summary.json  ...

# 3. Confirm lcov.info references TypeScript source paths (not compiled JS)
head -5 coverage/lcov.info
# Expected: SF:src/index.ts  (not SF:dist/index.js)

# 4. Deliberately break a threshold and confirm CI fails
# Edit vitest.config.ts: set thresholds.statements to 99
pnpm vitest run --coverage
# Expected: exit code 1, "Coverage threshold not met" error
```

## Related

- `vitest-coverage-threshold-workers-ci.md` — per-package threshold configuration
- `vitest-pool-workers-cloudflare-test-api.md` — Workers pool setup
- `vitest-workers-miniflare-testing-setup.md` — Miniflare integration
- `code-coverage-tools.md` — general coverage tooling overview

## Sources

- Vitest Docs: "Coverage" — https://vitest.dev/guide/coverage
- c8 (V8 coverage) GitHub: https://github.com/bcoe/c8
- Cloudflare Docs: "@cloudflare/vitest-pool-workers" — https://developers.cloudflare.com/workers/testing/vitest-integration/
