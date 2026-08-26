# Android Workers Battery-Aware Sync Scheduling

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Sync jobs running on a fixed timer drain battery on low-end devices and trigger battery saver complaints in Play Store reviews. The app needs to defer sync when the battery is low or the device is heavily constrained, adapt the sync interval dynamically based on thermal and battery state, and call a Workers endpoint to fetch only the changed data (delta sync) so each sync is as cheap as possible.

## Context

WorkManager is the correct API for deferrable background work on Android. It natively supports `requiresBatteryNotLow()` and `requiresCharging()` constraints. Combined with a `BroadcastReceiver` for `ACTION_BATTERY_CHANGED` and `PowerManager` thermal status, the app can choose between three sync tiers:

| Tier | Condition | Interval |
|------|-----------|----------|
| Fast | Charging + battery > 50% | 15 min |
| Normal | Battery 20–50% | 30 min |
| Minimal | Battery < 20% / battery saver | 2 h |

The Workers endpoint accepts a `last_sync` cursor and returns only records modified after that timestamp, limiting payload size.

---

## BatteryState Utility

```kotlin
// app/src/main/java/com/example/sync/BatteryState.kt
package com.example.sync

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager

data class BatterySnapshot(
  val levelPercent: Int,
  val isCharging: Boolean,
  val isBatterySaver: Boolean,
  val thermalStatus: Int, // PowerManager.THERMAL_STATUS_*
)

object BatteryState {
  fun snapshot(context: Context): BatterySnapshot {
    val pm = context.getSystemService(Context.POWER_SERVICE) as PowerManager

    val filter = IntentFilter(Intent.ACTION_BATTERY_CHANGED)
    val intent = context.registerReceiver(null, filter) ?: return BatterySnapshot(50, false, false, 0)

    val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
    val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, 100)
    val levelPercent = if (scale > 0) (level * 100 / scale) else 50

    val status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
    val isCharging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
      status == BatteryManager.BATTERY_STATUS_FULL

    val isBatterySaver = pm.isPowerSaveMode

    val thermalStatus = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
      pm.currentThermalStatus
    } else {
      PowerManager.THERMAL_STATUS_NONE
    }

    return BatterySnapshot(levelPercent, isCharging, isBatterySaver, thermalStatus)
  }

  fun syncTier(snap: BatterySnapshot): SyncTier = when {
    snap.isBatterySaver || snap.levelPercent < 20 -> SyncTier.MINIMAL
    snap.isCharging && snap.levelPercent >= 50 -> SyncTier.FAST
    else -> SyncTier.NORMAL
  }
}

enum class SyncTier(val intervalMinutes: Long) {
  FAST(15),
  NORMAL(30),
  MINIMAL(120),
}
```

## WorkManager Constraints Builder

```kotlin
// app/src/main/java/com/example/sync/SyncScheduler.kt
package com.example.sync

import android.content.Context
import androidx.work.*
import java.util.concurrent.TimeUnit

object SyncScheduler {

  private const val WORK_NAME = "battery_aware_sync"

  fun schedule(context: Context) {
    val snap = BatteryState.snapshot(context)
    val tier = BatteryState.syncTier(snap)

    val constraints = Constraints.Builder()
      .setRequiredNetworkType(NetworkType.CONNECTED)
      .setRequiresBatteryNotLow(tier != SyncTier.FAST) // fast tier runs even on lowish battery
      .setRequiresCharging(false) // never require charging — that prevents background sync entirely
      .build()

    val request = PeriodicWorkRequestBuilder<SyncWorker>(
      tier.intervalMinutes, TimeUnit.MINUTES,
      // Flex: allow WorkManager to fire within a 5-min window for batching
      5, TimeUnit.MINUTES
    )
      .setConstraints(constraints)
      .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 2, TimeUnit.MINUTES)
      .setInputData(workDataOf("tier" to tier.name))
      .build()

    WorkManager.getInstance(context).enqueueUniquePeriodicWork(
      WORK_NAME,
      ExistingPeriodicWorkPolicy.UPDATE,   // re-schedule with new interval if tier changed
      request
    )
  }

  fun cancel(context: Context) {
    WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
  }
}
```

## SyncWorker: Delta Sync via Workers

```kotlin
// app/src/main/java/com/example/sync/SyncWorker.kt
package com.example.sync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject

class SyncWorker(context: Context, params: WorkerParameters) :
  CoroutineWorker(context, params) {

  private val client = OkHttpClient()
  private val prefs = context.getSharedPreferences("sync_prefs", Context.MODE_PRIVATE)

  override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
    // Re-evaluate battery before doing any work
    val snap = BatteryState.snapshot(applicationContext)
    if (snap.isBatterySaver && snap.levelPercent < 15) {
      // Defer: return success so WorkManager retries at next interval
      return@withContext Result.success()
    }

    // Thermal throttle: skip if the device is severely hot
    if (snap.thermalStatus >= android.os.PowerManager.THERMAL_STATUS_SEVERE) {
      return@withContext Result.success()
    }

    val lastSync = prefs.getLong("last_sync_ms", 0L)
    val token = TokenManager.getValidToken(applicationContext)

    val request = Request.Builder()
      .url("https://api.example.com/sync/delta?since=${lastSync}")
      .header("Authorization", "Bearer $token")
      .get()
      .build()

    return@withContext try {
      val response = client.newCall(request).execute()
      if (!response.isSuccessful) {
        if (response.code == 429) Result.retry() else Result.failure()
      } else {
        val body = response.body?.string() ?: "{}"
        applyDelta(JSONObject(body))
        prefs.edit().putLong("last_sync_ms", System.currentTimeMillis()).apply()
        Result.success()
      }
    } catch (e: Exception) {
      Result.retry()
    }
  }

  private fun applyDelta(delta: JSONObject) {
    // Write changed records to Room database
    val records = delta.optJSONArray("records") ?: return
    val db = AppDatabase.getInstance(applicationContext)
    for (i in 0 until records.length()) {
      val obj = records.getJSONObject(i)
      db.recordDao().upsert(Record(id = obj.getString("id"), data = obj.toString()))
    }
  }
}
```

