# GitHub Merge Queue Integration with Cloudflare Workers CI

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Multiple contributors merge PRs to `main` simultaneously. Individual PR checks passed against the PR's base, but when two PRs land together one breaks the other's Worker smoke test. GitHub Merge Queue serialises and batches merges, running CI against the combined state before any commit reaches `main`.

## Context

GitHub Merge Queue (enabled per-branch in repository settings) holds PRs in a queue, groups them into batches, and runs all required status checks against the merged state of the batch. Only when checks pass does the batch land on `main`. The `merge_group` event triggers workflows specifically for this validation step, separate from `pull_request` checks.

For Cloudflare Workers this means deploying a preview and running a smoke test against it — in the merge queue context — before the code is allowed onto the default branch.

## Enabling Merge Queue

In **Settings → Branches → Branch protection rules** for `main`:

1. Enable **Require merge queue**.
2. Under **Require status checks to pass before merging**, add the status check names that must pass in the merge queue context (e.g., `merge-queue-smoke-test`).
3. Set **Maximum PRs to build** (1–100) and **Minimum PRs to merge** to tune batch size.

## Merge Queue Workflow

```yaml
# .github/workflows/merge-queue-ci.yml
name: Merge Queue CI

on:
  # Fired when GitHub adds a PR to the merge queue batch
  merge_group:
    types: [checks_requested]

  # Also run on regular PRs so developers see results before queuing
  pull_request:
    branches: [main]

concurrency:
  group: merge-queue-${{ github.ref }}
  cancel-in-progress: false # never cancel a merge-queue run mid-flight

jobs:
  unit-tests:
    name: Unit tests
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
      - run: npm ci
      - run: npm test -- --reporter=github-actions

  deploy-preview:
    name: Deploy preview Worker
    runs-on: ubuntu-24.04
    # Only deploy a live preview during merge-queue validation
    if: github.event_name == 'merge_group'
    outputs:
      preview_url: ${{ steps.deploy.outputs.preview_url }}
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - name: Install Wrangler
        run: npm install -g wrangler@3.57.0

      - name: Deploy preview version
        id: deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_STAGING }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          # Workers versioning: upload without promoting to live traffic
          VERSION_OUTPUT=$(wrangler versions upload --env staging 2>&1)
          echo "$VERSION_OUTPUT"
          # Extract the preview URL from wrangler output
          PREVIEW_URL=$(echo "$VERSION_OUTPUT" | grep -oP 'https://[^\s]+\.workers\.dev' | tail -1)
          echo "preview_url=$PREVIEW_URL" >> "$GITHUB_OUTPUT"

  smoke-test:
    name: merge-queue-smoke-test
    runs-on: ubuntu-24.04
    needs: [unit-tests, deploy-preview]
    if: github.event_name == 'merge_group'
    steps:
      - uses: actions/checkout@v4

      - name: Run smoke tests against preview
        env:
          PREVIEW_URL: ${{ needs.deploy-preview.outputs.preview_url }}
        run: |
          echo "Testing preview at $PREVIEW_URL"

          # Health endpoint
          STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "$PREVIEW_URL/health")
          [ "$STATUS" = "200" ] || { echo "Health check failed: $STATUS"; exit 1; }

          # Functional smoke test
          BODY=$(curl -sf "$PREVIEW_URL/api/ping")
          echo "$BODY" | jq -e '.ok == true' || { echo "Ping failed"; exit 1; }

          # Latency guard: p50 must be < 200ms
          TIME=$(curl -sf -o /dev/null -w "%{time_total}" "$PREVIEW_URL/api/ping")
          python3 -c "import sys; t=float('$TIME'); sys.exit(0 if t < 0.2 else 1)" \
            || { echo "Latency too high: ${TIME}s"; exit 1; }

          echo "All smoke tests passed"

  # Summary job that merge queue watches as the required check
  merge-queue-gate:
    name: merge-queue-smoke-test
    runs-on: ubuntu-24.04
    needs: [unit-tests, smoke-test]
    if: always() && github.event_name == 'merge_group'
    steps:
      - name: Evaluate results
        run: |
          if [ "${{ needs.smoke-test.result }}" != "success" ] || \
             [ "${{ needs.unit-tests.result }}" != "success" ]; then
            echo "Merge queue gate FAILED"
            exit 1
          fi
          echo "Merge queue gate PASSED"
```

## Handling Parallel Validation Groups

GitHub Merge Queue can split PRs into multiple parallel groups when the queue is long. Each group runs independently, and only the groups that pass merge. Your CI must be group-aware:

```yaml
# The merge_group context provides group information
- name: Log merge group context
  run: |
    echo "Head SHA:  ${{ github.event.merge_group.head_sha }}"
    echo "Base SHA:  ${{ github.event.merge_group.base_sha }}"
    echo "Head ref:  ${{ github.event.merge_group.head_ref }}"
    # head_ref format: refs/heads/gh-readonly-queue/main/pr-<n>-<sha>
    PR_NUM=$(echo "${{ github.event.merge_group.head_ref }}" \
      | grep -oP 'pr-\K[0-9]+')
    echo "PR number: $PR_NUM"
```

## Anti-patterns

- Setting `cancel-in-progress: true` on merge queue concurrency — a cancelled merge queue run causes the PR to be removed from the queue and must be re-queued manually.
- Requiring the same check name for both `pull_request` and `merge_group` events when the jobs differ — use distinct job names and configure separate required status checks.
- Deploying to the production environment during merge queue validation — use preview/staging Workers only; production deploys happen after the merge.
- Making the smoke test hit a mutable staging URL instead of the preview version URL — two merge queue groups would test each other's previews non-deterministically.

## Gotchas

- If a required status check job is skipped (via `if:` condition), GitHub treats it as **not run**, not as passed. Add a gate job with `if: always()` that explicitly sets exit code.
- Merge queue does not retry failed groups automatically — a flaky test causes a PR to be ejected from the queue.
- The `merge_group` event is **not** available for `push` or `workflow_dispatch` triggers; keep merge-queue logic in a dedicated workflow.
- Worker preview URLs generated by `wrangler versions upload` are ephemeral — they expire after 24 hours or when a new version supersedes them.

## Verification

```bash
# List open merge queue entries
gh api repos/example-org/example-repo/merge-queue \
  --jq '.entries[] | {pr: .pull_request.number, state: .state}'

# Check required status check configuration
gh api repos/example-org/example-repo/branches/main/protection \
  --jq '.required_status_checks.contexts'

# Trigger a merge queue run manually (requires admin)
gh pr merge 42 --merge --auto
```

## Related

- `github-actions-reusable-workflows-workers-deploy.md`
- `github-environments-cloudflare-deployment-protection.md`
- `github-issue-auto-triage-workers-ai-webhook.md`

## Sources

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
- https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#merge_group
- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
