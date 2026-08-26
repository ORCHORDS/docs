# Git Stash — Workflow Management and Recovery Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

You are mid-feature when a production bug comes in. Your working
directory has 15 modified files that are not ready to commit. You run
`git stash` with no message, switch to the hotfix branch, fix the bug,
then return to find three unnamed stashes (`stash@{0}`, `stash@{1}`,
`stash@{2}`) with no indication of which contains your feature work.
You apply the wrong stash, get merge conflicts, and lose track of your
changes.

## Context

`git stash` temporarily shelves uncommitted changes (both staged and
unstaged) so you can work on something else, then re-apply them later.
A stash is stored as a commit object in `.git/refs/stash` with a
reflog for history. In 2026, stash remains the quickest context-switch
tool for short interruptions (minutes to hours). For longer parallel
work (hours to days), git worktrees are preferred because they maintain
a full working directory per branch. The key best practice is to always
use descriptive messages (`git stash push -m "description"`) and to
treat stashes as temporary — if work will be stashed for more than a
few hours, commit it on a WIP branch instead.

## Core commands

```bash
# Stash with descriptive message (always do this)
git stash push -m "WIP: payment form validation"

# Stash only staged changes
git stash push --staged -m "ready: new API endpoint"

# Stash including untracked files
git stash push -u -m "WIP: includes new test files"

# Stash including untracked AND ignored files
git stash push -a -m "WIP: includes build artifacts"

# Stash specific files only
git stash push -m "WIP: just the model changes" src/models/

# List all stashes
git stash list
# stash@{0}: On feature/payments: WIP: payment form validation
# stash@{1}: On main: hotfix: disable rate limit temporarily

# Show stash contents (diff)
git stash show -p stash@{0}

# Apply most recent stash (keep in stash list)
git stash apply

# Apply specific stash
git stash apply stash@{1}

# Apply and remove from stash list
git stash pop

# Drop a specific stash
git stash drop stash@{1}

# Clear all stashes (DANGER)
git stash clear
```

## Workflow patterns

```
Quick context switch (minutes):
  1. git stash push -m "WIP: feature X"
  2. Switch branch, fix urgent issue #<number>. Switch back
  4. git stash pop

Partial stash (stage what's ready):
  1. git add <files-ready-for-stash>
  2. git stash push --staged -m "ready: part A"
  3. Continue working on remaining files

Branch-aware stash:
  1. git stash push -m "WIP: feature X on payments-branch"
  2. git checkout hotfix-branch
  3. Fix and commit
  4. git checkout payments-branch
  5. git stash pop

Stash as temporary backup:
  1. git stash push -m "backup before risky refactor"
  2. Attempt refactor
  3. If refactor fails: git stash pop
  4. If refactor succeeds: git stash drop stash@{0}
```

## Stash vs alternatives

```
                  Stash           WIP Commit        Worktree
Duration:         Minutes-hours   Hours-days         Days-weeks
Visibility:       Local only      In git log         Full branch
Collaboration:    No              Push to share      Full workflow
Multiple tasks:   Awkward         Natural            Ideal
Recovery:         Limited         Full git history   Full
Best for:         Quick pause     Save progress      Parallel work

Decision tree:
  Interruption < 2 hours → git stash
  Interruption > 2 hours → git commit -m "WIP: ..."
  Parallel long-running work → git worktree
```

## Recovery

```bash
# Recover accidentally dropped stash
# Stashes are commit objects — recoverable until garbage collected

# Find lost stash commits
git fsck --unreachable | grep commit
# or
git log --graph --oneline --all $(git fsck --no-reflogs 2>/dev/null \
  | grep "dangling commit" | cut -d' ' -f3)

# Inspect a found commit
git show <commit-hash>

# Re-apply a found stash commit
git stash apply <commit-hash>

# Recovery window:
# Active repos: hours to days (before gc runs)
# Quiet repos: weeks to months
# After git gc --prune=now: unrecoverable
```

## Anti-patterns

- **Unnamed stashes** — using `git stash` without `-m`. Multiple
  unnamed stashes are impossible to distinguish without inspecting
  each one. Always use descriptive messages.
- **Long-lived stashes** — keeping stashes for days or weeks. Stashes
  are meant for short-term storage. For anything longer, create a
  WIP commit on a branch. Stashes accumulate merge conflict risk
  as the codebase evolves.
- **Stash as version control** — using stashes to save multiple
  versions of work instead of commits. Stashes are a stack, not a
  history. Use branches and commits for version tracking.
- **Stash clear without checking** — running `git stash clear`
  without reviewing the stash list. This permanently deletes all
  stashes (until gc runs). Always `git stash list` before clearing.

## Gotchas

- **Stash applies to current branch** — `git stash pop` applies
  changes to whatever branch you are currently on, not necessarily
  the branch where you created the stash. This can cause unexpected
  conflicts if the branches have diverged.
- **Untracked files not stashed by default** — `git stash push`
  only stashes tracked files. New files (untracked) require the
  `-u` flag. Forgetting `-u` leaves new files in the working
  directory, which may cause confusion.
- **Merge conflicts on pop** — if the codebase changed since the
  stash was created, `git stash pop` may produce merge conflicts.
  Unlike `apply`, a failed `pop` does NOT drop the stash, so you
  can resolve conflicts and the stash is still available.
- **Stash index** — stash indices shift when entries are dropped.
  If you drop `stash@{1}`, what was `stash@{2}` becomes
  `stash@{1}`. Reference stashes by message or hash for clarity.

## Verification

- All stashes have descriptive messages (enforced via team convention).
- Stash list is reviewed and cleaned weekly.
- No stashes older than 1 week (converted to WIP commits).
- Team knows recovery procedures for accidentally dropped stashes.
- Untracked files are included when needed (`-u` flag).

## Related

- `documentation/categories/worktree/git-worktree-monorepo-parallel-ai-agents.md`
- `documentation/categories/worktree/git-workflow-best-practices.md`
- `documentation/categories/worktree/rebase-vs-merge-strategy.md`

## Source URLs (verified 2026-08-16)

- Git Working with Stash: Practical 2026 Playbook — https://thelinuxcode.com/git-working-with-stash-practical-2026-playbook/
- How to Manage Git Stash Workflow — https://labex.io/tutorials/git-how-to-manage-git-stash-workflow-418099
- Engineering Effective Stashing & Git Submodule Workflows — https://namastedev.com/blog/engineering-effective-stashing-git-submodule-workflows/
- Git Workflow Best Practices: Developer's Guide for 2026 — https://dev.to/_d7eb1c1703182e3ce1782/git-workflow-best-practices-the-developers-guide-for-2026-4gl0
