# Git Worktree — Monorepo Parallel Development and AI Agent Isolation

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

You are working on a feature branch and need to urgently fix a
production bug, but switching branches means stashing uncommitted work,
reinstalling dependencies, and rebuilding from scratch. In a monorepo,
this takes 5-10 minutes each way. You run multiple AI coding agents
(Claude Code, Copilot, Codex) but they conflict when operating on the
same worktree simultaneously — file writes collide, build artifacts
interfere, and test runs produce unreliable results. You want parallel
development across multiple branches without the overhead of multiple
clones.

## Context

`git worktree` creates additional working trees linked to the same
repository. Each worktree checks out a different branch but shares the
same `.git` object database — no cloning required, and the worktree is
created in under a second even for multi-gigabyte repositories. In 2026,
git worktrees have become the standard pattern for running parallel AI
coding agents, with JetBrains IDEs (2026.1+), VS Code (2025+), and
Claude Code all supporting worktree-based workflows. Teams using
worktrees with AI agents report 2-3x throughput improvement because
agents never idle waiting for branch switches.

## Basic usage

```bash
# Create a worktree for a hotfix branch
git worktree add ../hotfix-payment hotfix/payment-bug

# Create a worktree with a new branch
git worktree add ../feature-search -b feature/search-redesign

# List all worktrees
git worktree list
# /path/to/project          abc1234 [main]
# /path/to/project def5678 [hotfix/payment-bug]
# /path/to/project 789abcd [feature/search-redesign]

# Remove a worktree when done
git worktree remove ../hotfix-payment

# Prune stale worktrees (deleted directories)
git worktree prune
```

## Monorepo patterns

### Sparse checkout + worktree

```bash
# Create worktree with only the packages you need
git worktree add ../agent-frontend -b feature/new-header

cd ../agent-frontend
git sparse-checkout init --cone
git sparse-checkout set packages/web packages/ui-lib packages/shared

# Worktree contains only:
#   packages/web/
#   packages/ui-lib/
#   packages/shared/
# Not the full monorepo — saves disk and reduces file watcher load
```

### Per-package development

```bash
# Agent 1: working on the API
git worktree add ../work-api -b feature/api-v2
cd ../work-api && pnpm install --filter @org/api...

# Agent 2: working on the frontend
git worktree add ../work-web -b feature/web-redesign
cd ../work-web && pnpm install --filter @org/web...

# Agent 3: working on shared library
git worktree add ../work-shared -b feature/shared-types
cd ../work-shared && pnpm install --filter @org/shared...

# Each agent operates independently — no file conflicts
```

## AI agent isolation pattern

```
Problem: two AI agents editing the same repo

Agent A writes src/api.ts ←── conflict ──→ Agent B writes src/api.ts

Solution: each agent gets its own worktree

git worktree add ../agent-a -b agent/feature-a
git worktree add ../agent-b -b agent/feature-b

Agent A works in ../agent-a/    (branch: agent/feature-a)
Agent B works in ../agent-b/    (branch: agent/feature-b)

No file conflicts. Independent builds. Independent tests.
Merge results via PRs when both agents complete.
```

### Setup script

```bash
#!/bin/bash
# create-agent-worktree.sh — create an isolated worktree for an AI agent

BRANCH_NAME="${1:?Usage: $0 <branch-name>}"
WORKTREE_DIR="../worktrees/$BRANCH_NAME"

# Create worktree
git worktree add "$WORKTREE_DIR" -b "$BRANCH_NAME" 2>/dev/null \
  || git worktree add "$WORKTREE_DIR" "$BRANCH_NAME"

cd "$WORKTREE_DIR"

# Install dependencies (monorepo-aware)
if [ -f pnpm-lock.yaml ]; then
  pnpm install --frozen-lockfile
elif [ -f package-lock.json ]; then
  npm ci
fi

echo "Worktree ready at $WORKTREE_DIR on branch $BRANCH_NAME"
```

## Disk and performance considerations

