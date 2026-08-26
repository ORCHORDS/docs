# Atomics.waitAsync Synchronous Versus Promise Result

**Issue:** Atomics.waitAsync does not always return a Promise. It returns a record whose value may be an immediate string or a Promise, depending on the observed value and timeout.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Inspect the returned async flag before awaiting value.
- Use only supported shared integer typed arrays and validate the index.
- Recheck shared state in a loop after wakeup because notification does not establish an application invariant by itself.
- Bound waits and define shutdown notification behavior.

## Verification

- Exercise not-equal, zero-timeout, notification, and timed-out paths.
- Race state changes around the wait and verify the loop predicate.
- Run compatibility tests on every supported runtime.

## Gotchas

- A notification count is not proof that a particular waiter completed useful work.
- Shared-memory synchronization still requires a correct atomic state protocol.

## Official sources

- https://tc39.es/ecma262/multipage/structured-data.html#sec-atomics.waitasync
