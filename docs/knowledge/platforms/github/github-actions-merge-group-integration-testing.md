# GitHub Actions merge_group Trigger for Integration Testing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

PRs that individually pass unit tests still break the main branch after merge because
integration tests only run post-merge.  The `merge_group` event lets you run those
tests *inside* the merge queue, blocking any batch that would break the branch.

## Context

GitHub's merge queue groups PRs into batches and creates a temporary `gh-readonly-queue`
branch per batch.  The `merge_group` trigger fires for each batch so workflows can run
the same integration suite that would normally run on `push` to `main`, but *before* the
commits land.  A failing job blocks the entire batch and ejects the offending PR(s).

The event is distinct from `pull_request` and `push`; required status checks must be
configured to expect results from `merge_group` runs, not only from `pull_request` runs.

---

## 1. Basic merge_group Workflow

```yaml
# .github/workflows/integration.yml
name: Integration Tests

on:
  pull_request:
    branches: [main]
  merge_group:          # fires when a PR enters the merge queue
    types: [checks_requested]

jobs:
  integration:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Run integration tests
        run: pnpm test:integration
        env:
          DATABASE_URL: ${{ secrets.TEST_DATABASE_URL }}
```

---

## 2. Distinguishing merge_group from pull_request Context

Some steps should behave differently depending on which event triggered the run.

```yaml
      - name: Set deploy target
        id: target
        run: |
          if [[ "${{ github.event_name }}" == "merge_group" ]]; then
            echo "env=staging-queue" >> "$GITHUB_OUTPUT"
          else
            echo "env=preview" >> "$GITHUB_OUTPUT"
          fi

      - name: Deploy preview / staging
        run: pnpm deploy --env ${{ steps.target.outputs.env }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## 3. Cloudflare Workers Integration Test Against D1

Run a Workers integration suite in the merge queue that spins up a throwaway D1
database, seeds it, and tears it down after the test.

```yaml
  d1-integration:
    runs-on: ubuntu-latest
    environment: merge-queue-test      # scoped secrets + protection rules
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - run: pnpm install --frozen-lockfile

      - name: Create ephemeral D1 database
        id: d1
        run: |
          DB_NAME="ci-mq-${{ github.run_id }}-${{ github.run_attempt }}"
          OUTPUT=$(pnpm wrangler d1 create "$DB_NAME" --json)
          echo "db_id=$(echo "$OUTPUT" | jq -r '.uuid')" >> "$GITHUB_OUTPUT"
          echo "db_name=$DB_NAME" >> "$GITHUB_OUTPUT"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Apply migrations
        run: pnpm wrangler d1 migrations apply "${{ steps.d1.outputs.db_name }}" --env test
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Run integration tests
        run: pnpm vitest run --project integration
        env:
          TEST_D1_DATABASE_ID: ${{ steps.d1.outputs.db_id }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Delete ephemeral D1 database
        if: always()
        run: pnpm wrangler d1 delete "${{ steps.d1.outputs.db_name }}" --force
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## 4. Required Status Checks Configuration

The required status check must reference the `merge_group` event, not just the
`pull_request` event.  Both must be listed in branch protection / ruleset settings.

```yaml
# wrangler.toml excerpt — not needed, this is a GitHub settings concern
# In the repository Ruleset or Branch Protection:
#   Required status checks:
#     - "integration / integration"    (from pull_request)
#     - "integration / d1-integration" (from merge_group)
#   Require branches to be up to date: true
```

In a Ruleset (GitHub UI or API):

```jsonc
// PATCH /repos/{owner}/{repo}/rulesets/{id}
{
  "rules": [
    {
      "type": "required_status_checks",
      "parameters": {
        "required_status_checks": [
          { "context": "integration / integration" },
          { "context": "integration / d1-integration" }
        ],
        "strict_required_status_checks_policy": true
      }
    }
  ]
}
```

---

## 5. Skipping Expensive Steps Outside the Queue

Heavy smoke tests should only run in `merge_group` to keep PR feedback fast.

```yaml
      - name: Smoke tests (queue only)
        if: github.event_name == 'merge_group'
        run: pnpm test:smoke
        timeout-minutes: 10
```

---

## Anti-patterns

- Registering a required status check only for `pull_request` but not `merge_group`:
  the queue will report no status and may auto-pass or permanently stall.
- Running the full integration suite on every `push` to feature branches — use
  `merge_group` + `pull_request` scoping to avoid burning minutes.
- Not cleaning up ephemeral resources (D1 DBs, R2 buckets) on test failure: use
  `if: always()` on teardown steps.
- Hardcoding `main` in `merge_group` triggers — the queue fires regardless of target
  branch; filter with `if: github.base_ref == 'main'` if needed.

## Gotchas

- The temporary `gh-readonly-queue/*` branch does NOT match `push: branches: [main]`
  patterns, so `push`-triggered workflows do not fire for queue batches.
- `github.event.merge_group.base_sha` and `head_sha` are available for diffing.
- Status checks from `merge_group` runs are reported against the queue branch, not
  the PR branch — the PR page shows them only if the check name matches exactly.
- Secrets from `environment:` blocks require the environment to allow `merge_group`
  deployments; create a dedicated `merge-queue-test` environment with no required
  reviewers but scoped secrets.

## Verification

```bash
# Confirm the merge_group event fires by inspecting a recent run
gh run list --workflow integration.yml --event merge_group --limit 5

# Check required status checks are configured for the ruleset
gh api repos/{owner}/{repo}/rulesets \
  | jq '.[].rules[] | select(.type=="required_status_checks")'
```

## Related

- `github-merge-queue-mechanics.md`
- `github-merge-queue-required-check-event-coverage.md`
- `github-merge-queue-workers-deploy-coordination.md`
- `github-actions-cloudflare-d1-migration-pipeline.md`
- `github-actions-required-status-checks-branch-gates.md`

## Sources

- https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#merge_group
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
- https://github.blog/changelog/2023-02-08-pull-request-merge-queue-public-beta/
