# Node.js test process-isolation boundaries

**Issue**

Disabling Node test isolation can improve speed but permits module cache, globals, environment, mocks, timers, and handles to leak between files.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Keep process isolation for authoritative CI; use no-isolation only in a measured lane with order-randomization checks.
- Reset globals, mocks, environment, and resources explicitly.
- Reject tests whose outcome depends on file order or shared ports.
- Track open handles and heap growth across the suite.

## Verification

1. Run files alone, together, reversed, and randomized.
2. Seed a leaking global and require the hygiene check to catch it.
3. Compare duration and flake rate against isolated execution.

## Gotchas

- Passing without isolation can conceal pollution.
- Concurrency and isolation are separate controls.
- Native addons and singleton modules may resist reset.

## Official source

- [Official documentation](https://nodejs.org/api/test.html#test-runner-execution-model)