## Workers: Delta Sync Endpoint

```typescript
// workers/src/sync/delta.ts
import { Env } from '../types';

export async function handleDeltaSync(
  request: Request,
  env: Env
): Promise<Response> {
  const auth = request.headers.get('Authorization');
  if (!auth) return Response.json({ error: 'unauthorized' }, { status: 401 });

  const url = new URL(request.url);
  const since = parseInt(url.searchParams.get('since') ?? '0', 10);

  // D1: fetch only records modified after `since` (Unix ms)
  const { results } = await env.DB.prepare(
    `SELECT id, data, updated_at_ms FROM records
     WHERE updated_at_ms > ?
     ORDER BY updated_at_ms ASC
     LIMIT 200`
  )
    .bind(since)
    .all<{ id: string; data: string; updated_at_ms: number }>();

  return Response.json({
    records: results,
    count: results.length,
    server_time_ms: Date.now(),
  });
}
```

## BroadcastReceiver: Reschedule on Battery State Change

```kotlin
// app/src/main/java/com/example/sync/BatteryReceiver.kt
package com.example.sync

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.PowerManager

class BatteryReceiver : BroadcastReceiver() {
  override fun onReceive(context: Context, intent: Intent) {
    when (intent.action) {
      Intent.ACTION_BATTERY_LOW,
      Intent.ACTION_POWER_CONNECTED,
      Intent.ACTION_POWER_DISCONNECTED,
      PowerManager.ACTION_POWER_SAVE_MODE_CHANGED -> {
        // Re-evaluate tier and reschedule
        SyncScheduler.schedule(context)
      }
    }
  }
}
```

```xml
<!-- AndroidManifest.xml -->
<receiver android:name=".sync.BatteryReceiver" android:exported="false">
  <intent-filter>
    <action android:name="android.intent.action.BATTERY_LOW"/>
    <action android:name="android.intent.action.POWER_CONNECTED"/>
    <action android:name="android.intent.action.POWER_DISCONNECTED"/>
    <action android:name="android.os.action.POWER_SAVE_MODE_CHANGED"/>
  </intent-filter>
</receiver>
```

---

## Anti-patterns

- **AlarmManager for periodic sync** — `setRepeating` ignores battery constraints entirely and can be whitelisted out of Doze. WorkManager handles Doze, battery saver, and boot persistence automatically.
- **`setRequiresCharging(true)` in constraints** — this causes sync to never run for users who never plug in their phones (common in many markets). Use `requiresBatteryNotLow()` instead.
- **Full sync every period instead of delta** — downloading all records burns data and CPU. Always pass a `since` cursor and only transfer changes.
- **Checking battery level inside WorkManager without re-checking at runtime** — WorkManager constraints are evaluated before launch, but the battery can change during a long sync. Re-evaluate early in `doWork()`.

---

## Gotchas

- **WorkManager minimum interval is 15 min** — `PeriodicWorkRequest` enforces a 15-minute floor even if you pass a shorter interval. `FAST` tier (15 min) is the minimum granularity.
- **`ExistingPeriodicWorkPolicy.UPDATE` vs `REPLACE`** — `UPDATE` keeps the existing work's timing (avoids immediate re-run); `REPLACE` cancels and re-enqueues (can cause an immediate sync). Use `UPDATE` when rescheduling on battery change.
- **Battery level < 20% threshold** — `setRequiresBatteryNotLow()` uses the system-defined threshold (usually 15–20% depending on OEM), not a fixed number. For the custom 20% threshold, read it from `BatteryState.snapshot()` manually.
- **Doze whitelist** — in Doze mode, WorkManager jobs run only during Doze maintenance windows. If the Workers endpoint must be reached more frequently, the app needs `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` permission — but Play Store policy requires justification.

---

## Verification

```bash
# Simulate battery low on emulator
adb shell am broadcast -a android.intent.action.BATTERY_LOW

# Check enqueued work
adb shell dumpsys jobscheduler | grep "com.example"

# Force WorkManager run now (debug only)
adb shell am broadcast -a androidx.work.diagnostics.REQUEST_DIAGNOSTICS \
  --es package com.example.app
```

---

## Related

- `android-workmanager-workers-sync.md`
- `android-workmanager-background.md`
- `mobile-battery-optimization.md`
- `mobile-offline-first-sync-cloudflare-queues.md`
- `android-exact-alarm-permission-and-fallback.md`

---

## Sources

- WorkManager constraints — https://developer.android.com/topic/libraries/architecture/workmanager/how-to/define-work#work-constraints
- PowerManager thermal API — https://developer.android.com/reference/android/os/PowerManager#getCurrentThermalStatus()
- BatteryManager constants — https://developer.android.com/reference/android/os/BatteryManager
- Cloudflare D1 — https://developers.cloudflare.com/d1/
