# Git detached-worktree experiment handoff

**Issue:** Commits created in a detached worktree can become unreachable when the worktree is removed without an explicit handoff.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use `git worktree add --detach` for disposable builds or experiments only. Before removal, detect commits not reachable from approved refs and require an explicit outcome: create a named branch, tag an artifact commit, or discard after recording object IDs and expiry. Do not auto-push detached commits. Keep generated artifacts outside Git or attach them through the normal release process.

## Verification

Create commits in a detached worktree, verify the pre-removal gate detects them, test branch handoff and intentional discard, then run reflog-expiry and garbage-collection drills.

## Gotchas

- Detached commits are valid but not protected by a branch.
- Reflogs are temporary recovery aids.
- Submodules may have separate detached state.

## Official source

- [Git worktree documentation](https://git-scm.com/docs/git-worktree)
