# Android ApplicationStartInfo startup diagnostics

**Issue:** Mobile startup telemetry records one wall-clock duration and guesses why a process launched. Cold, warm, hot, relaunch, backup, broadcast, service, and system-throttled starts are mixed into one percentile, hiding regressions and encouraging incorrect startup behavior.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published; API 35+ with fallback

## Controls and implementation

On supported Android versions, retrieve `ApplicationStartInfo` through `ActivityManager.getHistoricalProcessStartReasons()` and use the completion listener when the current record is finalized. Record the documented reason, start type, timestamps, launch mode, and throttling state as diagnostic dimensions. Add application milestones only through the supported timestamp API and keep a schema version.

Feature-detect by SDK level and retain existing first-frame/startup tracing for older devices. Sample and bound history, redact intent/component extras and user-linked data, and upload outside the critical startup path. Never branch authorization or essential product behavior on a diagnostic record.

## Verification

Exercise launcher, notification, deep link, broadcast, service, backup/restore, process recreation, crash relaunch, force stop, warm resume, multi-process components, throttled start, and OS upgrade. Compare platform milestones with trace/first-frame evidence and verify missing records are tolerated.

## Gotchas

Historical records are bounded platform diagnostics, not a durable audit log. A start reason explains how the process was launched, not necessarily what the person intended, and callback completion timing must not block rendering.

## Sources

- Android Developers, [ApplicationStartInfo API reference](https://developer.android.com/reference/android/app/ApplicationStartInfo)
- Android Developers, [ActivityManager API reference](https://developer.android.com/reference/android/app/ActivityManager)
