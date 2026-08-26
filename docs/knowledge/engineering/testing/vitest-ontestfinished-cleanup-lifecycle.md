# Vitest onTestFinished cleanup lifecycle

**Issue:** Resource cleanup placed in a distant `afterEach` hook can miss dynamically created resources, while a global cleanup registration can attach to the wrong concurrently running test.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Register cleanup with `onTestFinished` immediately after acquiring a file, server, database connection, fake clock, or other per-test resource.
- In `test.concurrent`, use the `onTestFinished` function from that test's context; the global hook cannot reliably track concurrent tests.
- Make cleanup idempotent, bounded by a timeout, and safe after partial setup. Register independent cleanups in acquisition order knowing they run in reverse order.
- Remember that `onTestFinished` runs after `afterEach`; do not make correctness depend on an undocumented cross-hook race.
- Fail the test or emit explicit quarantine evidence when cleanup fails; never silently leave ports, processes, data, or credentials behind.

## Verification

Exercise pass, assertion failure, thrown setup error after partial acquisition, timeout, cancellation, concurrent tests, multiple LIFO cleanups, cleanup failure, and a rerun in the same worker. Assert no resource survives and no cleanup operates on another test's object.

## Gotchas

- The hook must be registered from inside a running test.
- Cleanup locality improves ownership but does not replace suite-level recovery after process termination.
- A killed worker cannot run in-process cleanup; external leases still need expiry or a janitor.

## Official source

- [Vitest hooks: onTestFinished](https://vitest.dev/api/hooks.html#ontestfinished)
- [Vitest setup and teardown](https://vitest.dev/guide/learn/setup-teardown.html#cleanup-with-ontestfinished)
