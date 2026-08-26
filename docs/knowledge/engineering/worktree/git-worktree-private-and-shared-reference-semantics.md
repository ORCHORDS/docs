# Git worktree-private and shared reference semantics

**Issue:** Automation that treats every Git reference as repository-global can read or mutate the wrong state when multiple worktrees run bisects, rebases, or other operations concurrently.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Treat `HEAD` and operation-specific pseudorefs such as bisect state as worktree-private, while ordinary branch refs remain shared. Use Git plumbing commands instead of constructing paths below `.git`. Resolve administrative locations through `git rev-parse --git-path`, and address another worktree's private refs only through the documented `worktrees/<name>/...` namespace when a reviewed tool truly needs it. Give each automation worker its own branch.

## Verification

Start independent bisects in two disposable linked trees and verify their private state does not cross. Update a normal branch ref in one tree and confirm the shared ref is visible in the other. Run tooling from both the main and linked worktrees to catch assumptions that `.git` is always a directory.

## Gotchas

Refs under `refs/` are generally shared except documented per-worktree namespaces. Direct filesystem access is brittle with reftable, linked worktrees, and future storage changes; use Git commands.

## Official sources

- https://git-scm.com/docs/git-worktree
- https://git-scm.com/docs/gitrepository-layout
- https://git-scm.com/docs/git-rev-parse
