# Code Coverage for Workers Tests Using V8/c8 with Vitest

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Cloudflare Workers project has a growing test suite but you have no visibility into which code paths are actually exercised. Developers merge changes touching untested modules without realizing coverage has dropped. You need automated coverage measurement that enforces a minimum threshold, blocks PRs that drop below it, and gives reviewers a per-file coverage report without requiring them to run tests locally.

---

## Context
Vitest ships with first-class V8 coverage support via `@vitest/coverage-v8`, which hooks into the V8 engine's built-in instrumentation rather than transpiling code with Istanbul. This works correctly with Workers TypeScript because the V8 provider instruments the compiled JavaScript directly. Configuring coverage thresholds in `vitest.config.ts` causes `vitest run --coverage` to exit non-zero when any threshold is missed, making it straightforward to enforce in CI. The HTML report can be uploaded as a GitHub Actions artifact, and a separate step can parse the coverage JSON summary to post per-file numbers as a PR comment.

---

## Vitest Coverage Configuration

```typescript
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wranglerConfigPath: './wrangler.toml',
      },
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'json-summary', 'html', 'lcov'],
      reportsDirectory: './coverage',
      // Enforce minimums — vitest exits 1 if any threshold is missed
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 75,
        statements: 80,
      },
      // Exclude auto-generated and config files from coverage
      exclude: [
        'node_modules/**',
        'dist/**',
        'coverage/**',
        '**/*.d.ts',
        '**/*.config.ts',
        '**/*.config.js',
        '**/test/**',
        '**/tests/**',
        'src/generated/**',       // e.g. Prisma client, protobuf output
        'src/migrations/**',      // SQL migration files
        'src/types/**',           // type-only files have no executable lines
        'worker-configuration.d.ts',
      ],
      // Report coverage relative to project root
      include: ['src/**/*.ts'],
      // When true, files with zero coverage appear in the report
      all: true,
    },
  },
});
```

---

## Example Source File Under Test

```typescript
// src/lib/format.ts  — a utility with multiple branches
export function formatCurrency(amount: number, currency: string): string {
  if (amount < 0) throw new RangeError('amount must be non-negative');
  if (!currency.match(/^[A-Z]{3}$/)) throw new TypeError('currency must be a 3-letter ISO code');
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amount);
}

export function truncate(text: string, maxLength: number): string {
  if (maxLength <= 0) throw new RangeError('maxLength must be positive');
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1)}…`;
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/[\s_-]+/g, '-')
    .replace(/^-+|-+$/g, '');
}
```

```typescript
// test/lib/format.test.ts
import { describe, it, expect } from 'vitest';
import { formatCurrency, truncate, slugify } from '../../src/lib/format';

describe('formatCurrency', () => {
  it('formats USD correctly', () => {
    expect(formatCurrency(1234.5, 'USD')).toBe('$1,234.50');
  });
  it('throws on negative amount', () => {
    expect(() => formatCurrency(-1, 'USD')).toThrow(RangeError);
  });
  it('throws on invalid currency code', () => {
    expect(() => formatCurrency(10, 'us')).toThrow(TypeError);
  });
});

describe('truncate', () => {
  it('returns text unchanged when within limit', () => {
    expect(truncate('hello', 10)).toBe('hello');
  });
  it('truncates long text with ellipsis', () => {
    expect(truncate('hello world', 8)).toBe('hello w…');
  });
  it('throws on non-positive maxLength', () => {
    expect(() => truncate('hello', 0)).toThrow(RangeError);
  });
});

describe('slugify', () => {
  it('converts to lowercase kebab', () => {
    expect(slugify('Hello World')).toBe('hello-world');
  });
  it('strips special characters', () => {
    expect(slugify('foo & bar!')).toBe('foo-bar');
  });
  it('trims leading and trailing hyphens', () => {
    expect(slugify('  --foo--  ')).toBe('foo');
  });
});
```

---

## GitHub Actions Workflow with Coverage Artifact and PR Comment

```yaml
# .github/workflows/coverage.yml
name: Test Coverage

on:
  push:
    branches: [main]
  pull_request:

