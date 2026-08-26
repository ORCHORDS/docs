# git-worktree-best-practices

**Issue:** Git worktree — multiple branches, hotfix workflow
**Date:** 2026-08-09
**Status:** documented

## Symptom
You're on a feature branch. A critical hotfix is
needed on main. You `git stash`, `git checkout main`,
fix, push, `git checkout feature`, `git stash pop`.
You lose context. You have merge conflicts. You wish
you could be in two places at once.

## Root cause
**One working tree = one branch.** Use `git worktree`.

**Source:** Git docs.

## The "worktree" concept

A worktree is an additional working directory linked
to the same `.git`:
- **Multiple branches:** Simultaneously
- **Shared object store:** One .git, many trees
- **No stashing:** Independent state
- **Each can build/test:** Separately

The worktrees share the repo.

## The "create" pattern

For a new worktree:
```bash
# Add a worktree for an existing branch
git worktree add ../project-hotfix hotfix/login-bug

# Add a worktree with a new branch
git worktree add -b feature/new-auth ../project-auth main

# Detached HEAD at a commit
git worktree add --detach ../project-review abc123
```

The worktree is created.

## The "list" pattern

For listing:
```bash
git worktree list
# /path/to/project         abc123 [main]
# /path/to/project  def456 [hotfix/login-bug]
# /path/to/project    ghi789 [feature/new-auth]
```

The worktrees are listed.

## The "remove" pattern

For removal:
```bash
# Clean worktree
git worktree remove ../project-hotfix

# Force (uncommitted changes)
git worktree remove --force ../project-hotfix

# Manual + prune
rm -rf ../project-hotfix
git worktree prune
```

The worktree is removed.

## The "lock" pattern

For protection:
```bash
# Lock a worktree
git worktree lock ../project-release --reason "Release in progress"

# Check lock status
git worktree list --porcelain

# Unlock
git worktree unlock ../project-release
```

The worktree is protected.

## The "directory structure" pattern

For organization:
```
~/projects/
myproject/              # Primary worktree (main)
myproject-feature-auth/  # Feature worktree
myproject-hotfix/        # Hotfix worktree
```

The structure is consistent.

## The "bare + linked" pattern

For a multi-worktree setup:
```bash
# Clone as bare
git clone --bare [email protected]:user/myproject.git myproject.git

# Create linked worktrees
cd myproject.git
git worktree add ../myproject-main main
git worktree add ../myproject-develop develop
```

The bare + linked is clean.

## The "agent integration" pattern

For AI agents, worktrees are perfect:
```bash
# Claude Code
claude --worktree <name>  # or: claude -w <name>

# GitHub Copilot CLI in VS Code
# Pick "Worktree isolation" when creating a session
```

The agent works in isolation.

## The "shared stash" anti-pattern

Stash is global to the repo:
```bash
# Stash in one worktree
cd ../project-feature
git stash

# Visible from another
cd ../project-hotfix
git stash list
# Shows the same stash
```

**Issue:** Stash is shared.

**Workaround:** Use branches instead of stash.

## The "shared node_modules" anti-pattern

`node_modules` is per-worktree:
```bash
# Install in one worktree
cd ../project-feature
npm install

# Not installed in another
cd ../project-hotfix
ls node_modules  # Doesn't exist
```

**Issue:** Each worktree needs its own install.

**Workaround:** Use `pnpm` with a content-addressable store.

## The "shared git" anti-pattern

`git fetch` updates all worktrees:
```bash
# Fetch in one
cd ../project-feature
git fetch

# All other worktrees see the new refs
cd ../project-hotfix
git log origin/main
```

This is usually fine.

## The "branch conflict" anti-pattern

Same branch, two worktrees:
```bash
# Both can't have main
git worktree add ../project-main main
# fatal: 'main' is already checked out
```

**Fix:** Use a different branch per worktree.

## The "use cases" pattern

For worktree use cases:
- **Hotfix:** Different branch
- **Code review:** Detached HEAD
- **Multiple features:** Parallel
- **CI/agent isolation:** Per branch
- **Version comparison:** Detached at tags

The use case drives the setup.

## The "VS Code multi-worktree" pattern

For VS Code:
1. **Add worktrees:** `git worktree add ...`
2. **Open each:** `code ../project-feature`
3. **Or add to workspace:** Multi-root

The IDE works with each.

## The "performance" pattern

For performance:
- **No checkout:** `git worktree add --no-checkout`
- **Sparse checkout:** For large repos
- **Bare + linked:** Best for many

The right setup for the size.

## The "cleanup" pattern

For cleanup:
```bash
# Prune stale references
git worktree prune

# Repair corrupted references
git worktree repair

# Lock to prevent accidental remove
git worktree lock
```

The worktrees are maintained.

## The "worktree anti-pattern" anti-patterns

### 1. Same branch twice
- **Issue:** Refuses
- **Fix:** Use different branches

### 2. No prune
- **Issue:** Stale references
- **Fix:** `git worktree prune` regularly

### 3. No lock on prod
- **Issue:** Accidental remove
- **Fix:** `git worktree lock`

### 4. Stash for context switching
- **Issue:** Stash is global
- **Fix:** Use a worktree

## Verification
- **Test:** Worktree creates
- **Test:** Branch can be checked out in multiple
- **Test:** Worktree can be removed
- **Test:** Lock prevents remove
- **Audit:** Quarterly prune

## Gotchas
- **The "same branch twice" anti-pattern.** Different
  branches.
- **The "shared stash" anti-pattern.** Use branches.
- **The "shared node_modules" anti-pattern.** Use pnpm.

## Related
- `worktree/gitlinks-trap.md`
- `worktree/rebase-vs-merge.md`
- `worktree/squash-merge-default.md`
- Git docs: https://git-scm.com/docs/git-worktree
- OneUptime guide: https://oneuptime.com/blog/post/2026-01-24-git-worktrees/
- iuriio guide: https://www.iuriio.com/blog/posts/2026/07/git-worktrees-guide
