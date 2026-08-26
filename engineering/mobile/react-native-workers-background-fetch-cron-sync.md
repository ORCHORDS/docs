# React Native Background Fetch with Cloudflare Workers Cron Sync

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

Your React Native app needs to sync data periodically in the background — refreshing a content feed, pre-fetching user preferences, updating cached route data — without requiring the app to be open. You are using `react-native-background-fetch` but the Worker backend doesn't know when devices are actively syncing, which jobs have already run, or how to avoid redundant writes when multiple devices fetch the same content. You need a coordinated system where the Worker schedules work and records completion, and the client reports results back so the Worker can skip identical fetches.

---

## Context

`react-native-background-fetch` (by Transistor Software) provides a cross-platform background fetch API that works on both iOS (`BGAppRefreshTask`) and Android (`JobScheduler` / WorkManager). It fires a callback every 15–30 minutes when the OS grants background time.

The coordination problem: if a Worker generates a "sync manifest" — a versioned list of data the client should fetch — clients only re-fetch when the manifest version changes. This prevents unnecessary DB writes and bandwidth on both sides.

Manifest versions are stored in KV and checked via a lightweight `HEAD` request before the client downloads anything. The Worker also records per-device sync history in D1 for debugging and analytics.

```toml
# wrangler.toml
name = "bg-sync-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "MANIFESTS"
id = "YOUR_KV_NAMESPACE_ID"

[[d1_databases]]
binding = "DB"
database_name = "sync_history"
database_id = "YOUR_D1_DATABASE_ID"

[triggers]
crons = ["*/15 * * * *"]
```

---

## 1. D1 Schema

```sql
-- migrations/0001_sync_history.sql
CREATE TABLE IF NOT EXISTS sync_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id   TEXT NOT NULL,
  user_id     TEXT NOT NULL,
  manifest_v  TEXT NOT NULL,
  synced_at   INTEGER NOT NULL,
  duration_ms INTEGER,
  status      TEXT NOT NULL DEFAULT 'ok'
);

CREATE INDEX IF NOT EXISTS idx_se_device ON sync_events (device_id, synced_at DESC);
```

---

## 2. Worker: Manifest Generation (Cron)

```typescript
// src/index.ts
export interface Env {
  MANIFESTS: KVNamespace;
  DB: D1Database;
}

interface SyncManifest {
  version: string;       // SHA-256 hash of the payload
  generatedAt: number;
  items: ManifestItem[];
}

interface ManifestItem {
  key: string;
  url: string;           // Worker-relative path
  cacheSeconds: number;
}

async function generateManifest(env: Env): Promise<SyncManifest> {
  // In production: query D1 for changed content since last manifest
  const items: ManifestItem[] = [
    { key: "feed_v2", url: "/sync/feed", cacheSeconds: 900 },
    { key: "user_prefs", url: "/sync/prefs", cacheSeconds: 3600 },
    { key: "route_cache", url: "/sync/routes", cacheSeconds: 1800 },
  ];

  const payload = JSON.stringify(items);
  const hashBuffer = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(payload),
  );
  const version = Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16);

  return { version, generatedAt: Date.now(), items };
}

export default {
  // Cron: regenerate and store manifest every 15 minutes
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const manifest = await generateManifest(env);
    await env.MANIFESTS.put("current", JSON.stringify(manifest), {
      expirationTtl: 60 * 60, // 1 hour safety TTL
    });
    console.log(`Manifest ${manifest.version} published at ${manifest.generatedAt}`);
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const { pathname } = url;

    // HEAD /sync/manifest  — lightweight version check
    if (request.method === "HEAD" && pathname === "/sync/manifest") {
      const manifest = await env.MANIFESTS.get<SyncManifest>("current", "json");
      if (!manifest) return new Response(null, { status: 503 });
      return new Response(null, {
        headers: {
          "x-manifest-version": manifest.version,
          "x-manifest-age": String(Math.floor((Date.now() - manifest.generatedAt) / 1000)),
          "cache-control": "public, max-age=60",
        },
      });
    }

    // GET /sync/manifest  — full manifest payload
    if (request.method === "GET" && pathname === "/sync/manifest") {
      const manifest = await env.MANIFESTS.get<SyncManifest>("current", "json");
      if (!manifest) return new Response(JSON.stringify({ error: "Not ready" }), { status: 503 });
      return new Response(JSON.stringify(manifest), {
        headers: {
          "content-type": "application/json",
          "x-manifest-version": manifest.version,
          "cache-control": "public, max-age=60",
        },
      });
    }

    // POST /sync/complete  — client reports sync completion
    if (request.method === "POST" && pathname === "/sync/complete") {
      const body = await request.json<{
        deviceId: string;
        userId: string;
        manifestVersion: string;
        durationMs: number;
        status: "ok" | "partial" | "error";
      }>();

      await env.DB.prepare(
        `INSERT INTO sync_events (device_id, user_id, manifest_v, synced_at, duration_ms, status)
         VALUES (?, ?, ?, ?, ?, ?)`,
      )
        .bind(
          body.deviceId,
          body.userId,
          body.manifestVersion,
          Date.now(),
          body.durationMs,
          body.status,
        )
        .run();

      return new Response(JSON.stringify({ ok: true }), {
        headers: { "content-type": "application/json" },
      });
    }

    // Data endpoints referenced in manifest items
    if (pathname === "/sync/feed" && request.method === "GET") {
      // Return serialized feed data — implement per your data model
      return new Response(JSON.stringify({ feed: [] }), {
        headers: { "content-type": "application/json", "cache-control": "public, max-age=900" },
      });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

---

## 3. React Native: Background Fetch Configuration

```typescript
// src/backgroundSync.ts
import BackgroundFetch from "react-native-background-fetch";
import { getDeviceId } from "react-native-device-info";
import AsyncStorage from "@react-native-async-storage/async-storage";

