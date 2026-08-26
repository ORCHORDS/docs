# Mobile Background Sync via Workers Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need offline-collected data on iOS and Android to sync reliably to a Cloudflare Workers backend even when the app is not in the foreground. The pattern: OS background tasks (iOS `BGAppRefreshTask`, Android `WorkManager`) post payloads to a Workers Queue HTTP endpoint; a separate Queue consumer Worker processes messages and reconciles them against D1 on the next batch delivery.

## Context

- iOS 17+ with `BackgroundTasks` framework (`BGAppRefreshTask`)
- Android API 26+ with `WorkManager` 2.9 (Kotlin)
- Cloudflare Workers Queues (producer + consumer in the same Worker module)
- D1 for server-side deduplication and reconciliation
- KV for per-device sync watermark storage

---

## Workers Queue Producer & Consumer

```typescript
// workers/src/index.ts
import type { Queue, MessageBatch } from '@cloudflare/workers-types';

export interface Env {
  SYNC_QUEUE: Queue<SyncPayload>;
  DB: D1Database;
  KV: KVNamespace;
}

export interface SyncPayload {
  deviceId: string;
  eventType: 'checkin' | 'reading' | 'action';
  payload: Record<string, unknown>;
  clientTs: number;   // Unix ms timestamp from device
  idempotencyKey: string;
}

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, X-Device-Id',
};

export default {
  // ─── HTTP handler: enqueue incoming sync events ───────────────────────────
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    if (request.url.endsWith('/sync') && request.method === 'POST') {
      const events = await request.json<SyncPayload[]>();
      if (!Array.isArray(events) || events.length === 0) {
        return new Response(JSON.stringify({ error: 'empty payload' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json', ...corsHeaders },
        });
      }

      // Batch-send to Queue (max 100 per batch call)
      const chunks = chunkArray(events, 100);
      for (const chunk of chunks) {
        await env.SYNC_QUEUE.sendBatch(
          chunk.map((e) => ({ body: e, contentType: 'json' }))
        );
      }

      return new Response(JSON.stringify({ queued: events.length }), {
        status: 202,
        headers: { 'Content-Type': 'application/json', ...corsHeaders },
      });
    }

    // Watermark endpoint: GET /sync/watermark?deviceId=xxx
    if (request.url.includes('/sync/watermark')) {
      const url = new URL(request.url);
      const deviceId = url.searchParams.get('deviceId');
      if (!deviceId) {
        return new Response(JSON.stringify({ error: 'deviceId required' }), { status: 400 });
      }
      const watermark = await env.KV.get(`wm:${deviceId}`);
      return new Response(JSON.stringify({ watermark: watermark ? Number(watermark) : 0 }), {
        headers: { 'Content-Type': 'application/json', ...corsHeaders },
      });
    }

    return new Response('Not Found', { status: 404 });
  },

  // ─── Queue consumer: process batched sync events ──────────────────────────
  async queue(batch: MessageBatch<SyncPayload>, env: Env): Promise<void> {
    const stmt = env.DB.prepare(
      `INSERT OR IGNORE INTO sync_events
         (idempotency_key, device_id, event_type, payload, client_ts, processed_at)
       VALUES (?, ?, ?, ?, ?, datetime('now'))`
    );

    const watermarks = new Map<string, number>();

    for (const message of batch.messages) {
      const e = message.body;
      try {
        await stmt
          .bind(
            e.idempotencyKey,
            e.deviceId,
            e.eventType,
            JSON.stringify(e.payload),
            e.clientTs
          )
          .run();

        // Track highest processed clientTs per device for watermark
        const prev = watermarks.get(e.deviceId) ?? 0;
        if (e.clientTs > prev) watermarks.set(e.deviceId, e.clientTs);

        message.ack();
      } catch (err) {
        console.error('Failed to process message', e.idempotencyKey, err);
        message.retry();
      }
    }

    // Persist watermarks to KV
    await Promise.all(
      Array.from(watermarks.entries()).map(([deviceId, ts]) =>
        env.KV.put(`wm:${deviceId}`, String(ts), { expirationTtl: 60 * 60 * 24 * 90 })
      )
    );
  },
};

function chunkArray<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}
```

---

## D1 Schema

```sql
-- migrations/0001_sync_events.sql
CREATE TABLE IF NOT EXISTS sync_events (
  idempotency_key TEXT    PRIMARY KEY,
  device_id       TEXT    NOT NULL,
  event_type      TEXT    NOT NULL,
  payload         TEXT    NOT NULL,  -- JSON string
  client_ts       INTEGER NOT NULL,  -- Unix ms
  processed_at    TEXT    NOT NULL
);

CREATE INDEX idx_sync_device ON sync_events(device_id, client_ts);
```

---

## wrangler.toml

```toml
name = "myapp-sync"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[queues.producers]]
binding  = "SYNC_QUEUE"
queue    = "myapp-sync-queue"

[[queues.consumers]]
queue             = "myapp-sync-queue"
max_batch_size    = 100
max_batch_timeout = 5
max_retries       = 3
dead_letter_queue = "myapp-sync-dlq"

[[d1_databases]]
binding       = "DB"
database_name = "myapp-prod"
database_id   = "<your-d1-id>"

[[kv_namespaces]]
binding = "KV"
id      = "<your-kv-id>"
```

---

## iOS BGAppRefreshTask

