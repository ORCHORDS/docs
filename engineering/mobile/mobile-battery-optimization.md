# mobile-battery-optimization

**Issue:** Reducing battery drain from background work, location, and network polling in mobile apps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Apps appearing in battery usage settings cause uninstalls; OS background restrictions also terminate poorly-behaved apps.

## Pattern / Solution
**General principles:**
- Batch network requests; avoid polling — use push (FCM/APNs) instead
- Use `WorkManager` (Android) / `BGTaskScheduler` (iOS) for deferrable background work
- Request location at lowest accuracy needed; stop updates when app is backgrounded

**Android — WorkManager for deferred sync:**
```kotlin
val constraints = Constraints.Builder()
  .setRequiredNetworkType(NetworkType.UNMETERED) // WiFi only
  .setRequiresBatteryNotLow(true)
  .build()

val request = PeriodicWorkRequestBuilder<SyncWorker>(1, TimeUnit.HOURS)
  .setConstraints(constraints)
  .build()

WorkManager.getInstance(context).enqueueUniquePeriodicWork(
  "sync", ExistingPeriodicWorkPolicy.KEEP, request
)
```

**iOS — BGAppRefreshTask:**
```swift
BGTaskScheduler.shared.register(forTaskWithIdentifier: "com.example.sync", using: nil) { task in
  task.expirationHandler = { task.setTaskCompleted(success: false) }
  Task {
    await SyncService.sync()
    task.setTaskCompleted(success: true)
    scheduleNextRefresh()
  }
}
```

**React Native — `react-native-background-fetch`:**
```ts
BackgroundFetch.configure({
  minimumFetchInterval: 15,  // minutes
  stopOnTerminate: false,
  enableHeadless: true,
}, async (taskId) => {
  await syncData();
  BackgroundFetch.finish(taskId);
});
```

## Gotchas
- Android Doze mode and App Standby buckets aggressively defer background work — test on physical devices with Doze enabled
- iOS limits background refresh to ~30 seconds; long-running tasks must use `BGProcessingTask`
- GPS at `PRIORITY_HIGH_ACCURACY` drains 10–15% battery per hour; use `PRIORITY_BALANCED_POWER_ACCURACY` for geofencing
- Keeping a `WakeLock` indefinitely on Android causes battery drain and potential ANR

## Related
- `mobile-network-resilience.md`
- `android-workmanager-background.md`
- `ios-background-fetch.md`