const API_BASE = "https://bg-sync-api.YOUR_ACCOUNT.workers.dev";
const LAST_MANIFEST_KEY = "@sync:lastManifestVersion";

export async function configureBackgroundFetch(userId: string): Promise<void> {
  await BackgroundFetch.configure(
    {
      minimumFetchInterval: 15,        // minutes (iOS minimum)
      stopOnTerminate: false,
      startOnBoot: true,
      enableHeadless: true,
      requiresNetworkConnectivity: true,
      requiredNetworkType: BackgroundFetch.NETWORK_TYPE_ANY,
    },
    async (taskId) => {
      console.log("[BackgroundFetch] task:", taskId);
      await runSyncTask(userId);
      BackgroundFetch.finish(taskId);
    },
    (taskId) => {
      // OS timed out the task — finish immediately
      console.warn("[BackgroundFetch] timeout:", taskId);
      BackgroundFetch.finish(taskId);
    },
  );
}

async function runSyncTask(userId: string): Promise<void> {
  const deviceId = await getDeviceId();
  const start = Date.now();
  let status: "ok" | "partial" | "error" = "ok";

  try {
    // 1. Lightweight version check — avoid downloading if unchanged
    const headResponse = await fetch(`${API_BASE}/sync/manifest`, {
      method: "HEAD",
      headers: { "x-user-id": userId },
    });
    const remoteVersion = headResponse.headers.get("x-manifest-version");
    const lastVersion = await AsyncStorage.getItem(LAST_MANIFEST_KEY);

    if (remoteVersion && remoteVersion === lastVersion) {
      console.log("[BackgroundFetch] manifest unchanged, skipping sync");
      return;
    }

    // 2. Fetch full manifest
    const manifestResponse = await fetch(`${API_BASE}/sync/manifest`, {
      headers: { "x-user-id": userId },
    });
    const manifest = await manifestResponse.json<{
      version: string;
      items: Array<{ key: string; url: string; cacheSeconds: number }>;
    }>();

    // 3. Fetch each item in parallel, write to AsyncStorage
    const results = await Promise.allSettled(
      manifest.items.map(async (item) => {
        const dataResponse = await fetch(`${API_BASE}${item.url}`, {
          headers: { "x-user-id": userId },
        });
        const data = await dataResponse.text();
        await AsyncStorage.setItem(`@sync:${item.key}`, data);
        await AsyncStorage.setItem(
          `@sync:${item.key}:expires`,
          String(Date.now() + item.cacheSeconds * 1000),
        );
      }),
    );

    const failed = results.filter((r) => r.status === "rejected").length;
    status = failed === 0 ? "ok" : failed < results.length ? "partial" : "error";

    if (status !== "error") {
      await AsyncStorage.setItem(LAST_MANIFEST_KEY, manifest.version);
    }

    // 4. Report completion back to Worker
    await fetch(`${API_BASE}/sync/complete`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        deviceId,
        userId,
        manifestVersion: manifest.version,
        durationMs: Date.now() - start,
        status,
      }),
    });
  } catch (err) {
    console.error("[BackgroundFetch] error:", err);
    status = "error";
  }
}
```

---

## 4. Headless Task (Android Background-Only)

```typescript
// index.js — register headless task at app entry point
import BackgroundFetch from "react-native-background-fetch";
import { runSyncTask } from "./src/backgroundSync";

