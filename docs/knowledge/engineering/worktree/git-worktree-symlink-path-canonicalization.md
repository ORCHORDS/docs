# Git worktree path canonicalization and symlink controls

**Issue**

Automation that compares textual worktree paths can create duplicate intent, bypass allowlists, or clean the wrong location when symlinks and relative paths resolve to the same directory.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Resolve requested parent directories to canonical absolute paths before policy checks.
- Reject symlink components for privileged automation unless explicitly approved.
- Compare device/inode identity as well as normalized paths before create, move, or remove.
- Use Git's machine-readable worktree inventory as the authority and constrain paths to an approved root.

## Verification

1. Test relative paths, symlink aliases, case variants where applicable, and `..` traversal.
2. Attempt a time-of-check/time-of-use symlink swap in a disposable fixture.
3. Verify cleanup refuses a path whose identity changed.

## Gotchas

- String-prefix checks do not establish containment.
- Canonicalization alone does not prevent later symlink replacement.
- Filesystem case and mount semantics vary across runners.

## Official source

- [Official documentation](https://git-scm.com/docs/git-worktree)