jobs:
  coverage:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write   # needed to post PR comments
      contents: read

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci

      - name: Run tests with coverage
        run: npx vitest run --coverage

      - name: Upload HTML coverage report
        if: always()   # upload even when thresholds fail
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage/
          retention-days: 14

      - name: Post coverage summary to PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const summary = JSON.parse(
              fs.readFileSync('coverage/coverage-summary.json', 'utf8')
            );
            const total = summary.total;
            const lines = [
              '## Coverage Report',
              '',
              `| Metric | Coverage |`,
              `|--------|----------|`,
              `| Lines | ${total.lines.pct}% (${total.lines.covered}/${total.lines.total}) |`,
              `| Functions | ${total.functions.pct}% (${total.functions.covered}/${total.functions.total}) |`,
              `| Branches | ${total.branches.pct}% (${total.branches.covered}/${total.branches.total}) |`,
              `| Statements | ${total.statements.pct}% (${total.statements.covered}/${total.statements.total}) |`,
              '',
              '<details><summary>Per-file coverage</summary>',
              '',
              '| File | Lines | Functions | Branches |',
              '|------|-------|-----------|----------|',
              ...Object.entries(summary)
                .filter(([k]) => k !== 'total')
                .sort(([, a], [, b]) => a.lines.pct - b.lines.pct)
                .slice(0, 20)  // top 20 lowest-coverage files
                .map(([file, data]) => {
                  const short = file.replace(process.cwd() + '/', '');
                  return `| \`${short}\` | ${data.lines.pct}% | ${data.functions.pct}% | ${data.branches.pct}% |`;
                }),
              '',
              '</details>',
            ];

            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: lines.join('\n'),
            });
```

---

## Anti-patterns
- **Using `@vitest/coverage-istanbul` for Workers** — Istanbul instruments source with babel transforms that conflict with the Workers runtime. Use `@vitest/coverage-v8` (the V8 provider) for Worker projects.
- **Committing the `coverage/` directory** — Coverage artifacts are large, change on every run, and belong in CI artifact storage. Add `coverage/` to `.gitignore`.
- **Setting thresholds at 100%** — 100% coverage is achievable but often requires testing trivial getters and error-path branches that add noise without value. 80% lines / 75% branches is a practical floor for most Worker projects.
- **Forgetting `all: true` in coverage config** — Without `all: true`, files that aren't imported by any test are invisible to the coverage report. A module with 0% coverage won't appear and won't drag down your numbers — a false sense of security.

---

## Gotchas
- `@vitest/coverage-v8` must be installed explicitly — it's not bundled with Vitest. Run `npm install -D @vitest/coverage-v8` before running `--coverage`.
- The `json-summary` reporter is required for the PR comment script to parse `coverage/coverage-summary.json`. Without it, the comment step will fail.
- lcov output (`lcov.info`) can be consumed by tools like Codecov or SonarCloud for trend tracking. Add the lcov reporter alongside `json-summary` if you use these services.
- `thresholds` failures exit the process with code 1 after all tests pass. If you have a subsequent step that needs to run even on threshold failures (like uploading the HTML artifact), use `if: always()` in your workflow step.
- Auto-generated Zod schema types or Wrangler-generated `worker-configuration.d.ts` may contain unreachable branches in the compiled output. Always add these paths to the `exclude` array to avoid phantom uncovered branch counts.

---

## Verification

```bash
# Run tests with coverage report
npx vitest run --coverage

# View text summary in terminal
npx vitest run --coverage --reporter=verbose 2>&1 | tail -30

# Open HTML report in browser
open coverage/index.html  # macOS
xdg-open coverage/index.html  # Linux

# Check thresholds without running tests (parse summary JSON)
node -e "
  const s = require('./coverage/coverage-summary.json').total;
  console.table({ lines: s.lines.pct, functions: s.functions.pct, branches: s.branches.pct });
"

# Verify excluded files are absent from report
grep 'generated' coverage/coverage-summary.json && echo 'WARN: generated files in coverage' || echo 'OK: generated files excluded'
```

---

## Related
- `workers-api-contract-testing-zod.md`
- `workers-property-based-testing-fast-check.md`
- `workers-performance-regression-test-benchmark.md`

---

## Sources
- Vitest coverage documentation — https://vitest.dev/guide/coverage
- @vitest/coverage-v8 — https://github.com/vitest-dev/vitest/tree/main/packages/coverage-v8
- Cloudflare Workers Vitest pool — https://developers.cloudflare.com/workers/testing/vitest-integration/
- GitHub Actions upload-artifact — https://github.com/actions/upload-artifact