// Called when app is terminated on Android
const headlessTask = async (event: { taskId: string }) => {
  console.log("[BackgroundFetch headless] task:", event.taskId);
  const userId = "STORED_USER_ID"; // retrieve from encrypted storage
  await runSyncTask(userId);
  BackgroundFetch.finish(event.taskId);
};

BackgroundFetch.registerHeadlessTask(headlessTask);
```

---

## 5. Reading Cached Sync Data in the App

```typescript
// src/hooks/useSyncedData.ts
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useEffect, useState } from "react";

export function useSyncedData<T>(key: string): { data: T | null; stale: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [stale, setStale] = useState(false);

  useEffect(() => {
    (async () => {
      const raw = await AsyncStorage.getItem(`@sync:${key}`);
      const expiresRaw = await AsyncStorage.getItem(`@sync:${key}:expires`);
      if (!raw) return;
      setData(JSON.parse(raw) as T);
      setStale(expiresRaw ? Date.now() > Number(expiresRaw) : true);
    })();
  }, [key]);

  return { data, stale };
}
```

---

## Anti-Patterns

- **Fetching data unconditionally on every background fetch** — always check `x-manifest-version` first. Background fetch budget on iOS is finite and the OS deprioritises apps that waste it.
- **Writing to AsyncStorage on every fetch regardless of change** — unnecessary writes wake the JS thread and delay the battery-sensitive background task.
- **Making the background task await a slow analytics call** — call `BackgroundFetch.finish(taskId)` as soon as sync data is written; fire the completion POST asynchronously afterward.
- **Using MMKV in headless Android tasks** — MMKV requires a React Native instance; in headless mode use AsyncStorage or SQLite.

---

## Gotchas

- iOS grants background fetch roughly every 15 minutes but the actual frequency is learned from usage patterns. Apps that the OS considers low-engagement may receive fetch events less often than `minimumFetchInterval` suggests.
- Android 12+ restricts exact alarms; WorkManager (which BackgroundFetch uses internally) uses inexact scheduling. Do not assume precise 15-minute intervals.
- KV `expirationTtl` on the manifest key ensures stale manifests are not served indefinitely if the Cron trigger fails. Set it to 2× the cron interval minimum (30 minutes for a 15-minute cron).
- `getDeviceId()` from `react-native-device-info` may return `"unknown"` in certain simulator configurations. Gate the D1 insert to reject that value.

---

## Verification

1. Use `BackgroundFetch.scheduleTask({ taskId: "com.example.test", delay: 5000, periodic: false })` in dev to trigger a task immediately without waiting for the OS scheduler.
2. Watch `wrangler tail` for `/sync/manifest` HEAD requests and `/sync/complete` POSTs.
3. Query D1: `SELECT * FROM sync_events ORDER BY synced_at DESC LIMIT 10` to confirm records are written.
4. Change a feed item, regenerate the manifest (trigger the Cron manually with `wrangler cron trigger`), and verify the next background fetch downloads updated data.

---

## Related

- `ios-background-fetch.md`
- `android-workmanager-background.md`
- `android-workmanager-workers-sync.md`
- `react-native-workers-offline-queue-sync.md`
- `mobile-offline-first-sync-cloudflare-queues.md`
- `mobile-battery-optimization.md`

---

## Sources

- react-native-background-fetch: https://github.com/transistorsoft/react-native-background-fetch
- Cloudflare Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- iOS BGAppRefreshTask: https://developer.apple.com/documentation/backgroundtasks/bgapprefreshtask
- Android WorkManager: https://developer.android.com/topic/libraries/architecture/workmanager
