# Git filesystem stat-check policy

**Problem**

Reducing index stat checks can improve performance on unusual filesystems but increases risk of missing worktree changes.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use only after measuring false-dirty or timestamp-resolution behavior.

## Controls

- Choose `core.checkStat` from verified filesystem semantics.
- Keep content-based verification before release.
- Scope config to affected repositories.

## Implementation

- Canary minimal mode.
- Record filesystem/mount characteristics.
- Provide rollback.

## Tests

- Modify size, mode, timestamps, same-second content, network mounts, and clock changes; compare status/diff.

## Gotchas

- Stat heuristics are not content integrity.
- Filesystem behavior can change across runners.
- Performance gains may be negligible.

## Official sources

- [Official documentation](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corecheckStat)
