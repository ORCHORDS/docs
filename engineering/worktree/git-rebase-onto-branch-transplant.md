# Git Rebase --onto Branch Transplant

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A feature branch was accidentally cut from `staging` instead of `main`, and all commits need to move to `main` without carrying along `staging`'s divergent history. Standard rebase fails because the common ancestor is wrong.

## Context
`git rebase --onto <newbase> <upstream> <branch>` replays commits in the range `(upstream, branch]` onto `newbase`. This differs from plain `git rebase <newbase>`, which replays everything since the branch diverged from newbase. The three-argument form lets you transplant an arbitrary commit range, making it the correct tool when branches were cut from the wrong base, when you want to extract a sub-range of commits, or when a dependent PR chain needs re-rooting after an upstream rebase.

## Understanding the Three Arguments
```
git rebase --onto <newbase> <upstream> [<branch>]
```
- `newbase` — where the transplanted commits will land
- `upstream` — the exclusive lower bound: commits reachable from upstream are excluded
- `branch` — the inclusive upper bound (defaults to HEAD)

The range `(upstream, branch]` is replayed on top of `newbase`.

```bash
# Visualise the situation before transplanting
git log --oneline --graph staging main feature/payment-ui

# Commits only on feature/payment-ui since it diverged from staging:
git log --oneline staging..feature/payment-ui
```

## Scenario 1: Wrong Base Branch
```bash
# feature/payment-ui was cut from staging; move it onto main
git rebase --onto main staging feature/payment-ui

# Verify the transplant: commits should now sit on top of main
git log --oneline --graph main feature/payment-ui
```

## Scenario 2: Extracting a Sub-range of Commits
```bash
# Only take the last 3 commits from a long-running branch
CUTOFF=$(git rev-parse feature/big-branch~3)

git rebase --onto main "$CUTOFF" feature/big-branch

# Or use a named commit reference
git rebase --onto main feature/big-branch~3 feature/big-branch
```

## Scenario 3: Re-rooting a Stacked PR Chain
```bash
# Stack: main <- base-pr <- child-pr
# base-pr was squash-merged; re-root child-pr onto main

OLD_TIP=$(git merge-base base-pr child-pr)
git rebase --onto main "$OLD_TIP" child-pr

# With rerere enabled, repeated conflict patterns resolve automatically
git config rerere.enabled true
```

## Scenario 4: CI Automation with --onto
```yaml
# .github/workflows/rebase-check.yml
name: Rebase onto main check

on:
  pull_request:
    branches: [main]

jobs:
  rebase-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Detect wrong base
        id: basecheck
        run: |
          MERGE_BASE=$(git merge-base origin/main HEAD)
          EXPECTED=$(git rev-parse origin/main)
          if [ "$MERGE_BASE" != "$EXPECTED" ]; then
            echo "rebased=false" >> "$GITHUB_OUTPUT"
          else
            echo "rebased=true" >> "$GITHUB_OUTPUT"
          fi

      - name: Dry-run rebase onto main
        if: steps.basecheck.outputs.rebased == 'false'
        run: |
          git config user.email "ci@example.com"
          git config user.name "CI"
          git rebase --onto origin/main "$(git merge-base origin/main HEAD)" HEAD
```

## TypeScript Helper for Commit Range Validation
```typescript
// scripts/check-rebase-range.ts
import { execSync } from "node:child_process";

function getCommitRange(upstream: string, branch = "HEAD"): string[] {
  const out = execSync(`git log --format=%H ${upstream}..${branch}`, {
    encoding: "utf8",
  });
  return out.trim().split("\n").filter(Boolean);
}

function wouldConflict(newbase: string, upstream: string): boolean {
  try {
    execSync(
      `git merge-tree $(git merge-base ${newbase} ${upstream}) ${newbase} ${upstream}`,
      { encoding: "utf8" }
    );
    return false;
  } catch {
    return true;
  }
}

const commits = getCommitRange("staging", "feature/payment-ui");
console.log(`Transplanting ${commits.length} commits onto main`);
const conflict = wouldConflict("main", "staging");
console.log(conflict ? "Potential conflicts detected" : "Clean transplant");
```

## Anti-patterns
- Running `git rebase main feature/payment-ui` when the branch was cut from `staging` — this replays all commits since `feature/payment-ui` diverged from `main`, likely including all of `staging`
- Transplanting commits that contain merge commits — `--onto` replays only linear history; merge commits produce unexpected results and require `--rebase-merges`
- Forgetting to `git push --force-with-lease` after transplant — the remote still points to the old base
- Using `--onto` without `rerere.enabled true` in a repeated-conflict scenario

## Gotchas
- Commit SHAs change after transplant; any open PRs pointing to the old SHAs need to be updated or re-opened
- If `upstream` is not an ancestor of `branch`, git exits with an error — use `git merge-base` to verify the range is valid
- `git rebase --onto` does not update tracking references; run `git branch -u origin/<branch>` afterwards if needed
- In a worktree setup, all worktrees share the ref namespace, so a transplanted branch is visible immediately in other worktrees without any extra fetch

## Verification
```bash
# Confirm no commits from staging appear in the transplanted branch
git log --oneline main..feature/payment-ui | wc -l   # should equal original commit count
git log --oneline staging..feature/payment-ui | wc -l # should equal same count

# Ensure the new merge-base is main
git merge-base main feature/payment-ui | xargs git log -1 --format="%H %s"

# Run the project test suite against the transplanted branch
pnpm test
```

## Related
- `/documentation/categories/worktree/git-rebase-interactive.md`
- `/documentation/categories/worktree/git-rebase-vs-merge-2026.md`
- `/documentation/categories/worktree/git-rerere.md`
- `/documentation/categories/worktree/stacked-prs-workflow-2026.md`
- `/documentation/categories/worktree/cherry-pick-revert-bisect.md`

## Sources
- https://git-scm.com/docs/git-rebase#Documentation/git-rebase.txt---onto-ltnewbasegt
- https://git-scm.com/book/en/v2/Git-Branching-Rebasing
- https://andrewlock.net/working-with-stacked-prs-and-git-rebase-onto/
