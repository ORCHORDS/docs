# GitHub Actions Required Status Checks Branch Gates

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Workers monorepo has dozens of check names across multiple workflows: unit tests, Wrangler build validation, D1 migration dry-runs, Playwright end-to-end tests, and deployment previews. After a refactor renames a workflow job from `test` to `unit-test`, PRs can be merged without test results because the old check name is still listed in branch protection rules — GitHub treats a missing check as passing by default. Separately, matrix jobs produce check names like `test (node-20)` and `test (node-22)` that branch protection cannot enumerate in advance, causing merge gates to be incomplete.

## Context

Required status checks in GitHub branch protection (and rulesets) block PR merges until named checks report `success`. The checks are matched by their exact string name — the `name:` of the workflow job or the context string passed to the Checks API. A renamed job, a changed matrix dimension, or a check from a deleted workflow silently removes a gate. GitHub does not warn when a required check has never been reported for a PR; it passes as if the check succeeded. Understanding check naming, the difference between "strict" and "loose" mode, and the relationship between rulesets and classic branch protection is required to build reliable gates for Workers deployment pipelines.

## Check name resolution

A workflow job's check context is `{job-name}` by default. When a matrix is used, it becomes `{job-name} ({matrix-value})`.

```yaml
# These jobs produce check names:
#   "lint"              → single check
#   "build / node-20"  → with matrix separator (GitHub uses " / " for nested contexts in some versions)
#   "test (20)"        → typical matrix format

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: npm run lint

  build:
    strategy:
      matrix:
        node: [20, 22]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node }}
      - run: npm run build
```

For matrix jobs, the check names `build (20)` and `build (22)` must both be listed in required status checks. If the matrix gains a new dimension, the new check name is not required until the branch protection rule is updated.

## Stable check name via a merge job

Use a final aggregating job to produce a single stable check name regardless of how many matrix jobs run:

```yaml
jobs:
  test:
    strategy:
      matrix:
        node: [20, 22]
      fail-fast: false
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node }}
      - run: npm test

  # Single stable check name for branch protection
  all-tests-pass:
    needs: test
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Evaluate matrix result
        run: |
          if [[ "${{ needs.test.result }}" != "success" ]]; then
            echo "One or more matrix test jobs failed."
            exit 1
          fi
          echo "All matrix test jobs succeeded."
```

Branch protection requires only `all-tests-pass`. The matrix dimensions can change freely without updating the branch rule.

## Wrangler build gate for Workers

Add a required check that validates the Wrangler build but does not deploy:

```yaml
# .github/workflows/workers-ci.yml
name: Workers CI

on:
  pull_request:
    branches: [main]

jobs:
  wrangler-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - run: npm ci

      - name: Validate Wrangler build
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
        run: npx wrangler deploy --dry-run --outdir dist

      - name: Check bundle size
        run: |
          SIZE=$(du -k dist/*.js | awk '{print $1}')
          echo "Bundle size: ${SIZE}KB"
          if [[ $SIZE -gt 1024 ]]; then
            echo "::error::Worker bundle exceeds 1MB (${SIZE}KB). Wrangler limit is 1MB compressed."
            exit 1
          fi

  d1-migration-dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - name: D1 migration dry-run
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: npx wrangler d1 migrations apply my-database --dry-run

  all-ci-pass:
    needs: [wrangler-build, d1-migration-dryrun]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Evaluate all CI jobs
        run: |
          RESULTS='${{ toJSON(needs) }}'
          FAILED=$(echo "$RESULTS" | jq '[to_entries[] | select(.value.result != "success")] | length')
          if [[ "$FAILED" -gt 0 ]]; then
            echo "::error::${FAILED} required CI job(s) did not succeed."
            echo "$RESULTS" | jq '.'
            exit 1
          fi
```

Require only `all-ci-pass` in branch protection. Adding new CI jobs only requires updating the `needs:` list, not the branch protection rule.

## Configuring required status checks via the API

