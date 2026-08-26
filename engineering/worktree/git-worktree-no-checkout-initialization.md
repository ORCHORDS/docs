# Git worktree no-checkout initialization

**Issue:** A normal worktree checkout can materialize a huge tree or run into platform-specific files before sparse or custom checkout policy is configured.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use `git worktree add --no-checkout` to create administrative state without populating files, then configure the intended sparse-checkout or other checkout controls inside that worktree before the first checkout. Validate the target ref and clean destination first. Keep hooks and bootstrap scripts explicit; no-checkout does not mean the location is outside repository policy.

## Verification

Measure that no tracked files are populated initially, apply cone and non-cone sparse patterns, then verify index and working tree consistency. Test interruption between add and checkout and ensure cleanup leaves no orphaned worktree metadata.

## Gotchas

- Pin and test the exact supported version; defaults and feature states can change.
- Preserve reproducible evidence without storing secrets or personal data.
- Define rollback before production rollout.

## Official source

- [Primary documentation](https://git-scm.com/docs/git-worktree)
