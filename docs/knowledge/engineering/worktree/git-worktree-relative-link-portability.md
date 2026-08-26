# Git worktree relative-link portability

**Issue:** Absolute worktree links break when a repository bundle is moved between machines or mount points.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use `worktree.useRelativePaths=true` or `--relative-paths` only after confirming every supported Git version understands `extensions.relativeWorktrees`. Move the common repository and linked worktrees as one topology; do not assume relative links make independently moved directories valid. Record the required directory relationship in automation and use Git commands to inspect paths rather than parsing administrative files.

## Verification

Copy a disposable multi-worktree layout to a different absolute root and verify status, commits, and removal. Test the oldest client, mixed absolute/relative repair, symlinked parents, and rollback to absolute links.

## Gotchas

- Pin and test the exact supported version; defaults and feature states can change.
- Preserve reproducible evidence without storing secrets or personal data.
- Define rollback before production rollout.

## Official source

- [Primary documentation](https://git-scm.com/docs/git-worktree)
