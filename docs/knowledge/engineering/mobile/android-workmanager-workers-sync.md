# Android WorkManager + Cloudflare Workers Background Sync

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

Your Android app needs to reliably sync data to a Cloudflare Workers API endpoint even when the app is closed, the network is intermittent, or the device is in battery-saver mode. You need exponential back-off retries, constraint-based scheduling (only sync on WiFi or when charging), and the ability to inspect the sync result from a Workers-backed status endpoint — all without Firebase.

---

## Context

WorkManager is Android's recommended solution for deferrable, guaranteed background work. It persists work across app restarts and device reboots and respects battery optimisation constraints. When combined with Cloudflare Workers, the sync architecture is:

1. **Enqueue**: app enqueues a `SyncWorker` with network constraints.
2. **Execute**: WorkManager runs `SyncWorker` in the background; it POSTs a delta payload to a Workers API.
3. **Acknowledge**: the Worker writes the result to KV and returns a job ID.
4. **Poll** (optional): the app polls the Workers `/status/:jobId` endpoint to surface the result in UI.

WorkManager retries failed work using exponential back-off; the Worker is idempotent via a client-generated idempotency key.

---

## 1. Add WorkManager Dependency

```kotlin
// app/build.gradle.kts
dependencies {
    implementation("androidx.work:work-runtime-ktx:2.9.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
}
```

---

## 2. SyncWorker Implementation

```kotlin
// app/src/main/java/com/example/sync/SyncWorker.kt
package com.example.sync

import android.content.Context
import androidx.work.*
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

class SyncWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    @Serializable
    data class SyncPayload(
        val idempotencyKey: String,
        val userId: String,
        val records: List<String>,
        val clientTs: Long,
    )

    override suspend fun doWork(): Result {
        val userId = inputData.getString(KEY_USER_ID) ?: return Result.failure()
        val idempotencyKey = inputData.getString(KEY_IDEMPOTENCY_KEY)
            ?: return Result.failure()

        val pendingRecords = fetchPendingRecordsFromLocalDb()

        val payload = SyncPayload(
            idempotencyKey = idempotencyKey,
            userId = userId,
            records = pendingRecords,
            clientTs = System.currentTimeMillis(),
        )

        return try {
            val jobId = postToWorker(payload)
            // Persist jobId for status polling
            SyncPrefs.saveLastJobId(applicationContext, jobId)
            Result.success(
                workDataOf(KEY_JOB_ID to jobId)
            )
        } catch (e: IOException) {
            if (runAttemptCount < 4) Result.retry() else Result.failure()
        }
    }

    private fun fetchPendingRecordsFromLocalDb(): List<String> {
        // Replace with your Room DAO call
        return listOf("record_a", "record_b")
    }

    private fun postToWorker(payload: SyncPayload): String {
        val body = Json.encodeToString(payload)
            .toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url("https://sync.example.workers.dev/sync")
            .addHeader("Authorization", "Bearer ${SyncPrefs.getToken(applicationContext)}")
            .post(body)
            .build()

        httpClient.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("Sync failed: ${response.code}")
            val responseJson = Json.decodeFromString<Map<String, String>>(
                response.body!!.string()
            )
            return responseJson["jobId"] ?: throw IOException("Missing jobId in response")
        }
    }

    companion object {
        const val KEY_USER_ID          = "user_id"
        const val KEY_IDEMPOTENCY_KEY  = "idempotency_key"
        const val KEY_JOB_ID           = "job_id"
    }
}
```

---

## 3. Enqueue Sync with Constraints

```kotlin
// app/src/main/java/com/example/sync/SyncScheduler.kt
package com.example.sync

import android.content.Context
import androidx.work.*
import java.util.UUID
import java.util.concurrent.TimeUnit

object SyncScheduler {

    fun enqueueImmediate(context: Context, userId: String) {
        val idempotencyKey = UUID.randomUUID().toString()

        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        val workRequest = OneTimeWorkRequestBuilder<SyncWorker>()
            .setConstraints(constraints)
            .setInputData(
                workDataOf(
                    SyncWorker.KEY_USER_ID         to userId,
                    SyncWorker.KEY_IDEMPOTENCY_KEY to idempotencyKey,
                )
            )
            .setBackoffCriteria(
                BackoffPolicy.EXPONENTIAL,
                WorkRequest.MIN_BACKOFF_MILLIS,
                TimeUnit.MILLISECONDS
            )
            .addTag("sync")
            .build()

        WorkManager.getInstance(context)
            .enqueueUniqueWork(
                "user-sync-$userId",
                ExistingWorkPolicy.KEEP,  // don't replace an in-flight sync
                workRequest
            )
    }

    fun schedulePeriodic(context: Context, userId: String) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.UNMETERED) // WiFi only for periodic
            .setRequiresBatteryNotLow(true)
            .build()

        val request = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(constraints)
            .setInputData(workDataOf(
                SyncWorker.KEY_USER_ID to userId,
                SyncWorker.KEY_IDEMPOTENCY_KEY to UUID.randomUUID().toString(),
            ))
            .addTag("sync-periodic")
            .build()

        WorkManager.getInstance(context)
            .enqueueUniquePeriodicWork(
                "periodic-sync-$userId",
                ExistingPeriodicWorkPolicy.KEEP,
                request
            )
    }
}
```

