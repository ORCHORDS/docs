# stryker-mutation-testing-javascript

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

The project reports 90 % line coverage yet a critical
boundary-condition bug reaches production. Reviewers ask
"why didn't a test catch this?" — the covered line was
executed but the assertion never exercised the failing case.

## Context

Mutation testing answers whether tests actually detect
broken code. Stryker injects small code changes (mutants)
one at a time, re-runs the test suite after each, and
reports whether any test failed (mutant killed) or all
tests passed (mutant survived). A high mutation score
proves tests assert behaviour, not just execution. Code
coverage only proves a line ran.

## How Mutation Testing Works

```
Source code → Mutant generator → mutated copy
                                        ↓
                                 Run test suite
                                        ↓
                         All pass?   Some fail?
                             ↓            ↓
                         SURVIVED     KILLED
```

The mutation score is:

```
score = killed / (killed + survived + timeout) × 100
```

A score of 70–80 % is a reasonable initial target for
business-critical modules; 100 % is rarely cost-effective.

## Common Mutators

| Category    | Original      | Mutant           |
|-------------|---------------|------------------|
| Arithmetic  | `a + b`       | `a - b`          |
| Conditional | `x > y`       | `x >= y`         |
| Conditional | `a && b`      | `a \|\| b`        |
| String      | `'hello'`     | `''`             |
| Boolean     | `return true` | `return false`   |
| Array       | `[...arr]`    | `[]`             |

## Configuration for Vitest and Jest

Install the runner plugin for your test framework:

```bash
# For Vitest
npm install -D @stryker-mutator/core \
               @stryker-mutator/vitest-runner

# For Jest
npm install -D @stryker-mutator/core \
               @stryker-mutator/jest-runner
```

`stryker.config.mjs`:

```js
// @ts-check
/** @type {import('@stryker-mutator/api/core').PartialStrykerOptions} */
export default {
  testRunner: 'vitest',        // or 'jest'
  reporters: ['html', 'clear-text', 'progress', 'json'],
  coverageAnalysis: 'perTest', // needs Istanbul coverage
  mutate: [
    'src/**/*.ts',
    '!src/**/*.test.ts',
    '!src/**/*.spec.ts',
  ],
  thresholds: {
    high:  80,  // green badge
    low:   60,  // yellow badge
    break: 50,  // exit code 1 — fails CI
  },
  ignorePatterns: ['node_modules', 'dist'],
  incremental: true,           // cache state between runs
};
```

Run:

```bash
npx stryker run

# Incremental — only re-test mutations on changed files
npx stryker run --incremental
```

The HTML report opens at `reports/mutation/html/index.html`
and shows each surviving mutant with its source location.

## Interpreting Results

Stryker classifies each mutant:

| Status    | Meaning                                    |
|-----------|--------------------------------------------|
| Killed    | At least one test caught it — good         |
| Survived  | No test detected the change — gap found    |
| No coverage | No test touches the line — ignored line  |
| Timeout   | Mutant caused an infinite loop             |
| Ignored   | Excluded by `mutatorExclude` config        |

Focus first on survived mutants inside `src/core/` or any
module with explicit business rules. Survived mutants in
logging or serialisation utilities are lower priority.

## Which Mutations to Ignore

Ignoring a mutant class is appropriate when:

- String mutants in user-facing copy (translations handle
  the real values; empty-string swaps are noise).
- Array literal mutants in configuration constants that
  tests never exercise through behaviour.
- Arithmetic mutants inside pure formatting functions
  (e.g. padding numbers to a fixed width) where the
  output is never asserted.

Suppress individual lines with the inline directive
`// Stryker disable next-line: ArithmeticOperator`, or
exclude a whole class via `mutatorExcludes` in config.

## Anti-patterns

- Running Stryker over the entire monorepo on every PR —
  full runs take 10–30 min; scope to changed modules with
  `--mutate` or incremental mode.
- Treating 100 % mutation score as mandatory — trivial
  getters and log lines cost more to kill than the bug
  risk they represent.
- Ignoring timeouts without investigating — a timeout
  often indicates an accidentally created infinite loop
  in production code, not just a slow test.
- Adding tests that kill mutants without asserting a
  real behaviour — hollow assertions pass the score but
  add no regression protection.

## Gotchas

- `coverageAnalysis: 'perTest'` requires Istanbul
  instrumentation; disable if the project uses a custom
  transpiler that conflicts with the coverage transform.
- The incremental cache (`stryker.incremental.json`)
  should be committed to avoid re-running the full suite
  in CI after cold caches.
- Stryker opens the browser for the HTML report on some
  OSes; pass `--reporters clear-text,json` in CI to
  suppress the browser launch.
- Jest with `ts-jest` requires
  `@stryker-mutator/jest-runner` ≥ 8 for ESM support.

## Verification

```bash
# Dry run — list mutants without running tests
npx stryker run --dryRun

# Run against a single file only
npx stryker run \
  --mutate 'src/core/pricing.ts'

# Confirm CI exits non-zero when score < break threshold
echo "Exit code: $?"
```

Open `reports/mutation/html/index.html` and confirm the
mutation score exceeds the `thresholds.break` value.

## Related

- `testing/mutation-testing-stryker.md`
- `testing/mutation-testing-survivor-triage.md`
- `testing/test-coverage-meaningful-metrics.md`
- `testing/jest-coverage-thresholds.md`

## Source URLs (verified 2026-08-17)

- https://stryker-mutator.io/docs/stryker-js/getting-started/
- https://stryker-mutator.io/docs/stryker-js/configuration/
- https://stryker-mutator.io/docs/stryker-js/mutators/
- https://stryker-mutator.io/docs/stryker-js/reporters/
- https://stryker-mutator.io/blog/2019-04-03/one-mutation-testing-to-rule-them-all/
