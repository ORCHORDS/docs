# Node.js mock timers for deterministic time-based tests

**Issue:** Tests that wait on real timers or the wall clock are slow and flaky, while incomplete timer mocking can leave Date values, intervals, and promise scheduling inconsistent.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Use the Node.js test runner's per-test mock timers for code whose supported runtime provides the required API. Enable only the timer facilities under test, set an explicit initial time, and advance time deliberately. Inject clocks into domain code where possible and keep at least one integration test against real scheduling behavior.

## Verification

Cover timeouts, intervals, cancellation, Date advancement, boundary timestamps, and cleanup after each test. Run the suite repeatedly and with shuffled concurrency, confirming no mocked clock leaks into sibling tests. Compare one real-time smoke test with the mocked result.

## Gotchas

Advancing mocked time is not identical to waiting in the event loop; microtasks, I/O, and unsupported timer APIs may behave differently. The mock-timer API has evolved across Node releases, so pin and test the supported runtime rather than copying examples from another version.

## Official sources

- https://nodejs.org/api/test.html#mocking-timers
- https://nodejs.org/api/timers.html
