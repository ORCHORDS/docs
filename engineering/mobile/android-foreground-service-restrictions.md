# android-foreground-service-restrictions

**Issue:** Android 14 (API 34) through Android 16 (API 36) progressively tightened foreground services: every service must declare a specific type matching a declared permission, several types are blocked from starting while the app is in the background, and Android 15 introduced a hard 6-hour-per-24-hours runtime budget on `dataSync` (and `mediaProcessing`) services that kills the service via `onTimeout()` when exhausted. Apps written against pre-14 assumptions — "start a dataSync foreground service and sync forever" — now crash with `MissingForegroundServiceTypeException`, `ForegroundServiceStartNotAllowedException`, or get silently killed mid-upload. This article covers the 2025-2026 rules, the timeout mechanics, and how to migrate.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The rules you must satisfy now (Android 14+)

1. **Declare a type for every foreground service.** `<service android:foregroundServiceType="dataSync|mediaPlayback|location|connectedDevice|...">` plus the matching manifest permission (e.g. `FOREGROUND_SERVICE_DATA_SYNC`). Omitting the type when targeting API 34+ throws `MissingForegroundServiceTypeException` at `startForeground()`.
2. **Type must match what the service actually does.** Play review and platform heuristics flag mismatches (a `mediaPlayback` service doing network sync). Android 15 adds per-type requirements — e.g. `camera`/`microphone` types cannot start while the app is backgrounded at all, and Android 16 requires them to stop when the app loses visibility.
3. **Background start restrictions apply.** Since Android 12, calling `startForegroundService()` from the background (no visible activity, no exemption) throws `ForegroundServiceStartNotAllowedException` — the classic breakage is a push-received handler or `BOOT_COMPLETED` receiver starting an FGS without checking exemptions. Android 15 removes the `SYSTEM_ALERT_WINDOW` exemption for starting camera/mic FGS.
4. **`POST_NOTIFICATIONS` is a runtime permission since API 33.** The FGS notification still posts without it (the service runs), but the user sees no notification on Android 13+ unless granted — meaning an invisible "sync running" service users cannot see or understand. Request it in-context when starting long work.
5. **`dataSync` got a 6-hour/24-hour budget in Android 15.** Total runtime across all the app's `dataSync` FGS is capped at 6 hours in any rolling 24-hour window; `mediaProcessing` gets the same cap. When exhausted, the system calls `Service.onTimeout(startId, fgsType)` and force-stops the service shortly after if you don't stop it yourself.

## How the 6-hour dataSync timeout actually behaves

1. **The budget is app-wide and cumulative, not per-service-run.** Six 55-minute syncs across a day consume the same budget as one long run — developers hit "time limit already exhausted" on a sync that normally takes minutes because earlier runs already spent the window. Budget queries: `Service.getForegroundServiceTypeInfo()` / `getRemainingDurationMs()` (added in Android 15 / supported-extras APIs).
2. **Only user interaction resets the timer.** The 24-hour clock resets when the user actually interacts with the app (brings it to foreground), not when your service restarts or the device reboots alone. A purely background-used app can find itself permanently out of budget.
3. **`onTimeout()` gives you seconds, not minutes.** In the timeout callback you must stop work and call `stopSelf()`/`stopForeground()` promptly; on Android 16 (targeting API 36) the follow-up is an ANR ("FGS timeout") rather than a quiet kill if you keep running. Treat it as "flush and yield."
4. **Hand off unfinished work before dying.** The correct pattern in `onTimeout()` is: persist progress (Room, DataStore — see `mobile-offline-sync-conflict-resolution.md`), enqueue continuation via WorkManager, then stop. Never restart another `dataSync` FGS immediately — the budget is already gone and the restart will be killed.
5. **Detect and log budget state in the field.** Play Console vitals and `dumpsys activity services` show FGS usage locally, but you should also log remaining-duration at service start so production telemetry tells you which users are near the cliff before support tickets arrive.

## Migration paths off long-running dataSync

1. **Deferrable work → WorkManager.** Sync that merely needs to happen "soon" with network constraints belongs in `PeriodicWorkRequest` / expedited work (see `android-workmanager-background.md`). WorkManager is unaffected by the 6-hour FGS budget and is Google's explicit recommendation for background sync.
2. **Ongoing location → `location` FGS type.** Fitness/GPS tracking apps (runs, rides, delivery) moved to the `location` type with `ACCESS_BACKGROUND_LOCATION` and a visible persistent notification; this type has no 6-hour cap, but requires the runtime permission and honest disclosure to Play review.
3. **Media downloads → `mediaPlayback` or DownloadManager.** The androidx.media `DownloadService` broke under the Android 15 timeout precisely because it used `dataSync`; current androidx versions moved download foreground services to appropriate types — keeping an old androidx.media version pinned is itself a production bug.
4. **Device/IoT companions → `connectedDevice`.** BLE/Wearable-style ongoing connections map to `connectedDevice` (with `FOREGROUND_SERVICE_CONNECTED_DEVICE` and a declared companion-device or Bluetooth justification). Choose the narrowest type that matches; Play review documentation lists accepted justifications per type.
5. **User-visible long jobs → do them in the foreground.** If the user is watching progress (video export, large upload with a progress screen), keeping an activity bound and the work in-app is more honest than a fake FGS — Android 16's rules increasingly require the type to match user-visible behavior anyway.

## Testing and compliance checklist

1. **Test the timeout end-to-end.** `adb shell cmd activity foreground-service-timeout --work ...` style device-side commands and the API-35 emulator let you shrink/trigger the dataSync budget; at minimum, write a test that calls `onTimeout()` directly and asserts state was persisted and the service stopped without ANR. Verify via `adb logcat` for the "FGS timeout" ANR string.
2. **Target-API pinning is a real mitigation, not a fix.** The 6-hour cap applies when targeting API 35+; shipping with targetSdk 34 buys time but blocks access to new APIs and eventually fails Play's target-API requirement. Plan the migration in the same release cycle, not "later."
3. **Audit `startForegroundService` call sites for background starts.** Wrap them with `try/catch ForegroundServiceStartNotAllowedException` and fall back to WorkManager; every crash-free dashboard after an OEM update contains these. For boot-time work, Android 15 restricts `BOOT_COMPLETED`-launched FGS to specific types (dataSync among the blocked) — use WorkManager from the receiver.
4. **Keep the notification honest.** A low-importance, accurate channel ("Syncing your data") with cancel affordance survives Play review; a silent/minimized notification that hides long-running work is a documented removal reason under misuse-of-FGS policy.
5. **Re-check rules per release.** Android 16 (API 36) tightens camera/mic FGS lifecycle and adds new timeout behaviors; the behavior-changes page for each API level is required reading before bumping targetSdk. Track the official docs: developer.android.com/about/versions/15/behavior-changes-15 and /16/behavior-changes-16.

## Related

- `android-workmanager-background.md` — the replacement for most dataSync use cases
- `mobile-battery-optimization.md` — why the platform keeps tightening FGS
- `android-play-store-submission.md` — FGS-type declaration review
- `app-store-policy-hotspots-2026.md` — platform policy overview
