# BuildKit cache-mount concurrency and integrity

**Issue:** Shared package caches speed container builds, but incompatible concurrent access or treating cache contents as trusted can cause corruption and nondeterministic builds.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

BuildKit `RUN --mount=type=cache` keeps package-manager cache data reusable across builds even when the instruction layer must run again. Choose mount targets and sharing semantics from the package manager's concurrency guarantees. Docker's APT example uses `sharing=locked` because concurrent access needs exclusive coordination.

A cache mount is an optimization, not an input of record. Lockfiles, verified registries, pinned base images, and package integrity checks must continue to determine build correctness.

## Operational controls

- Give unrelated projects or incompatible tool versions separate cache identities.
- Use locked sharing where the cache consumer requires exclusive access.
- Exclude credentials and authenticated configuration from cached paths.
- Keep generated application artifacts outside package-download caches unless their complete input key is proven.
- Establish cache garbage collection and disk-pressure monitoring on persistent builders.
- For external caches, apply registry authentication and trust controls independently of image publication.

## Verification

1. Build from an empty cache and record the resulting image digest or verified artifact manifest.
2. Rebuild warm and confirm equivalent outputs.
3. Run concurrent builds against the same cache and check for corruption or nondeterminism.
4. Change lockfiles and confirm packages are re-resolved correctly.
5. Simulate a missing or damaged cache and verify a safe clean rebuild.

## Sources

- [Docker Docs: Optimize cache usage in builds](https://docs.docker.com/build/cache/optimize/)
- [Dockerfile reference: RUN --mount=type=cache](https://docs.docker.com/reference/dockerfile/#run---mounttypecache)
- [Docker Docs: Cache storage backends](https://docs.docker.com/build/cache/backends/)
