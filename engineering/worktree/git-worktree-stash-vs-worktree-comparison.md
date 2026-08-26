# Git Stash vs Git Worktree: Context-Switching Cost Analysis

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A developer is mid-feature and must handle an interruption: a hotfix, a code review, a quick spike. The two primary options are `git stash` and `git worktree add`. Picking the wrong tool costs time: stash is fragile under rebase and loses untracked files; worktrees have a setup cost that is wasteful for a 30-second context switch. This article provides a decision framework, cost comparison, and shell alias recipes.

## Context

- Git 2.15+
- Any project type
- Developer machines and CI pipelines
- Shell: bash or zsh

---

## Section 1: Decision Matrix

```
┌─────────────────────────────────┬──────────────────┬────────────────────┐
│ Scenario                        │ Use stash        │ Use worktree       │
├─────────────────────────────────┼──────────────────┼────────────────────┤
│ Fix < 5 minutes, same branch    │ ✓                │ overkill           │
│ Review a PR (read + run tests)  │ painful          │ ✓                  │
│ Hotfix on different branch      │ risky            │ ✓                  │
│ WIP preserved across reboots    │ ✓ (stash stays)  │ ✓ (worktree stays) │
│ Need separate editor window     │ ✗                │ ✓                  │
│ Independent node_modules / deps │ ✗                │ ✓                  │
│ Single-file quick edit          │ ✓                │ overkill           │
│ Long-running parallel task      │ ✗ (blocks branch)│ ✓                  │
│ Uncommitted work on same branch │ ✓                │ ✗ (different branch│
│                                 │                  │   only)            │
└─────────────────────────────────┴──────────────────┴────────────────────┘
```

---

## Section 2: `git stash` — Mechanics and Pitfalls

```bash
# Basic stash (tracks staged + unstaged; NOT untracked files)
git stash push -m "WIP: auth refactor step 3"

# Include untracked files
git stash push --include-untracked -m "WIP: new files included"

# Include ignored files too (rarely needed)
git stash push --all -m "WIP: everything"

# List stashes
git stash list
# stash@{0}: On feature/auth: WIP: auth refactor step 3
# stash@{1}: On main: WIP: quick spike

# Apply and drop (pop)
git stash pop

# Apply without dropping (safe when unsure)
git stash apply stash@{0}

# Drop a specific stash
git stash drop stash@{1}

# Show stash diff
git stash show -p stash@{0}

# Stash only staged changes
git stash push --staged -m "staged-only WIP"
```

**Stash failure modes:**

```bash
# DANGER: stash + rebase interaction
git stash push -m "WIP"
git rebase origin/main    # rebases move commits; stash refs do NOT update
git stash pop             # conflicts likely because base has moved

# DANGER: stash is per-repo, not per-branch — easy to pop onto wrong branch
git checkout other-branch
git stash pop             # applies feature/auth WIP onto other-branch!

# SAFER: always name stashes and check before popping
git stash list | head -5
git stash show stash@{0}
git stash pop stash@{0}
```

---

## Section 3: `git worktree` — Mechanics and Cost

```bash
# Setup cost: one-time per task
git fetch origin
git worktree add ../myrepo--hotfix-789 origin/main  # ~1-2 seconds

# From this point: full isolation
# - separate working directory
# - separate index (staging area)
# - separate HEAD
# - same object store (no disk duplication of git objects)

# Teardown
git worktree remove ../myrepo--hotfix-789   # ~0.1 seconds
git worktree prune
```

**Disk usage comparison:**

```bash
# Stash: zero extra disk space (stored in .git/refs/stash)
du -sh .git/refs/stash 2>/dev/null || echo "No stash"

# Worktree: working tree files only (git objects are shared)
# For a 50 MB repo with 20 MB of source files:
du -sh ../myrepo--hotfix-789      # ~20 MB (source) + node_modules if installed
du -sh .git/worktrees/            # ~4 KB (admin metadata only)
```

---

## Section 4: Shell Alias Recipes

