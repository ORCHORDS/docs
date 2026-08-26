# Linux cachestat page-cache observation

**Problem**

Filesystem IO diagnosis often guesses cache effectiveness from process metrics instead of querying page-cache statistics for a file range.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for privileged performance diagnosis on supported kernels.

## Controls

- Open the intended file and query bounded ranges.
- Treat results as approximate observations, not billing counters.
- Restrict descriptor and path access.

## Implementation

- Call `cachestat` with explicit offset/length and record kernel/filesystem.
- Correlate with application latency and IO counters.
- Close descriptors deterministically.

## Tests

- Test cold, warm, evicted, sparse, and concurrently written files.
- Compare repeated samples.

## Gotchas

- Cache state changes immediately.
- Filesystem support differs.
- Observation can perturb workload.

## Official sources

- [Official documentation](https://man7.org/linux/man-pages/man2/cachestat.2.html)
