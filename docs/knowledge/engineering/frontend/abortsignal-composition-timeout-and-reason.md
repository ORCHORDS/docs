# AbortSignal Composition, Timeout, and Reason

**Issue:** UI operations leak after navigation or use independent timers/controllers that race, obscure whether a user canceled or a deadline expired, and leave downstream asynchronous work running.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Accept an `AbortSignal` at every abortable API boundary, call `throwIfAborted()` before starting work, and reject unsettled promises with `signal.reason`. Compose lifecycle, user-cancel, and deadline signals with `AbortSignal.any()`; create active-time deadlines with `AbortSignal.timeout()`. Pass the resulting signal through fetch, stream readers, and application tasks rather than creating unrelated controllers below them.

Use reason types as control flow: a timeout signal produces `TimeoutError`, while an ordinary controller defaults to `AbortError`. Remove event listeners or register them with a signal so cleanup is deterministic. Feature-detect static methods for older clients and keep a tested adapter.

## Verification

Test already-aborted inputs, user cancel before/after response headers, timeout during body consumption, two signals aborting nearly together, bfcache/document suspension, worker suspension, component unmount, retry, unsupported runtimes, and cleanup after success. Confirm the first abort reason wins and no late state update or duplicate request occurs.

## Gotchas

`AbortSignal.timeout()` uses active rather than wall-clock time, so suspension pauses its deadline. Aborting fetch also affects response body consumption. `AbortSignal.any()` preserves the first reason, but generic wrappers can accidentally replace it. Cancellation is cooperative; CPU work must check the signal.

## Sources

- [WHATWG DOM — AbortSignal](https://dom.spec.whatwg.org/#interface-abortsignal)
- [MDN AbortSignal.any](https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/any_static)
- [MDN AbortSignal.timeout](https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/timeout_static)
