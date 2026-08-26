# Git backfill partial-clone object policy

**Issue**

Backfilling missing objects in a partial clone can trade later latency for immediate network, disk, and trust-boundary cost.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Run backfill only against the configured trusted promisor remote.
- Select paths or object classes from measured offline/build needs.
- Budget bytes, disk headroom, and interruption recovery.

## Verification

1. Backfill a disposable partial clone and verify offline operations.
2. Interrupt and retry downloads.
3. Run fsck with promisor semantics and compare object counts.

## Gotchas

- Backfill can erase partial-clone storage benefits.
- Fetched objects remain subject to repository access policy.
- Version support is evolving.

## Official source

- [Official documentation](https://git-scm.com/docs/git-backfill)
