# Git replay ref-update boundaries

**Issue**

`git replay` can compute and emit reference update commands for rebased histories, separating commit replay from the decision to move refs.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin Git because replay remains evolving plumbing.
- Review emitted ref updates and expected old object IDs before applying them.
- Keep protected refs and shared worktree branches outside automatic updates.

## Verification

1. Replay merges, conflicts, empty commits, and multiple branches.
2. Apply updates with compare-and-swap expectations.
3. Verify reflogs and all linked worktrees afterward.

## Gotchas

- Replayed commits have new IDs.
- Generated updates are not authorization.
- Other worktrees may hold affected branches.

## Official source

- [Official documentation](https://git-scm.com/docs/git-replay)
