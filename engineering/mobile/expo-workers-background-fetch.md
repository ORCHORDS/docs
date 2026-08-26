# Expo BackgroundFetch Syncing to Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
An Expo app needs to refresh data (unread counts, draft orders, location traces) while backgrounded, and sync those changes to a Cloudflare Workers API so the server always has a recent snapshot even if the user never foregrounds the app.

## Context
Expo's `expo-background-fetch` module wraps iOS `BGAppRefreshTask` and Android `WorkManager` behind a single JS API. The system decides when the task actually runs (usually every 15+ minutes at minimum), but you can register a task that calls your Workers endpoint, processes the response, and stores results with `expo-sqlite` or `expo-secure-store`. Workers returns data in under 50 ms from edge PoPs so the task completes well within the OS budget.

## Registering the Background Task

```typescript
// tasks/backgroundSync.ts
import * as BackgroundFetch from 'expo-background-fetch';
import * as TaskManager from 'expo-task-manager';
import * as SecureStore from 'expo-secure-store';
import { syncWithWorkers } from '../api/workers';
import { localDb } from '../db/localDb';

export const BACKGROUND_SYNC_TASK = 'WORKERS_BACKGROUND_SYNC';

// Define the task at module scope — must execute before registerAsync
TaskManager.defineTask(BACKGROUND_SYNC_TASK, async () => {
  try {
    const token = await SecureStore.getItemAsync('auth_token');
    if (!token) return BackgroundFetch.BackgroundFetchResult.NoData;

    const lastSync = await localDb.getLastSyncTimestamp();
    const result = await syncWithWorkers(token, lastSync);

    if (result.records.length === 0) {
      return BackgroundFetch.BackgroundFetchResult.NoData;
    }

    await localDb.upsertRecords(result.records);
    await localDb.setLastSyncTimestamp(result.serverTime);

    return BackgroundFetch.BackgroundFetchResult.NewData;
  } catch (err) {
    console.error('[BackgroundSync] failed:', err);
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

export async function registerBackgroundSync(): Promise<void> {
  const status = await BackgroundFetch.getStatusAsync();

  if (
    status === BackgroundFetch.BackgroundFetchStatus.Restricted ||
    status === BackgroundFetch.BackgroundFetchStatus.Denied
  ) {
    console.warn('[BackgroundSync] Background fetch not available');
    return;
  }

  const isRegistered = await TaskManager.isTaskRegisteredAsync(BACKGROUND_SYNC_TASK);
  if (!isRegistered) {
    await BackgroundFetch.registerTaskAsync(BACKGROUND_SYNC_TASK, {
      minimumInterval: 15 * 60, // 15 minutes — iOS enforces this minimum
      stopOnTerminate: false,   // continue after force-quit (Android only)
      startOnBoot: true,        // restart on device reboot (Android only)
    });
  }
}
```

## Workers Sync Endpoint

```typescript
// worker/src/sync.ts
import { Env } from './types';

interface SyncRequest {
  lastSync: number; // epoch ms
}

interface SyncResponse {
  records: SyncRecord[];
  serverTime: number;
}

interface SyncRecord {
  id: string;
  type: 'order' | 'notification' | 'inventory';
  data: unknown;
  updatedAt: number;
}

export async function handleSync(request: Request, env: Env): Promise<Response> {
  const authHeader = request.headers.get('Authorization') ?? '';
  const token = authHeader.replace('Bearer ', '');

  // Verify JWT (use your own verifier)
  const payload = await verifyJwt(token, env.JWT_SECRET);
  if (!payload) return new Response('Unauthorized', { status: 401 });

  const body = await request.json<SyncRequest>();
  const { lastSync } = body;

  const { results } = await env.DB.prepare(
    `SELECT id, type, data, updated_at AS updatedAt
     FROM sync_records
     WHERE user_id = ? AND updated_at > ?
     ORDER BY updated_at ASC
     LIMIT 500`
  )
    .bind(payload.sub, lastSync)
    .all<SyncRecord>();

  const response: SyncResponse = {
    records: results,
    serverTime: Date.now(),
  };

  return Response.json(response, {
    headers: { 'Cache-Control': 'no-store' },
  });
}

async function verifyJwt(
  token: string,
  secret: string
): Promise<{ sub: string } | null> {
  try {
    const key = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(secret),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['verify']
    );
    const [headerB64, payloadB64, sigB64] = token.split('.');
    const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
    const sig = Uint8Array.from(atob(sigB64.replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0));
    const valid = await crypto.subtle.verify('HMAC', key, sig, data);
    if (!valid) return null;
    return JSON.parse(atob(payloadB64)) as { sub: string };
  } catch {
    return null;
  }
}
```

