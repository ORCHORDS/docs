# Node test isolation=none boundary

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Disabling test isolation runs files in one process, allowing globals, environment variables, mocks, handles, and module state to leak between files.

## When to use

Use only for a measured, explicitly ordered diagnostic lane—not as the default correctness lane.

## Controls

Keep an isolated required lane, pin file order if diagnosing, reset all state, detect open handles, and never use shared credentials.

## Implementation

Run the suite in default isolation and isolation=none, randomize manifests externally, compare results, and fail on order dependence.

## Tests

Test global mutation, module cache, timers, ports, environment restoration, uncaught errors, and cancellation.

## Gotchas

Speed gains do not justify losing isolation checks; concurrency and process-level failure behavior change.

## Official sources

- [Official documentation](https://nodejs.org/api/test.html#test-runner-execution-model)
