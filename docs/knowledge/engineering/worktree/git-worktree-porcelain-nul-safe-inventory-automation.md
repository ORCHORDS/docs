# Git worktree porcelain and NUL-safe inventory automation

**Issue:** Scripts that parse human-oriented worktree output can break on whitespace, localization, new annotations, or unusual path characters and then clean up the wrong tree.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Build automation on `git worktree list --porcelain -z`. Parse NUL-delimited records without shell word splitting, recognize rather than assume optional fields such as `locked` and `prunable`, and fail closed on malformed input. Resolve Git-owned paths with `git rev-parse --git-path` instead of assuming a directory layout.

## Verification

Test the parser against paths containing spaces and newlines, locked and detached worktrees, and a deliberately missing tree. Require a separate dry-run inventory before any prune or removal action.

## Gotchas

Porcelain output is stable, but automation must still tolerate fields added in future Git versions. Never feed an unvalidated parsed path into destructive recursion.

## Official sources

- https://git-scm.com/docs/git-worktree
- https://git-scm.com/docs/git-rev-parse
