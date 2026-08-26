# Android ProfilingManager System-Triggered Profiles

**Issue:** Lab traces miss rare ANRs, OOMs, cold-start regressions, and excessive-CPU failures, while unrestricted production profiling creates privacy, storage, and performance risk.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

On supported Android versions, use `ProfilingManager` or the recommended AndroidX wrapper to request bounded system traces, heap profiles, stack samples, or heap dumps. For API-level 36 system-triggered capture, register only relevant `ProfilingTrigger` types and a global listener, because trigger results are delivered through that listener. Set an application-side rate-limiting period in addition to platform limits.

Treat requests as best effort: they are rate-limited and not guaranteed. Copy/process delivered files within app storage, attach a non-sensitive correlation tag, redact before upload, enforce retention/size/network policy, and obtain any consent the product requires. Avoid collecting credentials or user content.

## Verification

Test supported/unsupported API levels, accepted and dropped requests, cancellation, callback after process restart, each registered trigger, duplicate registration replacement, storage pressure, redacted upload, offline queueing, and cleanup. Use Android's documented testing modes only on test devices and restore device configuration afterward.

## Gotchas

A request may start late; start continuous profiling early and cancel after the target region. Debug modes can retain additional results and must not be production configuration. Results are process-specific and system-triggered capture does not guarantee root cause.

## Sources

- [Android ProfilingManager API reference](https://developer.android.com/reference/android/os/ProfilingManager)
- [Android ProfilingTrigger API reference](https://developer.android.com/reference/android/os/ProfilingTrigger)