```
Shared across worktrees (no duplication):
  → .git/objects (commits, blobs, trees)
  → .git/packed-refs
  → .git/hooks
  → Total: the bulk of repository storage

Duplicated per worktree:
  → Working tree files (full checkout)
  → node_modules / vendor / venv (per worktree)
  → Build artifacts (dist/, .next/, target/)
  → .git/worktrees/<name>/ (HEAD, index, refs)

Disk usage example (2 GB repo):
  → Main worktree: 2 GB (full repo)
  → Additional worktree: ~2 GB (working files only, objects shared)
  → With sparse checkout: ~200 MB (subset of working files)

Performance:
  → Worktree creation: <1 second (hardlinks, no copy)
  → Branch checkout: same as normal git checkout
  → File watchers: multiply per worktree (IDE, build tools)
  → Recommendation: limit to 3-5 active worktrees
```

## CI integration

```yaml
# GitHub Actions: parallel testing across worktrees
name: Parallel Agent Testing
on: pull_request

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        package: [api, web, shared]
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Create package worktree
        run: |
          git worktree add ../test-${{ matrix.package }} HEAD
          cd ../test-${{ matrix.package }}
          git sparse-checkout init --cone
          git sparse-checkout set packages/${{ matrix.package }} packages/shared

      - name: Install and test
        working-directory: ../test-${{ matrix.package }}
        run: |
          pnpm install --filter @org/${{ matrix.package }}...
          pnpm --filter @org/${{ matrix.package }} test
```

## Anti-patterns

- **Too many worktrees** — creating 10+ worktrees with full
  `node_modules` in each. Disk usage multiplies (each worktree gets
  its own dependencies), file watchers compete for system resources,
  and IDE performance degrades. Limit active worktrees to 3-5.
- **Worktrees as long-lived clones** — using worktrees as permanent
  development directories. Worktrees are meant for temporary parallel
  work. Remove them when the branch is merged. Stale worktrees
  accumulate disk usage and confuse `git worktree list`.
- **Forgetting to prune** — deleting a worktree directory without
  `git worktree remove`. The repository still references the deleted
  worktree, preventing the branch from being checked out elsewhere.
  Use `git worktree prune` to clean up.
- **Shared state between worktrees** — storing state in the repo
  root that worktrees reference (e.g., a shared `.env` file via
  symlink). Each worktree should be fully self-contained; shared
  state creates hidden dependencies.

## Gotchas

- **Cannot check out the same branch twice** — git prevents two
  worktrees from checking out the same branch (to avoid conflicting
  index states). Create a new branch for each worktree, or use
  `--detach` for read-only inspection.
- **Submodule initialization** — submodules are not automatically
  initialized in new worktrees. Run `git submodule update --init`
  in each worktree that needs submodule content.
- **IDE file watchers** — each worktree triggers independent file
  watchers in your IDE. With 3 worktrees, you have 3x the inotify
  watches. On Linux, increase `fs.inotify.max_user_watches` if you
  hit the limit.
- **Git hooks are shared** — hooks in `.git/hooks/` apply to all
  worktrees. A pre-commit hook that assumes a specific directory
  structure may fail in worktrees with sparse checkout.

## Verification

- AI agents use separate worktrees for parallel development.
- Sparse checkout reduces worktree size in monorepos.
- Worktrees are removed after branches are merged.
- Active worktree count is limited to 3-5 per developer.
- CI uses worktrees for isolated parallel package testing.
- `git worktree prune` runs periodically to clean stale entries.

## Related

- `documentation/docs/policies/worktree/git-bisect-automated-regression-finding.md`
- `documentation/docs/policies/worktree/git-hooks-pre-commit-frameworks.md`
- `documentation/docs/policies/worktree/git-worktree-parallel-ci-patterns.md`

## Source URLs (verified 2026-08-16)

- Git Worktrees: Run Multiple AI Agents on Different Branches — https://medium.com/@jatin4228/git-worktrees-run-multiple-ai-agents-copilot-claude-code-on-different-branches-at-once-ba46cd8e0ae7
- Git Worktrees for Parallel Development: 3x Throughput with AI Agents — https://understandingdata.com/posts/git-worktrees-parallel-dev/
- Scaling Git: Monorepos, LFS, Sparse Checkout and Worktrees 2026 — https://mdsanwarhossain.me/blog-git-monorepo-lfs-submodules-sparse-checkout.html
- Git Worktree Isolation Patterns for Parallel AI Agent Development — https://zylos.ai/research/2026-02-22-git-worktree-parallel-ai-development/
