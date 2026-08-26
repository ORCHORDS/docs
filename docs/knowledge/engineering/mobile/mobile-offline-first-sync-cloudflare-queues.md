# Mobile Offline-First Sync with Cloudflare Queues

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

User actions (posts, reactions, follows) performed while offline in the example project app are silently
dropped when connectivity returns. Alternatively, duplicate mutations appear because the offline
queue is flushed multiple times on a flaky connection. Conflict resolution between local optimistic
state and the authoritative D1 database produces inconsistent UI states after sync.

## Context

example project targets anonymous social engagement where content creation must feel instant. The offline-first
architecture queues mutations locally (AsyncStorage on React Native, IndexedDB in the Capacitor PWA
WebView) and drains the queue via a Cloudflare Queue consumer Worker when the device reconnects.
D1 acts as the authoritative store; the Queue provides at-least-once delivery with idempotency
enforced by a `mutation_id` column.

## Architecture Overview

```
+------------------+         offline queue          +------------------+
| React Native /   |  AsyncStorage / IndexedDB       | Cloudflare Queue |
| Capacitor        | ==============================> | (example project-mutations) |
|                  |  on reconnect: batch flush       +--------+---------+
|  optimistic UI   |                                           |  consume
|  local state     |  <---- sync response (SSE/poll) ----+    v
+------------------+                                     | Worker consumer|
                                                         +--------+-------+
                                                                  | write
                                                                  v
                                                         +----------------+
                                                         | D1 Database    |
                                                         | (example project-db)      |
                                                         +----------------+
```

## Local Queue Schema (AsyncStorage / IndexedDB)

```typescript
// src/lib/offline/queue.ts
export interface QueuedMutation {
  mutationId: string;    // UUID — idempotency key
  type: "post" | "react" | "follow" | "delete";
  payload: unknown;
  createdAt: number;     // epoch ms
  attempts: number;
  lastAttemptAt: number | null;
}

const QUEUE_KEY = "example project:offline_queue";

export async function enqueue(
  type: QueuedMutation["type"],
  payload: unknown
): Promise<string> {
  const mutationId = crypto.randomUUID();
  const mutation: QueuedMutation = {
    mutationId,
    type,
    payload,
    createdAt: Date.now(),
    attempts: 0,
    lastAttemptAt: null,
  };
  const queue = await loadQueue();
  queue.push(mutation);
  await saveQueue(queue);
  return mutationId;
}

async function loadQueue(): Promise<QueuedMutation[]> {
  // React Native: AsyncStorage
  const raw = await AsyncStorage.getItem(QUEUE_KEY);
  return raw ? JSON.parse(raw) : [];
}

async function saveQueue(queue: QueuedMutation[]): Promise<void> {
  await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
}
```

## Queue Flush on Reconnect

```typescript
// src/lib/offline/sync.ts
import NetInfo from "@react-native-community/netinfo";

const MAX_ATTEMPTS = 5;
const BACKOFF_BASE_MS = 1000;
let flushInProgress = false;

export function startSyncListener(): () => void {
  const unsub = NetInfo.addEventListener(async (state) => {
    if (state.isConnected && !flushInProgress) {
      await flushQueue();
    }
  });
  return unsub;
}

async function flushQueue(): Promise<void> {
  flushInProgress = true;
  try {
    const queue = await loadQueue();
    if (queue.length === 0) return;

    const batch = queue.filter(
      (m) =>
        m.attempts < MAX_ATTEMPTS &&
        (m.lastAttemptAt === null ||
          Date.now() - m.lastAttemptAt > BACKOFF_BASE_MS * 2 ** m.attempts)
    );

    if (batch.length === 0) return;

    // Send entire batch to Worker in one request
    const res = await fetch("https://api.example.com/v1/sync/mutations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mutations: batch }),
    });

    if (!res.ok) {
      await markAttemptsIncremented(batch.map((m) => m.mutationId));
      return;
    }

    const { accepted, rejected } = await res.json<{
      accepted: string[];
      rejected: { mutationId: string; reason: string }[];
    }>();

    await removeFromQueue(accepted);
    await handleRejected(rejected);
  } finally {
    flushInProgress = false;
  }
}
```

## Cloudflare Queue Producer (Worker Ingestion)

```typescript
// worker/src/routes/sync.ts
export async function handleMutationBatch(
  request: Request,
  env: Env
): Promise<Response> {
  const { mutations } = await request.json<{ mutations: QueuedMutation[] }>();
  const accepted: string[] = [];
  const rejected: { mutationId: string; reason: string }[] = [];

  for (const mutation of mutations) {
    // Idempotency check — has this mutationId been processed before?
    const existing = await env.DB.prepare(
      "SELECT mutation_id FROM processed_mutations WHERE mutation_id = ?"
    )
      .bind(mutation.mutationId)
      .first();

    if (existing) {
      // Already processed — treat as accepted (idempotent success)
      accepted.push(mutation.mutationId);
      continue;
    }

    try {
      // Enqueue for async processing
      await env.MUTATIONS_QUEUE.send({
        ...mutation,
        userId: await resolveAnonymousUserId(request, env),
      });
      accepted.push(mutation.mutationId);
    } catch (err) {
      rejected.push({ mutationId: mutation.mutationId, reason: String(err) });
    }
  }

  return Response.json({ accepted, rejected });
}
```

## Cloudflare Queue Consumer (D1 Write)

