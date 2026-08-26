# squash-merge-default

**Issue:** Squash-merge by default + how to enforce it
**Date:** 2026-08-09
**Status:** documented

## Symptom
You merge a PR with 5 commits. The 5 commits land on main. The
history is cluttered. Half the commits are "fix typo", "address
review", "fix typo again." Hard to revert. Hard to bisect.

## Root cause
A PR is a logical unit of work. A single commit on main is a
logical unit. They don't have to be the same size. Squash-merge
collapses the PR's N commits into 1 commit on main.

**Source:** GH docs — squash merging:
https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/about-pull-request-merges

> "Squash merging ... combines all the commits in the pull
> request into a single commit."

## Fix
Configure squash-merge as the default in the repo:

### GH repo settings
Settings → General → Pull Requests → "Allow squash merging" ✅
→ Default: "Squash" → Default commit message: "Pull request
title and description"

### Branch protection
Settings → Branches → main → "Require pull request reviews
before merging" → ✅ + "Require status checks to pass"

### The squash-merge workflow
1. Author opens PR (N commits)
2. Reviewer reviews, requests changes
3. Author addresses, pushes more commits
4. Reviewer approves
5. Author clicks "Squash and merge"
6. GitHub creates 1 commit on main with the PR title + description
7. Branch is auto-deleted

The PR title becomes the commit message. The PR description
becomes the extended description (visible in `git log`).

## When NOT to squash-merge

Some commits are worth keeping as separate history:
- **Reverts:** A "revert: PR #<number>" commit is meaningful on its own
- **Cherry-picks:** A commit landed on main, was reverted, then
  cherry-picked back. The history tells the story.
- **Large refactors:** A 50-commit refactor benefits from a
  linear history to track what changed.
- **Release branches:** A release branch may merge into main
  with --no-ff to preserve the "release v1.2" marker.

For these, use **merge commit** instead of squash.

### The three options
1. **Merge commit** (`--no-ff`): preserves history, creates a
   merge commit
2. **Squash** (`--squash`): collapses to 1 commit (default
   recommended)
3. **Rebase** (`--rebase`): linear history, no merge commit
   (each commit is the same as the PR commit)

For most teams, **squash is the default** + **merge commit for
releases/refactors**.

## Verification
- **Test:** PR with 5 commits → merge → main has +1 commit
- **Live:** `git log --oneline -10` is clean
- **Audit:** Repo settings enforce squash + branch protection

## Gotchas
- **`git bisect` works better with squashed commits.** Each commit
  is a logical unit. Bisecting a 5-commit PR with 1 bad commit
  finds it in 1 step.
- **The "fix typo" commits are lost on squash.** That's the
  point — they're noise.
- **For monorepos with multiple packages,** squash-merge loses
  the per-package commit detail. Some teams use a bot to
  split the PR into per-package commits automatically.
- **The squash commit author defaults to the merger** (not the
  PR author). To preserve the PR author, enable "Co-authored-by"
  in the commit message (GH does this by default).
- **The PR description becomes the commit body.** If the
  description has a 24-point compliance audit table, that
  table is preserved in the commit body (visible in
  `git log`).
- **Auto-merge via the API uses the repo's default merge
  strategy.** If you want a specific strategy, pass
  `merge_method` explicitly.

## Related
- `rebase-vs-merge.md`
- `worktree/gitlinks-trap.md`
- GH squash: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/about-pull-request-merges
