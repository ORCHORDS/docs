# GitHub Actions Vitest Coverage Threshold Gate

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A PR merges code with 40% test coverage while the team's target is 80%. You want CI to fail the check when coverage drops below per-file or aggregate thresholds, post a diff of the change to the PR, and upload a coverage artifact — all without introducing a third-party coverage service.

## Context

Vitest's built-in `@vitest/coverage-v8` (or `coverage-istanbul`) provider generates LCOV, JSON, and text reports. The `thresholds` option in `vitest.config.ts` causes `vitest run --coverage` to exit with code 1 when a threshold is breached, making it a natural CI gate. Combining this with a GitHub Actions summary and PR comment gives reviewers immediate feedback. Workers-specific considerations: Vitest runs in Node.js, but the `@cloudflare/vitest-pool-workers` pool runs tests inside a miniflare environment — coverage collection in that pool requires passing `coverage: { provider: 'v8', experimentalAstAwareRemapping: true }`.

---

## 1. Vitest Coverage Configuration

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    pool: '@cloudflare/vitest-pool-workers',
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
      },
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'json', 'json-summary'],
      reportsDirectory: './coverage',
      // Aggregate thresholds — fail CI if ANY drops below these values
      thresholds: {
        lines:      80,
        functions:  80,
        branches:   75,
        statements: 80,
        // Per-file thresholds (stricter for critical paths)
        perFile: true,
        // Allow lower per-file thresholds as overrides:
        // 'src/auth/**': { lines: 95 }
      },
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.d.ts', 'src/**/*.test.ts', 'src/generated/**'],
    },
  },
});
```

## 2. CI Workflow — Run Coverage and Gate

```yaml
# .github/workflows/coverage.yml
name: Vitest Coverage Gate

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  coverage:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - name: Run tests with coverage
        id: vitest
        run: |
          pnpm vitest run --coverage 2>&1 | tee coverage-output.txt
          echo "exit_code=${PIPESTATUS[0]}" >> "$GITHUB_OUTPUT"
        # Do NOT use 'continue-on-error: true' here — let the exit code flow to the
        # post-comment step but still fail the job at the end.
        continue-on-error: true
```

## 3. Parse Coverage Summary and Post PR Comment

```yaml
      - name: Parse coverage summary
        id: summary
        run: |
          SUMMARY=$(node -e "
            const s = require('./coverage/coverage-summary.json');
            const t = s.total;
            const fmt = (x) => x.pct.toFixed(1) + '%';
            console.log([
              '| Metric | Coverage | Threshold |',
              '|--------|----------|-----------|',
              \`| Lines      | \${fmt(t.lines)}      | 80% |\`,
              \`| Functions  | \${fmt(t.functions)}  | 80% |\`,
              \`| Branches   | \${fmt(t.branches)}   | 75% |\`,
              \`| Statements | \${fmt(t.statements)} | 80% |\`,
            ].join('\n'));
          ")
          echo "table<<EOF" >> "$GITHUB_OUTPUT"
          echo "$SUMMARY"   >> "$GITHUB_OUTPUT"
          echo "EOF"        >> "$GITHUB_OUTPUT"

      - name: Post coverage comment on PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const status = '${{ steps.vitest.outputs.exit_code }}' === '0' ? '✅ Passed' : '❌ Failed';
            const body = [
              `## Coverage Report — ${status}`,
              '',
              '${{ steps.summary.outputs.table }}',
              '',
              `> Full report attached as workflow artifact.`,
            ].join('\n');
            const { data: comments } = await github.rest.issues.listComments({
              owner: context.repo.owner, repo: context.repo.repo,
              issue_number: context.issue.number,
            });
            const existing = comments.find(c => c.body.startsWith('## Coverage Report'));
            const method = existing ? 'updateComment' : 'createComment';
            const writeComment = github.rest.issues[method];
            await writeComment({
              owner: context.repo.owner, repo: context.repo.repo,
              ...(existing ? { comment_id: existing.id } : { issue_number: context.issue.number }),
              body,
            });
```

## 4. Upload Coverage Artifact and Job Summary

```yaml
      - name: Upload coverage report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-${{ github.run_id }}
          path: coverage/
          retention-days: 30

      - name: Write job summary
        if: always()
        run: |
          echo "## Coverage Gate" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"
          cat coverage-output.txt | tail -20 >> "$GITHUB_STEP_SUMMARY"

      - name: Fail job if thresholds not met
        if: steps.vitest.outputs.exit_code != '0'
        run: |
          echo "Coverage thresholds not met — see report above"
          exit 1
```

## 5. Enforce Coverage Ratchet (Never Let Coverage Drop Below Current)

```typescript
// scripts/coverage-ratchet.ts
// Reads coverage-summary.json from main (baseline) and PR branch and
// fails if any metric is lower than the baseline — stricter than fixed thresholds.
import { readFileSync, writeFileSync } from 'fs';

type CoverageMetric = { pct: number };
type CoverageSummary = { lines: CoverageMetric; functions: CoverageMetric; branches: CoverageMetric; statements: CoverageMetric };

const pr   = (JSON.parse(readFileSync('coverage/coverage-summary.json', 'utf8')).total) as CoverageSummary;
const base = (JSON.parse(readFileSync('coverage-baseline/coverage-summary.json', 'utf8')).total) as CoverageSummary;

const metrics = ['lines', 'functions', 'branches', 'statements'] as const;
let failed = false;

for (const m of metrics) {
  const diff = pr[m].pct - base[m].pct;
  if (diff < -0.5) {  // allow 0.5% rounding tolerance
    console.error(`FAIL: ${m} dropped ${diff.toFixed(1)}% (${base[m].pct.toFixed(1)}% → ${pr[m].pct.toFixed(1)}%)`);
    failed = true;
  } else {
    console.log(`OK:   ${m} ${base[m].pct.toFixed(1)}% → ${pr[m].pct.toFixed(1)}% (${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%)`);
  }
}

if (failed) process.exit(1);
```

---

## Anti-patterns

- Setting thresholds only at the aggregate level — a file at 0% coverage is hidden if unrelated files overcompensate. Use `perFile: true` for critical business logic.
- Using `continue-on-error: true` on the vitest step without a separate failure gate — the job shows green even when thresholds are breached.
- Running coverage in the Workers pool for every test run including watch mode — coverage instrumentation in V8 is 2–4× slower; gate it behind `CI=true` or a separate script.
- Checking in `coverage/` to git — the directory is large and the contents change every run; add it to `.gitignore`.

## Gotchas

- `@cloudflare/vitest-pool-workers` requires `experimentalAstAwareRemapping: true` for accurate source-map line attribution when using the V8 provider; without it, coverage maps back to bundled lines rather than source TypeScript.
- Vitest exits 0 even when tests pass but thresholds are configured and breached in some versions — always verify the exit code against `coverage-summary.json` as a second check.
- `json-summary` reporter is separate from `json` reporter; both are needed — `json-summary` produces the `coverage-summary.json` file the ratchet script reads.
- When running in a monorepo with workspaces, ensure the `reportsDirectory` is an absolute path or relative to the workspace root to avoid per-package path collisions.

## Verification

```bash
# Run locally and check exit code
pnpm vitest run --coverage; echo "Exit: $?"

# Inspect the summary
cat coverage/coverage-summary.json | python3 -m json.tool | grep -A3 '"total"'
```

The `coverage` job must be added as a required status check in branch protection rules. Name the check `coverage` (matching the job name) so it cannot be bypassed.

## Related

- `github-actions-vitest-test-sharding-workers.md`
- `github-actions-merge-group-integration-testing.md`
- `github-actions-required-status-checks-branch-gates.md`
- `github-actions-job-summaries-annotations-reporting.md`

## Sources

- https://vitest.dev/config/#coverage-thresholds
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://vitest.dev/guide/coverage.html
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#adding-a-job-summary
