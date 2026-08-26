# Mutation Testing with Stryker for Workers TypeScript

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project unit tests report 90%+ line coverage but still miss logic bugs — off-by-one errors in pagination, inverted null checks in auth middleware, and dropped `await` in D1 queries all pass a green coverage report. Coverage measures execution, not assertion quality.

## Context

Stryker Mutator injects deliberate faults (mutants) into the Workers TypeScript source and checks whether the test suite kills each one. A mutant that survives means a test gap. Stryker integrates with the `vitest` runner example project already uses, so no second test command is needed. A mutation score threshold in CI gates merges when quality drops below the team standard.

Version: `@stryker-mutator/core` 8.x, `@stryker-mutator/vitest-runner` 8.x, TypeScript 5.x, Workers source compiled to ESM.

## Installation

```bash
npm install --save-dev \
  @stryker-mutator/core \
  @stryker-mutator/vitest-runner \
  @stryker-mutator/typescript-checker
```

## Stryker Configuration

```javascript
// stryker.config.mjs
/** @type {import('@stryker-mutator/api/core').PartialStrykerOptions} */
export default {
  packageManager: "npm",
  reporters: ["html", "clear-text", "progress", "json"],
  testRunner: "vitest",
  vitest: {
    configFile: "vitest.config.ts",
  },
  checkers: ["typescript"],
  tsconfigFile: "tsconfig.json",
  mutate: [
    "src/handlers/**/*.ts",
    "src/middleware/**/*.ts",
    "src/db/**/*.ts",
    "!src/**/*.test.ts",
    "!src/**/__tests__/**",
  ],
  thresholds: {
    high:   80,
    low:    70,
    break:  65,   // CI fails below this score
  },
  timeoutMS:           10000,
  timeoutFactor:       2.5,
  concurrency:         4,
  coverageAnalysis:    "perTest",
  htmlReporter: {
    fileName: "reports/mutation/index.html",
  },
};
```

| Field              | Recommended Value        | Reason                                              |
|--------------------|--------------------------|-----------------------------------------------------|
| `break`            | 65                       | Gate that fails the CI pipeline                     |
| `coverageAnalysis` | `"perTest"`              | Only runs mutants against tests that cover the file |
| `concurrency`      | 4                        | Balance between speed and Miniflare memory          |
| `timeoutFactor`    | 2.5                      | Workers handlers can be slow under Miniflare        |
| `mutate`           | handlers + db only       | Skip generated types and config files               |

## Vitest Runner Integration

Stryker drives vitest directly — no separate runner script needed:

```typescript
// vitest.config.ts (already existing in example project)
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "miniflare",
    environmentOptions: {
      modules: true,
      d1Databases: ["DB"],
    },
    include: ["src/**/*.test.ts", "tests/unit/**/*.test.ts"],
    // Stryker injects its own timeout wrapper; keep vitest timeout loose
    testTimeout: 30_000,
  },
});
```

Run Stryker:

```bash
npx stryker run
# or with explicit config
npx stryker run --config stryker.config.mjs
```

## Mutation Score Threshold Gate in CI

```yaml
# .github/workflows/mutation.yml
name: Mutation Testing

on:
  pull_request:
    paths:
      - "src/handlers/**"
      - "src/middleware/**"
      - "src/db/**"

jobs:
  mutation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci
      - run: npx stryker run
        # Stryker exits non-zero when score < break threshold
      - name: Upload mutation report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: mutation-report
          path: reports/mutation/
```

Stryker exits with code `1` when the mutation score falls below `thresholds.break`. GitHub Actions marks the job failed and blocks the merge.

## Reading Mutation Results

```
Mutation score: 74.32%

Killed:    312
Survived:   87
Timed out:   6
No coverage: 14

---------------------------------
File: src/handlers/tracks.ts
  Survived mutants:
    [line 42] BooleanLiteral: `!isAuthenticated` => `isAuthenticated`
    [line 87] ConditionalExpression: `page > 0` => `page >= 0`
    [line 91] ArithmeticOperator: `offset = (page - 1) * size` => `offset = (page + 1) * size`
```

| Mutant status  | Meaning                                    | Action                           |
|----------------|--------------------------------------------|----------------------------------|
| Killed         | Test caught the fault — good               | None                             |
| Survived       | No test asserts on this branch             | Write a targeted assertion       |
| Timed out      | Worker hung on mutant — likely infinite loop | Inspect mutant, adjust timeout |
| No coverage    | No test even executes this line            | Add unit test or remove dead code|

## Targeting Surviving Mutants

When `BooleanLiteral` mutant survives on `!isAuthenticated`:

```typescript
// Original (src/middleware/auth.ts line 42)
if (!isAuthenticated(request)) {
  return new Response("Unauthorized", { status: 401 });
}
```

Add an explicit test for the authenticated = false branch:

```typescript
it("returns 401 when request has no auth token", async () => {
  const req = new Request("https://api.example.com/api/tracks");
  const res = await authMiddleware(req, mockEnv());
  expect(res.status).toBe(401);
});

it("calls next() when request has valid auth token", async () => {
  const req = new Request("https://api.example.com/api/tracks", {
    headers: { Authorization: "Bearer valid-token" },
  });
  const next = vi.fn().mockResolvedValue(new Response("OK"));
  await authMiddleware(req, mockEnv(), next);
  expect(next).toHaveBeenCalledOnce();
});
```

## Anti-patterns

- Running Stryker against the entire `src/` tree including generated D1 types — inflates mutant count with unkillable generated code.
- Setting `break: 0` to prevent CI failures — renders the gate meaningless; start at 50 and ratchet up.
- Using `coverageAnalysis: "all"` on a large Workers codebase — runs every mutant against every test, makes CI 10x slower.
- Treating timed-out mutants as killed — Stryker does not count them in the score; investigate whether the Worker hangs on boundary values.
- Adding `// Stryker disable` comments liberally — valid only for truly non-testable generated code, not hard-to-test logic.

## Gotchas

- Stryker's TypeScript checker validates mutants before running tests; a mutant that produces a type error is labelled `CompileError` and excluded from the score — check `--logLevel=debug` output if score seems unusually high.
- Miniflare starts a fresh Workers runtime per test file under Stryker's `perTest` coverage mode; memory usage spikes with many files — cap `concurrency` at 4.
- Workers global `Request`/`Response` must be available in the vitest environment; `environment: "miniflare"` handles this via `@miniflare/jest-environment-miniflare` or the vitest miniflare integration.
- Stryker 8.x requires ESM config (`stryker.config.mjs`) when the Workers project uses `"type": "module"` in `package.json`.
- Mutation report HTML is generated relative to the CWD; set `htmlReporter.fileName` explicitly to avoid it landing inside `src/`.

## Verification

```bash
# Dry run to see mutant count without running tests
npx stryker run --dryRun

# Run only against one handler to iterate quickly
npx stryker run --mutate "src/handlers/tracks.ts"

# Check threshold exit code
npx stryker run; echo "Exit: $?"
# Exit: 0 => above break threshold
# Exit: 1 => below break threshold (CI will fail)

# View HTML report
open reports/mutation/index.html
```

## Related

- `mutation-testing-stryker.md`
- `mutation-testing-surviving-mutants-and-threshold-governance.md`
- `stryker-mutation-testing-javascript.md`
- `vitest-setup.md`
- `workers-test-patterns.md`
- `jest-coverage-thresholds.md`

## Sources

- https://stryker-mutator.io/docs/stryker-js/vitest-runner/
- https://stryker-mutator.io/docs/stryker-js/configuration/
- https://stryker-mutator.io/docs/stryker-js/typescript-checker/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
