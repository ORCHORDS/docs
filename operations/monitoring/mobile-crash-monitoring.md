# mobile-crash-monitoring

**Issue:** Detecting, grouping, and resolving crashes in iOS and Android applications
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Users report crashes with no stack trace visible in server logs. Need mobile crash reporting to debug native crashes.

## Pattern / Solution
Integrate a crash reporting SDK: Firebase Crashlytics (free), Sentry (mobile SDK), or Bugsnag. Configure dSYM (iOS) and ProGuard/R8 mapping (Android) upload in CI pipeline. Group crashes by stack trace fingerprint. Track crash-free users rate (target above 99.5%). Alert when crash rate increases more than 0.5% after a release. Review crash trends per app version and OS version.

## Gotchas
dSYM upload is critical for iOS symbolication — crashes are unreadable without it. OOM kills are not reported by crash SDKs on iOS — track via MetricKit. ANR (Application Not Responding) on Android is separate from crashes. Crash rate spikes post-release may indicate device/OS compatibility issues.

## Related
sentry-error-tracking, deployment-event-tracking, real-user-monitoring-rum
