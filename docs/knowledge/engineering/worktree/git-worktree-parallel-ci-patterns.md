# Git Worktree Parallel Development and CI Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your developers constantly stash or commit half-finished work to switch
branches for code reviews, hotfixes, or experiments. CI pipelines cannot
run multiple branches in parallel within a single checkout. AI coding
agents need isolated working directories but cloning the full repository
for each agent is slow and wastes disk space. Switching between long-
running feature branches and the main branch requires rebuilding
node_modules or recompiling from scratch.

## Context

Git worktrees allow multiple working directories to share a single
`.git` directory, each checked out to a different branch. This avoids
full clones while maintaining complete branch isolation. In 2026,
worktrees are gaining adoption for two primary use cases: (1) AI agent
isolation — giving each coding agent its own worktree so they can modify
files in parallel without conflicts, and (2) parallel CI — running
builds for multiple branches simultaneously without multiple clones.
Teams report up to 63% reduction in CI pipeline time when using parallel
worktrees instead of sequential branch checkouts.

## Core commands

```bash
# Create a worktree for an existing branch
git worktree add ../project-feature feature-branch

# Create a worktree with a new branch
git worktree add -b hotfix-123 ../project-hotfix main

# List all worktrees
git worktree list

# Remove a worktree (after merging/deleting the branch)
git worktree remove ../project-feature

# Prune stale worktree references
git worktree prune
```

### Key constraint

Each branch can only be checked out in one worktree at a time. Attempting
to check out the same branch in two worktrees fails. Use `git worktree
add -b new-branch` to create a new branch if you need multiple worktrees
based on the same starting point.

## Developer workflow patterns

### Parallel branch work

```
~/project/           (main worktree — main branch)
~/project-review/    (worktree — colleague's PR branch)
~/project-hotfix/    (worktree — production hotfix)
~/project-experiment/(worktree — experimental feature)
```

Each directory has its own working tree, index, and HEAD, but they share
the object store. Changes in one worktree do not affect others. Each
can have its own running dev server on different ports.

### Code review without context switching

```bash
# Reviewer creates a worktree for the PR branch
git fetch origin pull/42/head:pr-42
git worktree add ../review-pr-42 pr-42

# Review, test, then clean up
cd ../review-pr-42
npm install && npm test
cd ../project
git worktree remove ../review-pr-42
```

### Hotfix while feature work continues

```bash
# Currently working on feature-x in main worktree
# Production issue reported — create hotfix worktree
git worktree add -b hotfix-urgent ../hotfix main

cd ../hotfix
# Fix the issue, test, commit, push
git push origin hotfix-urgent

# Return to feature work — no stash, no context loss
cd ../project
```

## AI agent isolation

Multiple AI coding agents working on the same repository need isolated
file systems to avoid write conflicts. Worktrees provide this without
full clones:

```bash
# Orchestrator creates one worktree per agent
git worktree add -b agent-1-task ../agent-1 main
git worktree add -b agent-2-task ../agent-2 main
git worktree add -b agent-3-task ../agent-3 main

# Each agent operates in its own directory
# Agent 1 modifies src/auth.ts in ../agent-1/
# Agent 2 modifies src/api.ts in ../agent-2/
# No conflicts — different working trees

# After agents complete, merge results
git merge agent-1-task
git merge agent-2-task
git merge agent-3-task
```

### Worktree cleanup automation

```bash
#!/bin/bash
# Clean up worktrees for merged branches
for wt in $(git worktree list --porcelain | grep 'worktree ' | awk '{print $2}'); do
  branch=$(git -C "$wt" branch --show-current 2>/dev/null)
  if [ -n "$branch" ] && git branch --merged main | grep -q "$branch"; then
    echo "Removing merged worktree: $wt ($branch)"
    git worktree remove "$wt"
  fi
done
git worktree prune
```

## CI pipeline patterns

### Parallel branch builds

```yaml
# GitHub Actions — build multiple branches in parallel using worktrees
jobs:
  parallel-build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        branch: [feature-a, feature-b, feature-c]
    steps:
      - uses: actions/checkout@v4
      - name: Create worktree
        run: |
          git fetch origin ${{ matrix.branch }}
          git worktree add ../${{ matrix.branch }} origin/${{ matrix.branch }}
      - name: Build in worktree
        working-directory: ../${{ matrix.branch }}
        run: npm ci && npm run build
```

### Shared dependency cache

Because worktrees share the `.git` directory, they can also share a
dependency cache:

```bash
# Install once, symlink to worktrees
npm ci --prefix ~/project
ln -s ~/project/node_modules ~/project-feature/node_modules
```

Caution: this only works if both branches use the same dependency
versions. Different lock files require separate installs.

## Anti-patterns

- **Too many active worktrees** — accumulating worktrees without
  cleaning up. Each worktree is a full working directory on disk. Prune
  regularly with `git worktree prune` and remove worktrees when the
  branch is merged.
- **Shared node_modules across incompatible branches** — symlinking
  dependencies between worktrees with different lock files causes
  mysterious build failures. Install independently when dependencies
  differ.
- **Worktrees on network drives** — git worktree performance degrades
  significantly on network file systems (NFS, SMB). Use local storage.
- **Forgetting worktree-specific gitignore** — build artifacts in one
  worktree can bleed into another if paths are not correctly isolated.

## Gotchas

- **Branch locking** — a branch checked out in any worktree cannot be
  checked out elsewhere or deleted. Use `git worktree list` to find
  which worktree holds a branch.
- **Submodule support** — submodules require separate initialization in
  each worktree. Run `git submodule update --init` in each new worktree.
- **IDE support** — most IDEs treat each worktree as a separate project.
  Open each worktree directory independently. Some IDEs (JetBrains) have
  native multi-worktree support.
- **Disk space** — while worktrees share the object store, each has its
  own working copy of all files. Large repositories with many worktrees
  multiply disk usage for tracked files.

## Verification

- Developers can review PRs without stashing or committing in-progress
  work.
- CI pipeline runs parallel branch builds using worktrees.
- Worktree cleanup is automated (merged branches are removed).
- AI agent workflows use worktrees for file-system isolation.
- No branch-locking issues reported from worktree conflicts.

## Related

- `documentation/docs/policies/worktree/monorepo-versioning-independent-releases.md`
- `documentation/docs/policies/worktree/incident-communication-runbook-templates.md`
- `documentation/docs/policies/infra/ci-cd-pipeline-design.md`

## Source URLs (verified 2026-08-16)

- Git worktree documentation — https://git-scm.com/docs/git-worktree
- Git worktree tutorial — https://www.gitkraken.com/learn/git/git-worktree
- Worktrees for parallel development — https://morgan.cugerone.com/blog/how-to-use-git-worktree-and-in-a-clean-way/
- Worktree CI patterns — https://dev.to/yankee/practical-guide-to-git-worktree-58o0
