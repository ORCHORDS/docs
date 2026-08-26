# Git cruft-pack retention policy

**Problem**

Unreachable objects retained in cruft packs improve recovery but consume disk and may preserve sensitive deleted history.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when balancing recovery windows with repository storage and data-erasure policy.

## Controls

- Set explicit expiration and legal retention policy.
- Protect recent recovery objects while honoring deletion requirements.
- Measure cruft growth.

## Implementation

- Use supported gc/repack commands.
- Keep one maintenance writer.
- Verify before/after object reachability.

## Tests

- Create unreachable objects of different ages, reflog retention, alternates, and interrupted repack; test recovery.

## Gotchas

- Unreachable is not immediately deletable.
- Expiration is destructive.
- Sensitive history may persist.

## Official sources

- [Official documentation](https://git-scm.com/docs/git-gc)
