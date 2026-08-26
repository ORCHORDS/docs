# github-auto-merge

**Issue:** Automatically merging PRs once all required checks pass and approvals are met
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Engineers approve a PR and leave it open waiting for a long CI run to finish, then forget to come back. Auto-merge lets a PR merge itself the moment all conditions are satisfied.

## Pattern / Solution
Auto-merge is enabled per repo (Settings → General → Allow auto-merge). Individual PRs opt in via the UI or API.

**Enable auto-merge on a PR via `gh` CLI:**
```bash
gh pr merge 123 --auto --squash    # or --merge, --rebase
```

**Enable auto-merge in a workflow (bot-created PRs):**
```yaml
jobs:
  open-pr:
    runs-on: ubuntu-latest
    steps:
      - name: Create PR
        id: pr
        run: |
          PR_URL=$(gh pr create \
            --title "chore: update dependencies" \
            --body "Automated dependency update" \
            --base main \
            --head deps/update-$(date +%Y%m%d))
          echo "url=$PR_URL" >> $GITHUB_OUTPUT
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Enable auto-merge
        run: gh pr merge --auto --squash "${{ steps.pr.outputs.url }}"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**GraphQL mutation (for fine-grained control):**
```graphql
mutation {
  enablePullRequestAutoMerge(input: {
    pullRequestId: "PR_kwDO...",
    mergeMethod: SQUASH
  }) {
    pullRequest { autoMergeRequest { enabledAt } }
  }
}
```

**Disabling auto-merge:**
```bash
gh pr merge 123 --disable-auto
```

## Gotchas
- Auto-merge requires at least one branch protection rule — without any rules, GitHub has no conditions to wait for and the PR merges immediately
- The user who enables auto-merge must have write access; the merge itself is performed by GitHub as that user
- Auto-merge is cancelled if the PR receives a review that requests changes — re-approving re-arms it
- `GITHUB_TOKEN` can enable auto-merge but the resulting merge won't trigger `push` workflows (bot limitation) — use a PAT if downstream workflows must fire
- Auto-merge does not bypass merge queue if the queue is enabled; the PR is added to the queue instead

## Related
- `github-merge-queue.md`
- `github-required-status-checks.md`
- `dependabot-best-practices-2026.md`
