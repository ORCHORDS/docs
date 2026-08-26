# android-workmanager-background

**Issue:** Running reliable background work on Android with WorkManager
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Android's battery optimization kills background processes aggressively. WorkManager is the recommended API for deferrable, guaranteed background work that must survive app restart and device reboot.

## Pattern / Solution
**Define a Worker:**
```kotlin
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        return try {
            val data = inputData.getString("user_id") ?: return Result.failure()
            syncUserData(data)
            Result.success()
        } catch (e: Exception) {
            if (runAttemptCount < 3) Result.retry() else Result.failure()
        }
    }
}
```

**Enqueue work:**
```kotlin
val constraints = Constraints.Builder()
    .setRequiredNetworkType(NetworkType.CONNECTED)
    .setRequiresBatteryNotLow(true)
    .build()

val request = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
    .setConstraints(constraints)
    .setInputData(workDataOf("user_id" to userId))
    .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 10, TimeUnit.MINUTES)
    .build()

WorkManager.getInstance(context).enqueueUniquePeriodicWork(
    "sync_work",
    ExistingPeriodicWorkPolicy.KEEP, // or UPDATE to replace
    request
)
```

**Observe status:**
```kotlin
WorkManager.getInstance(context)
    .getWorkInfosForUniqueWorkLiveData("sync_work")
    .observe(lifecycleOwner) { workInfos ->
        workInfos?.firstOrNull()?.let { info ->
            when (info.state) {
                WorkInfo.State.RUNNING -> showProgress()
                WorkInfo.State.SUCCEEDED -> showSuccess()
                WorkInfo.State.FAILED -> showError()
                else -> {}
            }
        }
    }
```

**React Native (expo-task-manager + expo-background-fetch):**
```ts
import * as BackgroundFetch from 'expo-background-fetch';
import * as TaskManager from 'expo-task-manager';

TaskManager.defineTask('background-sync', async () => {
  await syncData();
  return BackgroundFetch.BackgroundFetchResult.NewData;
});
await BackgroundFetch.registerTaskAsync('background-sync', { minimumInterval: 900 });
```

## Gotchas
- Minimum periodic interval is 15 minutes; WorkManager will not run work more frequently
- `Result.retry()` with exponential backoff has a cap; define `setBackoffCriteria` explicitly
- OEM battery optimizations (Huawei, Xiaomi, Samsung) may prevent even WorkManager from running; direct users to battery settings
- `KEEP` policy ignores new constraints if an identical work name already exists; use `UPDATE` when constraints change
- `doWork()` has a 10-minute execution window; for longer tasks use `setForeground()` to promote to a foreground service

## Related
- `ios-background-fetch.md`
- `react-native-offline-first.md`
- `android-firebase-messaging.md`
