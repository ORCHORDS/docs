# ios-background-fetch

**Issue:** Running periodic background tasks on iOS
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
iOS severely restricts background execution. Apps can't run arbitrary code in the background — they must use specific BGTask APIs. Misuse leads to background tasks being killed silently.

## Pattern / Solution
**Register tasks in AppDelegate (Swift):**
```swift
import BackgroundTasks

func application(_ application: UIApplication, didFinishLaunchingWithOptions ...) -> Bool {
    BGTaskScheduler.shared.register(
        forTaskWithIdentifier: "com.example.myapp.refresh",
        using: nil
    ) { task in
        self.handleAppRefresh(task: task as! BGAppRefreshTask)
    }
    return true
}

func scheduleAppRefresh() {
    let request = BGAppRefreshTaskRequest(identifier: "com.example.myapp.refresh")
    request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
    try? BGTaskScheduler.shared.submit(request)
}

func handleAppRefresh(task: BGAppRefreshTask) {
    scheduleAppRefresh() // reschedule immediately
    let operation = SyncOperation()
    task.expirationHandler = { operation.cancel() }
    operation.completionBlock = { task.setTaskCompleted(success: !operation.isCancelled) }
    OperationQueue.main.addOperation(operation)
}
```

**Info.plist:**
```xml
<key>BGTaskSchedulerPermittedIdentifiers</key>
<array>
    <string>com.example.myapp.refresh</string>
</array>
```

**In React Native (via expo-background-fetch):**
```ts
import * as BackgroundFetch from 'expo-background-fetch';
import * as TaskManager from 'expo-task-manager';

const TASK_NAME = 'background-sync';

TaskManager.defineTask(TASK_NAME, async () => {
  await syncData();
  return BackgroundFetch.BackgroundFetchResult.NewData;
});

await BackgroundFetch.registerTaskAsync(TASK_NAME, {
  minimumInterval: 15 * 60, // 15 minutes (minimum iOS allows)
  stopOnTerminate: false,
  startOnBoot: true,
});
```

## Gotchas
- iOS schedules background fetch at its own discretion based on usage patterns; `earliestBeginDate` is a hint, not a guarantee
- The background task budget is typically 30 seconds; long-running tasks need `BGProcessingTask` instead
- Test background tasks in the simulator with `e simulateBackgroundFetch` in the Xcode debugger console: `e -l objc -- (void)[[BGTaskScheduler sharedScheduler] _simulateLaunchForTaskWithIdentifier:@"com.example.myapp.refresh"]`
- Missing `BGTaskSchedulerPermittedIdentifiers` entry causes a crash at registration
- Background app refresh must be enabled by the user in iOS Settings; check with `BackgroundFetch.getStatusAsync()`

## Related
- `ios-push-notifications-apns.md`
- `android-workmanager-background.md`
- `react-native-offline-first.md`
