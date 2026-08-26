# Vitest Coverage Threshold Enforcement for Workers CI

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Coverage drops silently on each PR because thresholds are not enforced. You add `--coverage` to your Vitest run but CI still passes even when a new file brings line coverage below 80%. You want per-package thresholds, branch-level gates, and a failing CI step when coverage regresses — all inside a `@cloudflare/vitest-pool-workers` setup.

## Context

Vitest's built-in coverage provider (V8 or Istanbul) supports threshold enforcement via `coverage.thresholds` in `vitest.config.ts`. When a threshold is breached Vitest exits with a non-zero code, failing the CI step. For Cloudflare Workers the test runner uses `@cloudflare/vitest-pool-workers`, which runs tests inside a real Miniflare V8 isolate; coverage collection requires the V8 provider because Istanbul's instrumentation does not survive the isolate boundary.

Workers coverage reports are written to `coverage/` by default. In a pnpm monorepo each package runs its own Vitest instance, so thresholds are configured per-package rather than globally.

---

## Installing Coverage Dependencies

```bash
# Inside the Workers package
pnpm add -D @vitest/coverage-v8
```

V8 coverage is built into Node; no native add-ons required. Istanbul (`@vitest/coverage-istanbul`) does not work with `@cloudflare/vitest-pool-workers` because the isolate strips injected counters.

---

## Configuring Thresholds in vitest.config.ts

```typescript
// apps/worker/vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    globals: true,
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov", "html"],
      reportsDirectory: "./coverage",
      include: ["src/**/*.ts"],
      exclude: ["src/**/*.d.ts", "src/worker-configuration.d.ts"],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 75,
        statements: 80,
      },
    },
  },
});
```

Vitest reads thresholds after coverage collection. If any metric falls below its threshold the process exits with code 1 and prints a summary table showing actual vs required values.

---

## Per-file Thresholds for Critical Paths

```typescript
// apps/worker/vitest.config.ts
export default defineWorkersConfig({
  test: {
    coverage: {
      provider: "v8",
      thresholds: {
        lines: 70,
        // Apply higher bar to auth and routing modules
        "src/auth/**": {
          lines: 95,
          branches: 90,
          functions: 100,
        },
        "src/router.ts": {
          lines: 90,
          branches: 85,
        },
      },
    },
  },
});
```

Per-file globs are evaluated against paths relative to `root`. The global threshold acts as a floor; per-file overrides can only raise it.

---

## GitHub Actions Integration

```yaml
# .github/workflows/ci.yml
jobs:
  test-coverage:
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

      - name: Run Workers tests with coverage
        run: pnpm --filter ./apps/worker vitest run --coverage

      - name: Upload coverage report
        if: always()   # upload even on threshold failure for visibility
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: apps/worker/coverage/

      - name: Post LCOV to Codecov
        if: always()
        uses: codecov/codecov-action@v4
        with:
          files: apps/worker/coverage/lcov.info
          flags: worker
          fail_ci_if_error: false   # coverage gate is Vitest's job, not Codecov's
```

Setting `fail_ci_if_error: false` on Codecov prevents double-failing when Vitest already enforces thresholds. The Vitest step itself exits non-zero on threshold breach.

---

## Excluding Generated and Config Files

```typescript
// apps/worker/vitest.config.ts
export default defineWorkersConfig({
  test: {
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      exclude: [
        "src/**/*.test.ts",
        "src/**/*.spec.ts",
        "src/**/*.d.ts",
        "src/worker-configuration.d.ts",   // wrangler-generated types
        "src/index.ts",                     // thin entry point only
      ],
      thresholds: {
        lines: 80,
        branches: 75,
        functions: 80,
        statements: 80,
      },
    },
  },
});
```

The `wrangler types` output (`worker-configuration.d.ts`) contains only type declarations. Including it in coverage inflates line counts with uncoverable declaration syntax.

---

## Viewing the Threshold Summary Locally

```bash
# Run tests with coverage and show threshold table
pnpm --filter ./apps/worker vitest run --coverage

# Example threshold breach output:
# ERROR: Coverage for lines (72.3%) does not meet global threshold (80%)
#
# File            | Lines | Branches | Funcs | Stmts |
# All files       | 72.3% |   68.1%  | 79.4% | 72.3% |
```

```bash
# Open HTML report
open apps/worker/coverage/index.html
```

---

## Anti-patterns

- **Using Istanbul provider with pool-workers** — Istanbul injects counter increments into source text; the Workers runtime strips or errors on the injected syntax. Always use V8.
- **Setting thresholds to 100% globally from day one** — this forces authors to cover error branches that are genuinely untestable in an isolate (e.g. V8 OOM paths). Ratchet thresholds upward incrementally.
- **Running coverage on every watch-mode save** — coverage collection slows the feedback loop 3-5×. Use `vitest run --coverage` only in CI and in explicit local commands.
- **Committing the `coverage/` directory** — add `**/coverage/` to `.gitignore`; the directory is regenerated on each run and its HTML files are large.

---

## Gotchas

- `@cloudflare/vitest-pool-workers` requires Vitest ≥ 2.0 for V8 coverage support; earlier versions silently produce empty reports.
- V8 coverage counts source positions, not AST nodes, so an uncalled `else` branch in a one-liner ternary may report as covered. Istanbul is more precise but incompatible with the Workers pool.
- The `reportsDirectory` path is relative to the package root, not the repo root. In a monorepo each package writes to its own `coverage/` subdirectory.
- Threshold checks run after all tests complete. If tests themselves fail, Vitest exits before checking thresholds — fix failing tests first.
- When using `--reporter=github-actions` the threshold summary is posted as a GitHub Actions annotation visible inline on the PR.

---

## Verification

```bash
# Confirm V8 provider is active
pnpm --filter ./apps/worker vitest run --coverage --reporter=verbose 2>&1 | grep "coverage provider"
# Expected: "coverage provider: v8"

# Confirm threshold enforcement triggers non-zero exit
pnpm --filter ./apps/worker vitest run --coverage; echo "exit: $?"
# On breach: "exit: 1"

# Check report was written
ls apps/worker/coverage/lcov.info
```

---

## Related

- `vitest-pool-workers-cloudflare-test-api.md` — full Workers test API reference
- `vitest-workers-miniflare-testing-setup.md` — Miniflare isolate configuration
- `code-coverage-tools.md` — language-agnostic coverage tooling overview
- `lefthook-parallel-hooks-workers-ci.md` — running coverage gate in pre-push hooks

---

## Sources

- https://vitest.dev/config/#coverage-thresholds
- https://vitest.dev/guide/coverage.html
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- https://developers.cloudflare.com/workers/testing/vitest-integration/