```bash
# ~/.zshrc or ~/.bashrc

# ---- stash shortcuts ----
alias gs='git stash push --include-untracked'
alias gsp='git stash pop'
alias gsl='git stash list'
alias gss='git stash show -p stash@{0}'

# ---- worktree shortcuts ----

# wt-add <branch>: create sibling worktree for a remote branch
# Usage: wt-add feature/teammate-widget
wt-add() {
  local branch="$1"
  local repo_root
  repo_root=$(git rev-parse --show-toplevel)
  local repo_name
  repo_name=$(basename "$repo_root")
  local parent_dir
  parent_dir=$(dirname "$repo_root")
  local slug
  slug=$(echo "$branch" | tr '/' '-')
  local dest="${parent_dir}/${repo_name}--${slug}"

  git fetch origin
  git worktree add "$dest" "origin/$branch"
  echo "Worktree ready: $dest"
}

# wt-rm <branch>: remove a worktree by branch name (not path)
# Usage: wt-rm feature/teammate-widget
wt-rm() {
  local branch="$1"
  local repo_root
  repo_root=$(git rev-parse --show-toplevel)
  local repo_name
  repo_name=$(basename "$repo_root")
  local parent_dir
  parent_dir=$(dirname "$repo_root")
  local slug
  slug=$(echo "$branch" | tr '/' '-')
  local dest="${parent_dir}/${repo_name}--${slug}"

  git worktree remove "$dest"
  git worktree prune
  echo "Removed: $dest"
}

# wt-ls: formatted worktree list
wt-ls() {
  git worktree list --porcelain | awk '
    /^worktree/ { wt=$2 }
    /^branch/   { br=$2; gsub("refs/heads/","",br) }
    /^HEAD/     { sha=substr($2,1,7) }
    /^$/        { printf "%-50s %-30s %s\n", wt, br, sha }
  '
}

# wt-pr <pr-number>: open a PR for review in its own worktree
wt-pr() {
  local pr="$1"
  local branch
  branch=$(gh pr view "$pr" --json headRefName -q .headRefName)
  wt-add "$branch"
}
```

---

## Section 5: Multi-Task Development Pattern

```bash
# Typical developer day with worktrees
# Morning: main feature work
git checkout feature/auth-refactor
# ... hack hack hack ...

# Interruption 1: PR review needed
wt-pr #<number>                                    # creates worktree, fetches branch
code ../myrepo--feature-teammate-widget     # open in second editor
# ... review ...
wt-rm feature/teammate-widget

# Interruption 2: 2-minute hotfix on same branch (stash is fine here)
git stash push --include-untracked -m "WIP: auth step 3"
git commit --allow-empty -m "chore: trigger CI"
git stash pop

# Interruption 3: Long hotfix on release branch (worktree)
wt-add release/2.4
pushd ../myrepo--release-2.4
git cherry-pick abc1234
npm test
git push origin release/2.4
popd
wt-rm release/2.4

# End of day: stash remaining WIP cleanly
git stash push --include-untracked -m "WIP: auth refactor — end of 2026-08-24"
```

---

## Anti-patterns

- Do not use `git stash pop` without first running `git stash list` — you may apply the wrong stash entry onto the wrong branch.
- Do not rely on stash as long-term WIP storage during a rebase; create a WIP branch (`git checkout -b wip/auth-step-3`) instead.
- Do not create a worktree for a 30-second interruption on the same branch — the overhead is not worth it.
- Do not forget `--include-untracked` with stash when your WIP includes new files; the default stash silently ignores them.
- Do not accumulate more than ~5 stash entries — stash is a stack, not a shelf; use WIP branches for longer-lived saves.

## Gotchas

- `git stash pop` fails (without applying) if the pop would cause a conflict — it does NOT leave you in a half-applied state; but fixing the conflict manually and then popping again is confusing.
- Worktrees cannot check out a branch that is already checked out elsewhere (including your main tree). You must use `git worktree add -b local-copy origin/branch`.
- Stash entries survive `git branch -d` — they are not tied to any branch; they live in `.git/refs/stash`.
- `git worktree move` (Git 2.17+) lets you relocate a worktree without removing and re-adding it.

## Verification

```bash
# Verify stash includes untracked files
git stash push --include-untracked -m "test"
git stash show stash@{0} --stat
# should list new files

# Verify worktree isolation
git worktree add /tmp/test-wt origin/main
ls /tmp/test-wt
git worktree remove /tmp/test-wt
git worktree list  # should not show /tmp/test-wt
```

## Related

- `documentation/categories/worktree/git-worktree-code-review-parallel-checkout.md`
- `documentation/categories/worktree/git-worktree-release-branch-hotfix-parallel.md`
- `documentation/categories/worktree/git-worktree-ci-parallel-test-suites.md`

## Sources

- https://git-scm.com/docs/git-stash
- https://git-scm.com/docs/git-worktree
- https://git-scm.com/docs/git-worktree#_details