## Client-side API Wrapper

```typescript
// api/workers.ts
const WORKERS_BASE = 'https://api.example.com';

export interface SyncResult {
  records: { id: string; type: string; data: unknown; updatedAt: number }[];
  serverTime: number;
}

export async function syncWithWorkers(
  token: string,
  lastSync: number
): Promise<SyncResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20_000); // background tasks have ~25 s budget

  try {
    const res = await fetch(`${WORKERS_BASE}/sync`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ lastSync }),
      signal: controller.signal,
    });

    if (!res.ok) throw new Error(`Sync failed: ${res.status}`);
    return res.json() as Promise<SyncResult>;
  } finally {
    clearTimeout(timeout);
  }
}
```

## App Startup Registration

```typescript
// App.tsx
import { useEffect } from 'react';
import { registerBackgroundSync } from './tasks/backgroundSync';

export default function App() {
  useEffect(() => {
    // Register once on mount; idempotent if already registered
    registerBackgroundSync().catch(console.error);
  }, []);

  return <RootNavigator />;
}
```

## Anti-patterns
- Awaiting long-running operations without an abort timeout — OS will kill the task if it runs too long
- Registering `minimumInterval` below 900 seconds — iOS silently ignores shorter intervals
- Making multiple sequential Workers round-trips inside one task — batch everything into one request
- Storing auth tokens in AsyncStorage — use `expo-secure-store` so the token is available in background tasks
- Calling `registerTaskAsync` every render — check `isTaskRegisteredAsync` first to avoid duplicate registration

## Gotchas
- iOS does not guarantee execution time; the minimum interval is a lower bound, not a period
- On iOS the task runs in a separate JSC context — module-level singletons from the main app are not shared
- Android `stopOnTerminate: false` only works if the user has not force-stopped the app from Settings
- `BackgroundFetch.BackgroundFetchResult.Failed` tells the OS to back off scheduling — use it only for genuine failures
- Expo Go does not support background fetch on iOS; test on a standalone build or dev client

## Verification

```bash
# Trigger background fetch immediately on a connected Android device
adb shell cmd jobscheduler run -f com.example.myapp <job-id>

# iOS: In Xcode, Simulate Background Fetch
# Debug > Simulate Background Fetch

# Check last result
npx expo run:ios --device
# Then in device logs:
xcrun simctl spawn booted log stream --predicate 'process == "YourApp"' --level debug
```

```typescript
// Check registration status at runtime
import * as BackgroundFetch from 'expo-background-fetch';
import * as TaskManager from 'expo-task-manager';

const status = await BackgroundFetch.getStatusAsync();
const registered = await TaskManager.isTaskRegisteredAsync('WORKERS_BACKGROUND_SYNC');
console.log({ status, registered });
```

## Related
- `react-native-workers-background-fetch-cron-sync.md` — same pattern with React Native bare workflow
- `ios-background-fetch.md` — iOS-specific BGAppRefreshTask details
- `mobile-battery-optimization.md` — minimizing battery impact of background tasks
- `expo-notifications-workers-scheduled-push-d1.md` — push-triggered foreground sync alternative
- `react-native-workers-offline-queue-sync.md` — queuing mutations for replay when online

## Sources
- https://docs.expo.dev/versions/latest/sdk/background-fetch/
- https://docs.expo.dev/versions/latest/sdk/task-manager/
- https://developer.apple.com/documentation/backgroundtasks/bgapprefreshtask
- https://developers.cloudflare.com/workers/runtime-apis/handlers/fetch/
- https://developers.cloudflare.com/d1/api/worker-api/
