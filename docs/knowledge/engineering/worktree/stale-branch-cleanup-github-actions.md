# Stale Branch Cleanup Automation with GitHub Actions

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

---

## Symptom / Use-case

A repository used by multiple engineers accumulates dozens—sometimes hundreds—of abandoned
branches over months. Feature branches merged weeks ago still exist under `origin/`, sprint
branches from past quarters crowd `git branch -r`, and developers waste time deciphering
which names are still alive. Manual triage happens once, then drifts again. You need a
repeatable, policy-driven automation that deletes stale remote branches on a schedule,
notifies branch owners before deletion, and skips protected branches unconditionally.

---

## Context

GitHub's default merge-and-delete-branch button removes the branch immediately after a PR
merges, but it only fires when a PR is the merge vehicle. Branches pushed directly, branches
whose PRs were merged via the API, rebase-merged branches where the checkbox was skipped,
and long-lived experiment branches all escape that gate. For a Cloudflare Workers monorepo
with many contributors the accumulation is fast: each Worker, each binding change, and each
migration experiment tends to live on its own branch.

The GitHub Actions scheduler can run a workflow nightly or weekly. Combined with the GitHub
REST API (or `gh` CLI) it can query branches, check last-commit age, verify merged status,
warn owners via issue comment or PR mention, and finally delete after a grace period.

Key constraints:
- `main`, `production`, `staging`, `release/*`, and any branch referenced by an open PR must
  never be deleted automatically.
- Branch owners (last committer) should receive at least one warning before deletion.
- The workflow must be idempotent: re-running it on the same set of stale branches is safe.
- A manual override label (`no-auto-delete`) on the most-recent PR for that branch should
  suppress deletion permanently.

---

## Workflow Architecture

```
Schedule (weekly) ──► Inventory step ──► Filter step ──► Warn step ──► Delete step
                       (all branches)    (staleness,      (open issue    (after grace
                                         open PR,         or comment)    period)
                                         protection)
```

The workflow state is tracked in a GitHub Actions summary artifact and optionally a small
JSON file committed to a `.github/branch-health/` directory so the warn→delete grace period
survives across weekly runs.

---

## GitHub Actions Workflow

