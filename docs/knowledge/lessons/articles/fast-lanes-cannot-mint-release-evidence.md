# Fast lanes cannot mint release evidence

**Lesson:** A fast PR lane can reduce feedback time, but its reduced matrix, credentials, and environment cannot prove release readiness.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Operationalization

Separate PR smoke, nightly breadth, and protected release gates; bind release evidence to the exact SHA and environment.

## Verification

Pass PR smoke while failing a release-only signing/device/deployment test; verify promotion stops.

## Gotchas

Reusing a check name across weaker and stronger lanes can make branch protection consume the wrong conclusion.

## Official sources

- https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