```bash
# Using rulesets (recommended over classic branch protection)
gh api \
  --method POST \
  "/repos/{owner}/{repo}/rulesets" \
  --field name="Require CI on main" \
  --field target=branch \
  --field enforcement=active \
  --field 'conditions={"ref_name":{"include":["refs/heads/main"],"exclude":[]}}' \
  --field 'rules=[
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": false,
        "required_status_checks": [
          { "context": "all-ci-pass", "integration_id": null }
        ]
      }
    },
    { "type": "pull_request", "parameters": { "required_approving_review_count": 1 } }
  ]'
```

## Detecting stale required checks

A TypeScript script to audit whether all required check names have been reported on recent PRs:

```typescript
// scripts/audit-required-checks.ts
// Reports required checks that are never seen in recent PR check runs.

const REPO = "your-org/your-repo";
const BRANCH = "main";

async function fetchJson<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`https://api.github.com${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });
  return res.json() as Promise<T>;
}

async function auditChecks(token: string): Promise<void> {
  // Get required checks from rulesets
  const { rulesets } = await fetchJson<{ rulesets: Array<{ id: number; name: string }> }>(
    `/repos/${REPO}/rulesets`,
    token
  );
  console.log(`Found ${rulesets.length} rulesets`);

  // Get recent PRs merged to main
  const { data: prs } = await fetchJson<{
    data: Array<{ number: number; merge_commit_sha: string }>;
  }>(`/repos/${REPO}/pulls?state=closed&base=${BRANCH}&per_page=10`, token);

  const seenChecks = new Set<string>();
  for (const pr of prs.slice(0, 5)) {
    const { check_runs } = await fetchJson<{
      check_runs: Array<{ name: string; conclusion: string }>;
    }>(`/repos/${REPO}/commits/${pr.merge_commit_sha}/check-runs`, token);
    check_runs.forEach((r) => seenChecks.add(r.name));
  }

  console.log("Check names seen on recent merged PRs:", [...seenChecks].sort());
}

auditChecks(process.env.GH_TOKEN!);
```

## Anti-patterns

- Listing individual matrix job names (`test (20)`, `test (22)`) in required status checks instead of a stable merge job — any matrix dimension change breaks the gate without warning.
- Using "strict" required status check mode (`require branches to be up to date`) without merge queues — every PR must rebase before merge, creating a bottleneck on busy repos. Use a merge queue instead.
- Requiring a check by its workflow-level `name:` — the workflow name does not appear as a check context; only job names and explicit `name:` overrides on steps with `actions/github-script` or the Checks API are valid check contexts.
- Deleting old workflows without updating branch protection rules — the stale check name silently passes (not-reported = pass by default) and the merge gate is effectively removed.

## Gotchas

- GitHub treats an absent check as `pending`, not `failure`. If the workflow that produces a required check does not run on a PR (e.g., it has no `pull_request` trigger), the PR is permanently blocked. Use `if: always()` in the aggregate job and ensure the workflow triggers on `pull_request`.
- Required status checks are validated against the source app that reported them when "Source" filtering is enabled on rulesets. If the check is reported by a different app than expected (e.g., after changing the GitHub App), it does not satisfy the requirement even if the name matches.
- Renaming a workflow file does not change the check name. Renaming the `jobs.<job-id>` key does change it. Renaming the `name:` property of a job also changes it. Keep job IDs and names in sync with branch protection rules when refactoring.
- Rulesets can bypass required status checks for specific roles (e.g., `Organization admin`). Ensure bypass lists are reviewed — a bypass grants the ability to merge untested code.

## Verification

```bash
# List current required status checks on main via rulesets
gh api "/repos/{owner}/{repo}/rulesets" | jq '.[].rules[] | select(.type == "required_status_checks")'

# Simulate a PR check run to confirm the aggregate job name
gh pr create --base main --head feature/test-branch --title "Test checks"
gh pr checks <PR-number> --watch
# Look for "all-ci-pass" in the check list

# Confirm a PR cannot be merged without the required check
gh pr merge <PR-number> --squash
# Expected: error mentioning the required status check
```

## Related

- `github-required-status-checks.md`
- `github-rulesets-2026.md`
- `github-merge-queue-required-check-event-coverage.md`
- `github-actions-matrix-strategy-workers.md`
- `github-branch-protection-merge-queue.md`

## Sources

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-status-checks-before-merging
- https://docs.github.com/en/rest/checks/runs
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/using-jobs-in-a-workflow#defining-prerequisite-jobs