---

## 4. Cloudflare Worker — Idempotent Sync Endpoint

```typescript
// workers/sync/src/index.ts
export interface Env {
  SYNC_KV: KVNamespace;
}

interface SyncPayload {
  idempotencyKey: string;
  userId: string;
  records: string[];
  clientTs: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/sync") {
      return handleSync(request, env);
    }
    if (request.method === "GET" && url.pathname.startsWith("/status/")) {
      const jobId = url.pathname.split("/").pop()!;
      return handleStatus(jobId, env);
    }
    return new Response("Not found", { status: 404 });
  },
};

async function handleSync(request: Request, env: Env): Promise<Response> {
  const payload = await request.json<SyncPayload>();

  // Idempotency: if we've already processed this key, return the cached result
  const cached = await env.SYNC_KV.get(`idempotency:${payload.idempotencyKey}`);
  if (cached) {
    return Response.json(JSON.parse(cached));
  }

  const jobId = crypto.randomUUID();
  const result = {
    jobId,
    userId: payload.userId,
    recordsProcessed: payload.records.length,
    processedAt: new Date().toISOString(),
    status: "ok",
  };

  // Store idempotency record for 24 h
  await env.SYNC_KV.put(
    `idempotency:${payload.idempotencyKey}`,
    JSON.stringify(result),
    { expirationTtl: 86_400 }
  );

  // Store job status for polling
  await env.SYNC_KV.put(`job:${jobId}`, JSON.stringify(result), {
    expirationTtl: 86_400,
  });

  return Response.json(result);
}

async function handleStatus(jobId: string, env: Env): Promise<Response> {
  const status = await env.SYNC_KV.get(`job:${jobId}`, "json");
  if (!status) return Response.json({ error: "job not found" }, { status: 404 });
  return Response.json(status);
}
```

---

## Anti-Patterns

- **Using `Worker` instead of `CoroutineWorker` for network calls.** `Worker.doWork()` runs on a background thread pool but lacks structured cancellation. Use `CoroutineWorker` so the work can be cancelled cleanly when WorkManager needs to stop it.
- **Not using `enqueueUniqueWork`.** Enqueuing the same sync task repeatedly without a unique name creates duplicate in-flight syncs. Always use `enqueueUniqueWork` with `KEEP` or `REPLACE` policy.
- **Generating the idempotency key inside `doWork()`.** If WorkManager retries the job, a new key is generated each time, defeating idempotency. Generate the key before enqueuing and pass it via `inputData`.
- **Setting constraints to `NetworkType.NOT_REQUIRED`.** Without a network constraint the job may attempt to run offline and burn retries. Always require at least `NetworkType.CONNECTED`.

---

## Gotchas

- **15-minute minimum for `PeriodicWorkRequest`.** WorkManager enforces a minimum repeat interval of 15 minutes; shorter values are rounded up.
- **WorkManager and Doze mode.** In Doze mode Android batches background tasks into maintenance windows. Your Worker may not run immediately even when the network is available. Use `setExpedited()` for time-sensitive syncs (requires a foreground service notification on Android 12+).
- **`ExistingWorkPolicy.REPLACE` cancels the running Worker.** If an in-flight upload is cancelled mid-stream the server may receive a partial body. Use idempotency keys and `KEEP` policy, not `REPLACE`.
- **KV eventual consistency on the Workers side.** A status poll immediately after enqueuing may return 404 if the Worker's KV write hasn't propagated. Add a 1-second delay before the first poll.

---

## Verification

```bash
# 1. Deploy Worker
wrangler deploy

# 2. Simulate a sync POST with a fixed idempotency key
IDEM_KEY="test-key-$(date +%s)"
curl -X POST "https://sync.example.workers.dev/sync" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"idempotencyKey\":\"$IDEM_KEY\",\"userId\":\"u1\",\"records\":[\"r1\",\"r2\"],\"clientTs\":$(date +%s)000}"

# 3. Send the same request again — should return the cached result with the same jobId
curl -X POST "https://sync.example.workers.dev/sync" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"idempotencyKey\":\"$IDEM_KEY\",\"userId\":\"u1\",\"records\":[\"r1\",\"r2\"],\"clientTs\":$(date +%s)001}"

# 4. Poll job status
JOB_ID="<jobId from step 2>"
curl "https://sync.example.workers.dev/status/$JOB_ID"
```

---

## Related

- `android-workmanager-background.md`
- `android-workers-paging3-cursor-pagination.md`
- `mobile-offline-first-sync-cloudflare-queues.md`
- `mobile-network-resilience-cloudflare-workers.md`
- `android-foreground-service-restrictions.md`

---

## Sources

- WorkManager guide — https://developer.android.com/develop/background-work/background-tasks/persistent/getting-started
- `CoroutineWorker` — https://developer.android.com/reference/androidx/work/CoroutineWorker
- `enqueueUniqueWork` — https://developer.android.com/reference/androidx/work/WorkManager#enqueueUniqueWork
- Cloudflare KV — https://developers.cloudflare.com/kv/
- WorkManager constraints — https://developer.android.com/develop/background-work/background-tasks/persistent/getting-started/define-work#work-constraints
