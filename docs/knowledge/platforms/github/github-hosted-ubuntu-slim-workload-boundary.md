# GitHub-hosted ubuntu-slim workload boundary

**Issue:** GitHub's single-CPU `ubuntu-slim` runner is an unprivileged container with a 15-minute job limit, intended for lightweight automation rather than typical builds.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Route only measured short jobs; pin required tools explicitly; set a lower timeout; keep heavyweight builds, Docker-in-Docker, mounts, and low-level kernel work on full VM runners.

## Verification

Test worst-case duration, missing tools, privileged operations, artifact upload, cancellation, and fallback without changing required check names.

## Gotchas

The container has hypervisor-level isolation but is not a full VM workload profile. Queue routing must not silently skip the check when it exceeds limits.

## Official sources

- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
