# Git reachable-object disk-usage accounting

**Problem**

Repository directory size does not show which refs or histories retain objects; rev-list disk-usage modes provide scoped reachability accounting.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when planning history cleanup, retention, or clone-size work.

## Controls

- Measure reviewed ref sets and exclusions explicitly.
- Record object format, alternates, and pack state.
- Never delete objects from accounting output alone.

## Implementation

- Use `git rev-list --disk-usage` with exact revision arguments.
- Compare reachable, excluded, and reflog-retained sets.
- Follow with supported maintenance only after review.

## Tests

- Test packed/loose objects, alternates, replace refs, partial clones, and recent reflogs.
- Compare before/after without pruning during measurement.

## Gotchas

- Shared objects can be counted from multiple logical scopes.
- Reported disk use depends on packing.
- Reachability and business retention are different.

## Official sources

- [Official documentation](https://git-scm.com/docs/git-rev-list)