```typescript
// worker/src/consumers/mutations.ts
import type { MessageBatch, Queue } from "@cloudflare/workers-types";

export default {
  async queue(
    batch: MessageBatch<QueuedMutation & { userId: string }>,
    env: Env
  ): Promise<void> {
    const db = env.DB;

    for (const message of batch.messages) {
      const { mutationId, type, payload, userId } = message.body;

      try {
        await db.batch([
          // Write the actual mutation
          buildMutationStatement(db, type, payload, userId),
          // Record processed ID for idempotency
          db
            .prepare(
              "INSERT OR IGNORE INTO processed_mutations (mutation_id, processed_at) VALUES (?, ?)"
            )
            .bind(mutationId, Date.now()),
        ]);
        message.ack();
      } catch (err) {
        message.retry({ delaySeconds: 30 });
      }
    }
  },
};

function buildMutationStatement(
  db: D1Database,
  type: string,
  payload: any,
  userId: string
): D1PreparedStatement {
  switch (type) {
    case "post":
      return db
        .prepare(
          "INSERT OR IGNORE INTO posts (id, user_id, content, created_at) VALUES (?, ?, ?, ?)"
        )
        .bind(payload.id, userId, payload.content, payload.createdAt);
    case "react":
      return db
        .prepare(
          "INSERT OR IGNORE INTO reactions (post_id, user_id, emoji, created_at) VALUES (?, ?, ?, ?)"
        )
        .bind(payload.postId, userId, payload.emoji, payload.createdAt);
    default:
      throw new Error(`Unknown mutation type: ${type}`);
  }
}
```

## Conflict Resolution Strategy

```
+------------------+-----------------------------+------------------------------+
| Conflict type    | Strategy                    | Notes                        |
+------------------+-----------------------------+------------------------------+
| Duplicate post   | INSERT OR IGNORE on post.id | Client UUID = idempotent key |
| Duplicate react  | INSERT OR IGNORE on         | Natural uniqueness per user  |
|                  | (post_id, user_id, emoji)   |                              |
| Delete-after-    | Check tombstone table first | Mark deleted_at, not DELETE  |
| create           |                             |                              |
| Follow conflict  | Last-write-wins via         | Queue consumer timestamp     |
|                  | MAX(created_at)             |                              |
| Stale optimistic | Server response includes    | Client reconciles on flush   |
| count            | authoritative counts        | response                     |
+------------------+-----------------------------+------------------------------+
```

## Mobile Background Fetch (iOS + Android)

```typescript
// src/lib/offline/background-sync.ts  — Expo TaskManager
import * as BackgroundFetch from "expo-background-fetch";
import * as TaskManager from "expo-task-manager";

const SYNC_TASK = "example project-offline-sync";

TaskManager.defineTask(SYNC_TASK, async () => {
  try {
    await flushQueue();
    return BackgroundFetch.BackgroundFetchResult.NewData;
  } catch {
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

export async function registerBackgroundSync(): Promise<void> {
  await BackgroundFetch.registerTaskAsync(SYNC_TASK, {
    minimumInterval: 15 * 60, // 15 min (iOS minimum)
    stopOnTerminate: false,
    startOnBoot: true,
  });
}
```

## Anti-patterns

- Flushing the queue without a `flushInProgress` guard — concurrent flushes on rapid
  network-change events send duplicate batches, causing double-writes even with idempotency keys.
- Using AsyncStorage item keys per mutation — a scan across thousands of keys is O(n) and blocks
  the JS thread; store the entire queue as a single serialised array.
- Sending mutations one-by-one to the Worker — each request incurs a cold-start and TLS overhead;
  batch into a single POST per flush cycle.
- Storing `mutationId` only in memory — app kill between enqueue and flush drops it; always persist
  to AsyncStorage / IndexedDB before showing optimistic UI.
- Queue consumer retrying immediately without `delaySeconds` — hammers D1 on transient write errors
  and exhausts per-binding D1 request limits.
- Not pruning `processed_mutations` — the idempotency table grows unbounded; add a daily D1 purge
  for rows older than 30 days.

## Gotchas

- Cloudflare Queues guarantee at-least-once delivery; the D1 `INSERT OR IGNORE` pattern is
  non-negotiable for mutation consumers.
- iOS background fetch interval is advisory; the OS may delay up to several hours based on battery
  and usage patterns — do not rely on it for time-sensitive sync.
- `NetInfo.addEventListener` fires on every network quality change, not just connectivity changes;
  check `isConnected` explicitly before flushing.
- D1 `batch()` is a single HTTP round-trip but still counts each statement toward the D1 row-write
  budget; monitor `wrangler d1 info` for row counts approaching plan limits.
- Cloudflare Queue messages have a maximum size of 128 KB; large post payloads (embedded base64
  images) must be stripped before enqueuing and uploaded separately via R2.

## Verification

```bash
# Check queue depth
wrangler queues consumer list example project-mutations

# Tail queue consumer Worker
wrangler tail --env production mutations-consumer

# D1 idempotency table row count
wrangler d1 execute example project-db --command \
  "SELECT COUNT(*) as cnt FROM processed_mutations WHERE processed_at > unixepoch('now','-1 day')*1000"

# Simulate offline flush in Jest
jest src/lib/offline/sync.test.ts --testNamePattern="flushQueue"
```

## Related

- `mobile-offline-sync-conflict-resolution.md`
- `offline-first-worker-api-resilience.md`
- `react-native-async-storage.md`
- `mobile-push-notifications-cloudflare-queues.md`
- `react-native-netinfo.md`
- `pwa-background-sync.md`

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/d1/
- https://docs.expo.dev/versions/latest/sdk/background-fetch/
- https://github.com/react-native-netinfo/react-native-netinfo
- https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API