```swift
// iOS/BackgroundSync/SyncManager.swift
import BackgroundTasks
import Foundation

struct SyncEvent: Codable {
    let deviceId: String
    let eventType: String
    let payload: [String: String]
    let clientTs: Int
    let idempotencyKey: String
}

final class SyncManager {
    static let taskIdentifier = "com.myapp.sync"
    static let shared = SyncManager()

    private let apiBase = URL(string: ProcessInfo.processInfo.environment["API_BASE_URL"] ?? "https://sync.example.workers.dev")!

    // Call once in AppDelegate / App init
    func registerBackgroundTask() {
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: Self.taskIdentifier,
            using: nil
        ) { task in
            self.handleBackgroundSync(task: task as! BGAppRefreshTask)
        }
    }

    func scheduleNextSync() {
        let request = BGAppRefreshTaskRequest(identifier: Self.taskIdentifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60) // 15 min
        try? BGTaskScheduler.shared.submit(request)
    }

    private func handleBackgroundSync(task: BGAppRefreshTask) {
        scheduleNextSync() // Reschedule immediately

        let syncTask = Task {
            do {
                let events = LocalEventStore.shared.pendingEvents()
                guard !events.isEmpty else { task.setTaskCompleted(success: true); return }
                try await postEvents(events)
                LocalEventStore.shared.markSynced(events)
                task.setTaskCompleted(success: true)
            } catch {
                task.setTaskCompleted(success: false)
            }
        }

        task.expirationHandler = {
            syncTask.cancel()
        }
    }

    func postEvents(_ events: [SyncEvent]) async throws {
        var request = URLRequest(url: apiBase.appendingPathComponent("sync"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(events)
        request.timeoutInterval = 20
        let (_, response) = try await URLSession.shared.data(for: request)
        guard (response as? HTTPURLResponse)?.statusCode == 202 else {
            throw URLError(.badServerResponse)
        }
    }
}
```

---

## Android WorkManager (Kotlin)

```kotlin
// android/app/src/main/java/com/myapp/sync/SyncWorker.kt
package com.myapp.sync

import android.content.Context
import androidx.work.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import java.util.concurrent.TimeUnit

class SyncWorker(context: Context, params: WorkerParameters) :
    CoroutineWorker(context, params) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .build()

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        try {
            val events = LocalEventStore.getPendingEvents(applicationContext)
            if (events.isEmpty()) return@withContext Result.success()

            val body = JSONArray(events.map { it.toJsonObject() }).toString()
                .toRequestBody("application/json".toMediaType())

            val apiBase = applicationContext
                .getString(R.string.api_base_url)

            val request = Request.Builder()
                .url("$apiBase/sync")
                .post(body)
                .build()

            val response = client.newCall(request).execute()
            if (!response.isSuccessful) return@withContext Result.retry()

            LocalEventStore.markSynced(applicationContext, events)
            Result.success()
        } catch (e: Exception) {
            if (runAttemptCount < 3) Result.retry() else Result.failure()
        }
    }

    companion object {
        fun schedule(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val request = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .setBackoffCriteria(
                    BackoffPolicy.EXPONENTIAL,
                    WorkRequest.MIN_BACKOFF_MILLIS,
                    TimeUnit.MILLISECONDS
                )
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                "background_sync",
                ExistingPeriodicWorkPolicy.KEEP,
                request
            )
        }
    }
}
```

---

## Idempotency Key Generation (Shared)

```typescript
// Shared utility for both mobile (via Expo) and testing
// UUID v4 prefixed with event type + clientTs ensures uniqueness
export function makeIdempotencyKey(deviceId: string, eventType: string, clientTs: number): string {
  const rand = Math.random().toString(36).slice(2, 10);
  return `${deviceId}-${eventType}-${clientTs}-${rand}`;
}
```

---

## Anti-patterns

- Do NOT post events one-at-a-time from background tasks — batch them to reduce wake-up network round trips.
- Do NOT rely on the OS granting background time; always persist events locally first and sync opportunistically.
- Do NOT use `INSERT OR REPLACE` in D1 — it deletes and re-inserts, breaking foreign key relations; use `INSERT OR IGNORE` with the idempotency key as the primary key.
- Do NOT set `max_batch_timeout` to 0 — allow a few seconds for the queue to accumulate messages before flushing.

## Gotchas

- iOS `BGAppRefreshTask` does NOT guarantee execution at the requested interval; the OS throttles it based on app usage patterns.
- Android WorkManager minimum periodic interval is 15 minutes; shorter intervals are clamped.
- Cloudflare Queues deliver `at-least-once` — always implement idempotency via `INSERT OR IGNORE` on a unique key.
- `message.retry()` in the consumer re-enqueues the message; call it only for transient failures, not logic errors.
- KV watermarks can be stale by up to 60 seconds globally; do not rely on them for strict ordering.

---

## Verification

```bash
# Post test events to the sync endpoint
curl -s -X POST http://localhost:8787/sync \
  -H 'Content-Type: application/json' \
  -d '[{"deviceId":"dev-001","eventType":"checkin","payload":{},"clientTs":1724520000000,"idempotencyKey":"dev-001-checkin-1724520000000-abc123"}]'

# Check watermark
curl -s 'http://localhost:8787/sync/watermark?deviceId=dev-001' | jq .

# Inspect D1 for processed events
npx wrangler d1 execute myapp-prod --local \
  --command "SELECT idempotency_key, event_type, processed_at FROM sync_events LIMIT 10"

# Check DLQ for failed messages
npx wrangler queues list
```

---

## Related

- `documentation/categories/mobile/workers-expo-router-api-routes-d1.md`
- `documentation/categories/mobile/workers-ios-swift-async-d1-api.md`
- `documentation/categories/mobile/workers-flutter-riverpod-api-client.md`

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://developer.apple.com/documentation/backgroundtasks/bgapprefreshtas
- https://developer.android.com/topic/libraries/architecture/workmanager
- https://developers.cloudflare.com/queues/reference/consumer-concurrency/
