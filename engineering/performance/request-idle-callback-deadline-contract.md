# requestIdleCallback deadline contract

**Issue:** Idle callbacks are opportunistic and may be delayed indefinitely; timeout callbacks may run with no useful idle budget. Using them for required persistence or unbounded work causes data loss and jank.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Schedule only deferrable work, check `timeRemaining()` before each bounded chunk, yield early, and use a justified timeout. Required writes and security work use durable lifecycle-aware paths. Cancel callbacks on teardown and provide an unsupported scheduler fallback.

## Verification

Test busy/idle main thread, timeout with zero budget, hidden tabs, navigation, cancellation, large queues, unsupported browsers, and input arriving mid-work.

## Gotchas

An idle deadline is a per-callback hint, not reserved CPU time; implementations throttle background work.

## Sources

- W3C, [Cooperative Scheduling of Background Tasks](https://www.w3.org/TR/requestidlecallback/)
