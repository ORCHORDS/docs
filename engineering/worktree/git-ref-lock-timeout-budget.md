# Git reference-lock timeout budget

**Problem**

Reference updates can fail or stall under contention; an unreviewed timeout hides concurrent writers or creates flaky automation.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use in high-concurrency repositories after identifying legitimate lock contention.

## Controls

- Set files-ref lock timeout from measured transaction duration.
- Prefer reducing competing writers.
- Keep timeouts finite and observable.

## Implementation

- Configure in repository scope.
- Log ref operation and wait duration without sensitive names.
- Use atomic ref transactions.

## Tests

- Hold locks, run competing updates, crash writers, and test stale lock recovery.

## Gotchas

- Only the files backend uses this control.
- Long waits can hide deadlocks.
- Manual lock deletion is unsafe.

## Official sources

- [Official documentation](https://git-scm.com/docs/git-config#Documentation/git-config.txt-corefilesRefLockTimeout)
