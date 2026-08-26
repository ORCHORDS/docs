# Vitest projects isolation and configuration boundaries

**Issue:** Combining browser, Node, integration, and package tests in one implicit configuration can leak globals, use the wrong environment, and make parallel results order-dependent.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Define named Vitest projects with explicit include/exclude patterns, environment, setup files, pool, and timeouts. Keep project patterns non-overlapping unless duplicate execution is intentional. Use per-project isolation defaults; share only deterministic helpers, not mutable runtime state. Select projects explicitly in focused CI jobs while retaining an aggregate all-project gate.

## Verification

List resolved projects in CI, seed randomized tests, and run the full suite repeatedly with alternate worker counts. Add a sentinel test for each environment and confirm every intended file is collected exactly once.

## Gotchas

Project configuration inheritance can silently carry unsuitable root settings. Disabling isolation may improve speed but requires proof that tests reset modules, mocks, timers, globals, and external resources.

## Official sources

- https://vitest.dev/guide/projects
- https://vitest.dev/config/
