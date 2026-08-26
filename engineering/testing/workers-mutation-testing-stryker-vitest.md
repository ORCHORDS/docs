# Mutation Testing with Stryker + Vitest for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Vitest suite reports 90%+ line coverage, yet bugs slip into production. Coverage metrics tell you which lines ran—not whether the tests actually *verify* the behaviour. Mutation testing kills that false confidence by injecting tiny defects (mutants) and checking that at least one test fails for each. If all tests pass with a mutant alive, your suite has a gap.

## Context

Stryker Mutator 8+ ships `@stryker-mutator/vitest-runner`, which integrates directly with Vitest's worker pool. For Cloudflare Workers projects built with `wrangler` and `@cloudflare/vitest-pool-workers`, Stryker runs inside the same Miniflare environment, so D1, KV, and R2 bindings behave identically during mutation runs.

---

## Section 1 — Installation and baseline config

```bash
npm install --save-dev @stryker-mutator/core @stryker-mutator/vitest-runner
```

```ts
// stryker.config.ts
import type { Config } from '@stryker-mutator/core';

const config: Config = {
  testRunner: 'vitest',
  testRunnerNodeArgs: ['--experimental-vm-modules'],
  vitest: {
    // Forward your existing vitest config so the pool-workers environment loads
    configFile: 'vitest.config.ts',
  },
  // Mutate only source files, never test files or generated code
  mutate: [
    'src/**/*.ts',
    '!src/**/*.test.ts',
    '!src/**/*.spec.ts',
    '!src/generated/**',
  ],
  // Stryker's recommended mutator set for TypeScript
  mutator: {
    plugins: [],
    excludedMutations: [
      // Optional arithmetic mutants in logging paths add noise
      'StringLiteral',
    ],
  },
  reporters: ['html', 'json', 'progress'],
  htmlReporter: { fileName: 'reports/mutation/index.html' },
  jsonReporter: { fileName: 'reports/mutation/report.json' },
  // Baseline: enforce 80% mutation score on CI
  thresholds: { high: 90, low: 80, break: 80 },
  // Speed: only re-run the subset of tests that cover changed source lines
  coverageAnalysis: 'perTest',
  // Bail after 5 000 ms per mutant run (Workers boot fast)
  timeoutFactor: 1.5,
  timeoutMS: 5000,
  // Limit concurrency to avoid port conflicts in wrangler's dev server
  concurrency: 4,
  tempDirName: '.stryker-tmp',
};

export default config;
```

## Section 2 — Running a baseline score

```bash
# Dry run: list mutants without running tests
npx stryker run --dryRun

# Full run: produces reports/mutation/index.html
npx stryker run
```

Stryker prints a summary table. Aim for **>= 80 % mutation score** before enabling the CI threshold.

```
All files  |  89.23 |  78.40 |  90.11 |  88.60 |
           | % Score| % Killed| % Survived| % Timeout|
```

## Section 3 — Identifying under-tested branches

Open `reports/mutation/index.html`. Filter by **"Survived"** to find mutants your tests didn't kill. Common patterns in Workers code:

```ts
// workers/src/auth.ts  — typical survived mutant
export function requireAuth(request: Request): boolean {
  const token = request.headers.get('Authorization');
  // Stryker inserts: if (token !== null) — tests passed! Gap found.
  if (token === null) return false;
  return validateJwt(token);
}
```

The missing test:

```ts
// workers/src/auth.test.ts
import { describe, it, expect } from 'vitest';
import { requireAuth } from './auth';

describe('requireAuth', () => {
  it('returns false when Authorization header is absent', () => {
    const req = new Request('https://example.com');
    expect(requireAuth(req)).toBe(false);
  });

  it('returns false when Authorization header is empty string', () => {
    const req = new Request('https://example.com', {
      headers: { Authorization: '' },
    });
    // This is the branch that was missing
    expect(requireAuth(req)).toBe(false);
  });

  it('returns true for a valid token', () => {
    const req = new Request('https://example.com', {
      headers: { Authorization: 'Bearer valid-token' },
    });
    expect(requireAuth(req)).toBe(true);
  });
});
```

## Section 4 — CI threshold enforcement

```yaml
# .github/workflows/mutation.yml
name: Mutation Testing

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  mutation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
      - run: npm ci
      - name: Run Stryker
        run: npx stryker run
        # stryker exits non-zero when score < thresholds.break
      - name: Upload HTML report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: mutation-report
          path: reports/mutation/
          retention-days: 14
```

The `thresholds.break: 80` in `stryker.config.ts` causes `npx stryker run` to exit with code 1 when the mutation score drops below 80 %, blocking the PR merge.

## Anti-patterns

- **Excluding entire directories** (`mutate: ['!src/routes/**']`) to hit the threshold artificially. Fix gaps instead.
- **Setting `coverageAnalysis: 'off'`** — makes runs 10-20× slower; always use `perTest` with Vitest.
- **Ignoring timeout mutants** — in Workers code `await` chains, a timeout mutant often indicates a real missing assertion on async branches.
- **Running Stryker on every commit** — mutation testing is slow. Run it nightly or on PR labels (`mutation:run`).

## Gotchas

- Stryker creates many temporary `wrangler.toml` copies in `.stryker-tmp/`. Add it to `.gitignore`.
- `@cloudflare/vitest-pool-workers` requires `node >= 18.14`. Pin the CI `node-version` accordingly.
- KV and D1 bindings bound via `miniflare` in `vitest.config.ts` are inherited by each Stryker worker; no extra setup needed.
- Mutation runs can take 10–30 minutes on large codebases. Cache `.stryker-tmp/` between CI runs using `actions/cache` keyed on the source file hash.

## Verification

```bash
# Confirm exit code = 0 when score >= threshold
npx stryker run; echo "Exit: $?"

# Confirm exit code = 1 when score < threshold (simulate by lowering threshold)
STRYKER_THRESHOLD_BREAK=99 npx stryker run; echo "Exit: $?"
```

## Related

- `documentation/categories/testing/workers-vitest-pool-workers-setup.md`
- `documentation/categories/testing/workers-coverage-c8-thresholds.md`
- `documentation/ci/workers-github-actions-matrix.md`

## Sources

- https://stryker-mutator.io/docs/stryker-js/vitest-runner/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://stryker-mutator.io/docs/mutation-testing-elements/mutant-states-and-metrics/