```yaml
# .github/workflows/stale-branch-cleanup.yml
name: Stale Branch Cleanup

on:
  schedule:
    - cron: '0 3 * * 1'   # Every Monday at 03:00 UTC
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Dry run (no deletions, no notifications)'
        type: boolean
        default: true

permissions:
  contents: write          # delete branches
  issues: write            # open warning issues
  pull-requests: read      # check open PRs

jobs:
  cleanup:
    runs-on: ubuntu-latest
    env:
      STALE_DAYS: 60          # branch not pushed to in 60 days → stale
      GRACE_DAYS: 7           # days between warning and deletion
      DRY_RUN: ${{ github.event.inputs.dry_run || 'false' }}
      GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Identify stale branches
        id: identify
        run: |
          REPO="${{ github.repository }}"
          NOW=$(date -u +%s)
          STALE_CUTOFF=$(( NOW - STALE_DAYS * 86400 ))
          GRACE_CUTOFF=$(( NOW - GRACE_DAYS * 86400 ))

          # Branches protected from auto-deletion
          PROTECTED_PATTERN="^(main|master|production|staging|develop)$|^release/|^hotfix/"

          # Branches referenced by an open PR
          OPEN_PR_BRANCHES=$(gh api "repos/$REPO/pulls?state=open&per_page=100" \
            --paginate --jq '.[].head.ref' | sort -u)

          stale_json="[]"

          while IFS= read -r branch; do
            # Skip protected names
            if echo "$branch" | grep -qE "$PROTECTED_PATTERN"; then
              continue
            fi
            # Skip if referenced by open PR
            if echo "$OPEN_PR_BRANCHES" | grep -qxF "$branch"; then
              continue
            fi

            # Get last commit date
            last_commit_ts=$(gh api "repos/$REPO/branches/$branch" \
              --jq '.commit.commit.author.date' 2>/dev/null | \
              xargs -I{} date -d {} +%s 2>/dev/null || echo 0)

            if [[ "$last_commit_ts" -lt "$STALE_CUTOFF" ]]; then
              # Get last committer login
              author=$(gh api "repos/$REPO/branches/$branch" \
                --jq '.commit.author.login // "unknown"' 2>/dev/null || echo "unknown")

              stale_json=$(echo "$stale_json" | jq \
                --arg b "$branch" \
                --arg a "$author" \
                --arg ts "$last_commit_ts" \
                --arg gc "$GRACE_CUTOFF" \
                '. + [{"branch":$b,"author":$a,"last_commit_ts":($ts|tonumber),
                        "past_grace":( ($ts|tonumber) < ($gc|tonumber) )}]')
            fi
          done < <(gh api "repos/$REPO/branches?per_page=100" \
            --paginate --jq '.[].name')

          echo "stale_branches=$(echo "$stale_json" | jq -c '.')" >> "$GITHUB_OUTPUT"
          echo "Found $(echo "$stale_json" | jq 'length') stale branches"

      - name: Warn branch owners
        if: env.DRY_RUN == 'false'
        env:
          STALE: ${{ steps.identify.outputs.stale_branches }}
        run: |
          REPO="${{ github.repository }}"
          # Warn branches NOT yet past grace period
          echo "$STALE" | jq -r '.[] | select(.past_grace == false) |
            "\(.branch)\t\(.author)"' | \
          while IFS=$'\t' read -r branch author; do
            # Check if we already warned this week (idempotency)
            existing=$(gh issue list \
              --label "stale-branch" \
              --search "\"$branch\" in:title" \
              --json number,title --jq '.[0].number // ""')
            if [[ -z "$existing" ]]; then
              gh issue create \
                --title "Stale branch scheduled for deletion: \`$branch\`" \
                --label "stale-branch" \
                --assignee "$author" \
                --body "$(cat <<EOF
  ## Stale Branch Notice

  Branch \`$branch\` has not received any commits in over ${{ env.STALE_DAYS }} days.
  It is scheduled for automatic deletion in ${{ env.GRACE_DAYS }} days.

  **Owner**: @$author

  ### Options
  - Push a commit to reset the staleness timer.
  - Add the \`no-auto-delete\` label to the most-recent PR for this branch.
  - Delete the branch yourself now if you no longer need it.

  This issue will be closed automatically once the branch is deleted or becomes active.
  EOF
  )"
            fi
          done

      - name: Delete past-grace branches
        if: env.DRY_RUN == 'false'
        env:
          STALE: ${{ steps.identify.outputs.stale_branches }}
        run: |
          REPO="${{ github.repository }}"
          echo "$STALE" | jq -r '.[] | select(.past_grace == true) | .branch' | \
          while read -r branch; do
            echo "Deleting $branch"
            gh api --method DELETE "repos/$REPO/git/refs/heads/$branch" && \
              echo "Deleted: $branch" || echo "Failed to delete: $branch"

            # Close associated warning issue if it exists
            issue=$(gh issue list \
              --label "stale-branch" \
              --search "\"$branch\" in:title" \
              --json number --jq '.[0].number // ""')
            [[ -n "$issue" ]] && gh issue close "$issue" \
              --comment "Branch \`$branch\` has been automatically deleted."
          done

      - name: Dry-run summary
        if: env.DRY_RUN == 'true'
        env:
          STALE: ${{ steps.identify.outputs.stale_branches }}
        run: |
          echo "## Dry-run summary" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"
          echo "| Branch | Author | Past grace? |" >> "$GITHUB_STEP_SUMMARY"
          echo "|--------|--------|-------------|" >> "$GITHUB_STEP_SUMMARY"
          echo "$STALE" | jq -r \
            '.[] | "| \(.branch) | \(.author) | \(.past_grace) |"' \
            >> "$GITHUB_STEP_SUMMARY"
```

---

## Repository-Level Branch Protection Exemptions

Certain long-lived branches should be registered in a config file so the workflow remains
authoritative without hard-coding patterns per repo.

```json
// .github/branch-cleanup-config.json
{
  "never_delete": [
    "main",
    "production",
    "staging"
  ],
  "never_delete_patterns": [
    "release/.*",
    "hotfix/.*",
    "support/.*"
  ],
  "stale_days": 60,
  "grace_days": 7
}
```

Read the config in the workflow:

