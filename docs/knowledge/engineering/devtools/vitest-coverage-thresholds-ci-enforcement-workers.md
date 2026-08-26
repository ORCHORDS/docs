# Enforcing Vitest Coverage Thresholds in CI for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Coverage numbers drift downward sprint over sprint because no gate blocks a PR that drops below an agreed baseline. You need CI to fail fast on regressions and upload LCOV reports to Codecov for trend tracking.

## Context

`@cloudflare/vitest-pool-workers` runs tests inside a real Miniflare isolate, which means coverage must be collected by `@vitest/coverage-v8` (V8's built-in coverage), not Istanbul. The Workers pool reports coverage per-isolate and merges it at the Vitest level before threshold evaluation. Thresholds are declared in `vitest.config.ts` so they live in source control and evolve alongside the codebase.

## `vitest.config.ts` — Coverage Configuration

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

// Ratchet baseline — increase by 0.5 after each sprint green build
// Last updated: 2026-08-24 (sprint 42)
const COVERAGE_THRESHOLDS = {
  lines: 80,
  functions: 90,
  branches: 75,
  statements: 80,
} as const;

export default defineWorkersConfig({
  test: {
    pool: '@cloudflare/vitest-pool-workers',
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
        miniflare: {
          kvNamespaces: ['MY_KV'],
          d1Databases: ['DB'],
        },
      },
    },

    coverage: {
      provider: 'v8',             // required for Workers isolate
      enabled: false,              // enable explicitly via --coverage flag
      include: ['src/**/*.ts'],
      exclude: [
        'src/**/*.test.ts',
        'src/**/*.d.ts',
        'src/generated/**',        // skip wrangler-generated types
      ],

      // ── Reporter config ───────────────────────────────────────────────
      reporter: [
        'text',                    // human-readable summary in CI logs
        'json',                    // machine-readable for scripts
        'lcov',                    // LCOV for Codecov upload
        ['html', { subdir: 'html' }],  // local browsing
      ],
      reportsDirectory: './coverage',

      // ── Threshold enforcement (CI fails below these) ───────────────────
      thresholds: {
        ...COVERAGE_THRESHOLDS,
        // Fail loudly with a non-zero exit code when any threshold is breached
        // (Vitest default: process exits 1 automatically)
        autoUpdate: false,         // never silently adjust; update manually
      },
    },
  },
});
```

## GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Test & Coverage

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write   # required for Codecov PR comment

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'pnpm'

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      - name: Run tests with coverage
        run: pnpm vitest run --coverage
        # vitest exits 1 if any threshold is breached — CI fails here

      - name: Upload LCOV to Codecov
        if: always()  # upload even on threshold failure so we can see what dropped
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage/lcov.info
          flags: workers
          fail_ci_if_error: false  # Codecov outages shouldn't block deploys

      - name: Upload coverage HTML artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-html
          path: coverage/html/
          retention-days: 14
```

## The Ratchet Pattern

The ratchet prevents coverage regression while giving teams a predictable improvement cadence.

```typescript
// scripts/ratchet-coverage.ts
// Run after a green sprint build: pnpm tsx scripts/ratchet-coverage.ts
import { readFileSync, writeFileSync } from 'fs';

const CONFIG_PATH = new URL('../vitest.config.ts', import.meta.url).pathname;
const SUMMARY_PATH = './coverage/coverage-summary.json';
const INCREMENT = 0.5;

const summary = JSON.parse(readFileSync(SUMMARY_PATH, 'utf8'));
const actual = summary.total;

const metrics = ['lines', 'functions', 'branches', 'statements'] as const;
let config = readFileSync(CONFIG_PATH, 'utf8');

for (const metric of metrics) {
  const current = actual[metric].pct as number;
  // Only ratchet up — never down
  const newThreshold = Math.min(
    Math.floor((current - INCREMENT) * 2) / 2,  // round to nearest 0.5
    current
  );
  // Replace the number in the config string (safe for our controlled format)
  config = config.replace(
    new RegExp(`(${metric}: )(\\d+(\.\\d+)?)`),
    (_, prefix, old) => {
      const updated = Math.max(Number(old) + INCREMENT, newThreshold);
      return `${prefix}${updated}`;
    }
  );
}

writeFileSync(CONFIG_PATH, config);
console.log('Thresholds ratcheted. Commit vitest.config.ts.');
```

## Interpreting Threshold Failures

```
 ERROR  Coverage for lines (77.3%) does not meet global threshold (80%)
```

1. Check `coverage/html/index.html` locally — identify which files dropped.
2. Was it a new file added without tests, or an existing file that regressed?
3. If intentional (generated code, dead config paths), add the glob to `exclude`.
4. Never lower the threshold — write the missing tests instead.

## Anti-patterns

- **Using Istanbul (`@vitest/coverage-istanbul`) with the Workers pool** — Istanbul instruments source at the JS level and cannot instrument code running inside Miniflare's V8 isolate correctly. Always use `provider: 'v8'`.
- **Setting `autoUpdate: true`** — this silently mutates the config during CI, creating a phantom commit or masking regressions.
- **Thresholding at 100%** — unreachable error branches in Workers (e.g., `env.DB` is always bound) will permanently block CI unless excluded.
- **Uploading coverage only on success** — use `if: always()` so a failing threshold still gives you the report to diagnose.

## Gotchas

- `@cloudflare/vitest-pool-workers` requires Vitest ≥ 2.0 for stable coverage support.
- The `coverage.provider` must be set at the `defineWorkersConfig` level, not inside `poolOptions`.
- Running `vitest` without `--coverage` ignores all threshold config — add a CI lint step that asserts the flag is present.
- Codecov parses `lcov.info`, not `coverage-summary.json` — ensure `'lcov'` is in the reporter array.

## Verification

```bash
# Local threshold check
pnpm vitest run --coverage

# Inspect raw numbers
cat coverage/coverage-summary.json | jq '.total'

# Confirm LCOV was generated
ls -lh coverage/lcov.info
```

## Related

- `eslint-custom-rule-authoring-workers-monorepo.md`
- `miniflare-custom-storage-backend-testing.md`
- [Vitest coverage docs](https://vitest.dev/guide/coverage.html)

## Sources

- `@cloudflare/vitest-pool-workers` — https://www.npmjs.com/package/@cloudflare/vitest-pool-workers
- Vitest coverage thresholds — https://vitest.dev/config/#coverage-thresholds
- Codecov GitHub Action — https://github.com/codecov/codecov-action
