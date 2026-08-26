# GitHub Actions Self-Hosted Cache Speed Without Losing Checks

**Issue:** Self-hosted workflows waste time downloading tools and dependencies, but unsafe caching can restore stale outputs, hide missing verification, or hang jobs on a slow cache segment.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Safe speed controls

- Keep every lint, test, security, and build gate; cache inputs and deterministic intermediate data, not pass/fail results.
- Pin the cache action to a reviewed immutable commit and track its supported runner version. Current `actions/cache@v5` uses Node.js 24 and requires runner 2.327.1 or newer.
- Build cache keys from OS, architecture, toolchain version, lockfile hash, and any build flags that change outputs.
- Use restore-key prefixes only for data the package manager or compiler revalidates.
- Set `SEGMENT_DOWNLOAD_TIMEOUT_MINS` from measured network behavior so a stalled segment becomes a cache miss instead of consuming the job timeout.
- Pre-populate the runner tool cache through a versioned image or controlled installation and verify checksums; do not rely on mutable host state.
- Use separate save and restore phases only when ownership and trust boundaries are clear.

## Measurement

Record restore duration, save duration, hit type (exact/partial/miss), bytes transferred, install/build duration, and total job critical path. Remove caches whose transfer plus decompression costs more than recomputation. Test cold, warm, and corrupted-cache cases.

## Integrity tests

Delete caches and prove the workflow still passes from a clean state. Change the lockfile and toolchain independently and verify key invalidation. Inject an unusable restored directory and ensure the package manager verifies or rebuilds it. Confirm fork and untrusted-branch workflows cannot poison a cache later consumed by privileged jobs.

## Gotchas

Self-hosted runner caches are stored in GitHub-owned cloud storage for GitHub.com Actions, so local disk speed does not eliminate network transfer. Cross-OS archives need compatible GNU tar and zstd. Never cache credentials, signing material, test reports used as gates, or mutable deployment state.

## Sources

- [Official actions/cache repository](https://github.com/actions/cache)
- [GitHub dependency caching](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching)
- [GitHub self-hosted runners reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)