```yaml
- name: Load config
  id: config
  run: |
    cfg=".github/branch-cleanup-config.json"
    if [[ -f "$cfg" ]]; then
      echo "stale_days=$(jq '.stale_days' $cfg)" >> "$GITHUB_OUTPUT"
      echo "grace_days=$(jq '.grace_days' $cfg)" >> "$GITHUB_OUTPUT"
    else
      echo "stale_days=60" >> "$GITHUB_OUTPUT"
      echo "grace_days=7"  >> "$GITHUB_OUTPUT"
    fi
```

---

## Opt-out Label Convention

A PR merged with the label `no-auto-delete` should protect its source branch indefinitely.
Add this check to the filter step:

```bash
# Check for no-auto-delete label on last merged PR for this branch
last_pr=$(gh api "repos/$REPO/pulls?state=closed&head=$REPO_OWNER:$branch&per_page=1" \
  --jq '.[0].labels[].name' 2>/dev/null || true)

if echo "$last_pr" | grep -q "no-auto-delete"; then
  echo "Skipping $branch (no-auto-delete label)"
  continue
fi
```

---

## Anti-patterns

- **Deleting without grace period**: Branches occasionally belong to work-in-progress that
  simply hasn't been pushed recently (local commits). A warning window is mandatory.
- **Using push date on the PR, not the branch**: The merged PR's `merged_at` date is the
  wrong signal for deletion because a developer might keep building on the same branch after
  merge. Always use the branch's most-recent commit author date.
- **Skipping pagination**: `gh api` with `--paginate` is required; a repository with more
  than 100 branches silently truncates without it.
- **Deleting branches with `git push origin --delete` from a checkout**: This relies on SSH
  key access and fails in ephemeral runners that only have the `GITHUB_TOKEN`. Use the REST
  API (`DELETE /repos/{owner}/{repo}/git/refs/heads/{branch}`) instead.
- **Hard-coding `main` as the only protected branch**: Projects may have `master`, `trunk`,
  or `develop` as their default. Always pull the default branch from the API:
  `gh api repos/$REPO --jq '.default_branch'`.

---

## Gotchas

- **Rate limits**: Iterating over hundreds of branches with one API call per branch hits the
  5,000 req/hour limit for `GITHUB_TOKEN`. Batch the commit-date lookups using
  `gh api /repos/{owner}/{repo}/commits?sha={branch}&per_page=1` to get just the top commit
  and cache results in a JSON file between runs.
- **Deleted branch → open PR**: A branch with an open PR still in draft state is not caught
  by `state=open` filtering if the PR was converted to draft after creation. Always check
  `draft` field as well: `.[] | select(.draft == true or .draft == false) | .head.ref`.
- **Forks**: `gh api repos/$REPO/branches` only lists branches in the upstream repo.
  Cross-fork branches (PRs from forks) are never in scope and need no special handling.
- **Re-entrant runs**: If a scheduled Monday run overlaps with a `workflow_dispatch` dry run,
  two concurrent runs may both try to open warning issues for the same branch, creating
  duplicates. Use the idempotency check (`gh issue list --search`) shown above.

---

## Verification

```bash
# Count branches older than 60 days locally (sanity check before running workflow)
git fetch --prune
git for-each-ref --format='%(refname:short) %(authordate:unix)' refs/remotes/origin/ | \
  awk -v cutoff="$(date -d '60 days ago' +%s)" '$2 < cutoff {print $1}' | \
  grep -vE 'HEAD|main|production|staging|release/'

# Trigger a dry-run manually
gh workflow run stale-branch-cleanup.yml -f dry_run=true

# Watch the run
gh run watch $(gh run list --workflow=stale-branch-cleanup.yml --limit=1 --json databaseId \
  --jq '.[0].databaseId')
```

---

## Related

- `git-cleanup-2026.md` — manual branch pruning and `git fetch --prune` policy
- `branch-strategies-2026.md` — branch lifecycle and naming conventions
- `github-actions-reusable-2026.md` — reusable workflow patterns
- `ci-cd-pipeline-2026.md` — CI permission model and `GITHUB_TOKEN` scopes

---

## Sources

- GitHub REST API: Delete a branch reference —
  `DELETE /repos/{owner}/{repo}/git/refs/heads/{branch}`
- `gh` CLI documentation: `gh api`, `gh issue create`, `gh workflow run`
- GitHub Actions: `schedule` trigger cron syntax
- GitHub branch protection API: `GET /repos/{owner}/{repo}/branches/{branch}/protection`
