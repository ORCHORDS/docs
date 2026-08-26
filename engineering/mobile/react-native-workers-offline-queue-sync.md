# React Native Workers Offline Queue Sync

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
Anonymous users on example project / example.com post content while intermittently offline — on subway
rides, in tunnels, or under flaky cellular coverage. Actions like posting a wam, reacting, or
following someone are queued locally and must be flushed reliably to a Cloudflare Worker once
connectivity returns without duplicating writes or losing operations.

## Context
React Native's `NetInfo` and `AppState` APIs expose network and foreground/background transitions.
Pairing them with MMKV for a persistent outbox and a Cloudflare Worker endpoint that accepts batched
mutations via an idempotency key gives an end-to-end durable queue without any third-party queuing
infrastructure. The Worker stores successful mutations in D1 and acknowledges the client with a
per-operation status array.

## Architecture — Queue Shape and Persistence
Each queued operation is serialised to MMKV under a single `outbox` key as a JSON array. Operations
carry a client-generated UUID used as the idempotency key on the Worker side, ensuring retried
batches never produce duplicates.

```typescript
// lib/offlineQueue.ts
import { MMKV } from 'react-native-mmkv';

const storage = new MMKV({ id: 'example project-outbox' });
const OUTBOX_KEY = 'outbox_v1';

export type QueuedOperation = {
  id: string;           // UUIDv4 — idempotency key
  type: 'post_wam' | 'react' | 'follow' | 'unfollow';
  payload: Record<string, unknown>;
  createdAt: number;    // unix ms
  attempts: number;
};

export function enqueue(op: Omit<QueuedOperation, 'attempts'>): void {
  const current = readQueue();
  storage.set(OUTBOX_KEY, JSON.stringify([...current, { ...op, attempts: 0 }]));
}

export function readQueue(): QueuedOperation[] {
  const raw = storage.getString(OUTBOX_KEY);
  return raw ? (JSON.parse(raw) as QueuedOperation[]) : [];
}

export function dequeueByIds(ids: string[]): void {
  const updated = readQueue().filter((op) => !ids.includes(op.id));
  storage.set(OUTBOX_KEY, JSON.stringify(updated));
}

export function bumpAttempts(ids: string[]): void {
  const updated = readQueue().map((op) =>
    ids.includes(op.id) ? { ...op, attempts: op.attempts + 1 } : op,
  );
  storage.set(OUTBOX_KEY, JSON.stringify(updated));
}
```

## Workers Side — Batch Mutation Endpoint
The Worker receives a `POST /sync/batch` with a JSON body containing the operations array. It
processes each operation in a D1 transaction, records the idempotency key in a `processed_ops`
table to prevent re-execution, and returns a per-operation status so the client knows which items
to dequeue.

```typescript
// worker/src/sync-batch.ts
import { Env } from './types';

type BatchOperation = {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  createdAt: number;
};

type OperationResult = { id: string; status: 'ok' | 'duplicate' | 'error'; error?: string };

export async function handleSyncBatch(request: Request, env: Env): Promise<Response> {
  const anonId = request.headers.get('X-Anon-Id');
  if (!anonId) return new Response('Unauthorized', { status: 401 });

  const body = (await request.json()) as { operations: BatchOperation[] };
  const results: OperationResult[] = [];

  for (const op of body.operations) {
    try {
      // Check idempotency
      const exists = await env.DB.prepare(
        'SELECT 1 FROM processed_ops WHERE op_id = ?1 AND anon_id = ?2',
      )
        .bind(op.id, anonId)
        .first();

      if (exists) {
        results.push({ id: op.id, status: 'duplicate' });
        continue;
      }

      await applyOperation(op, anonId, env);

      await env.DB.prepare(
        'INSERT INTO processed_ops (op_id, anon_id, processed_at) VALUES (?1, ?2, ?3)',
      )
        .bind(op.id, anonId, Date.now())
        .run();

      results.push({ id: op.id, status: 'ok' });
    } catch (err) {
      results.push({ id: op.id, status: 'error', error: String(err) });
    }
  }

  return Response.json({ results });
}

async function applyOperation(
  op: BatchOperation,
  anonId: string,
  env: Env,
): Promise<void> {
  switch (op.type) {
    case 'post_wam':
      await env.DB.prepare(
        'INSERT INTO wams (id, anon_id, content, created_at) VALUES (?1, ?2, ?3, ?4)',
      )
        .bind(op.payload.wamId, anonId, op.payload.content, op.createdAt)
        .run();
      break;
    case 'react':
      await env.DB.prepare(
        'INSERT OR IGNORE INTO reactions (wam_id, anon_id, emoji) VALUES (?1, ?2, ?3)',
      )
        .bind(op.payload.wamId, anonId, op.payload.emoji)
        .run();
      break;
    case 'follow':
      await env.DB.prepare(
        'INSERT OR IGNORE INTO follows (follower_anon_id, followee_anon_id) VALUES (?1, ?2)',
      )
        .bind(anonId, op.payload.targetAnonId)
        .run();
      break;
    case 'unfollow':
      await env.DB.prepare(
        'DELETE FROM follows WHERE follower_anon_id = ?1 AND followee_anon_id = ?2',
      )
        .bind(anonId, op.payload.targetAnonId)
        .run();
      break;
    default:
      throw new Error(`Unknown operation type: ${op.type}`);
  }
}
```

## Mobile Side — Flush Logic with NetInfo and AppState
A singleton `QueueFlusher` subscribes to both network and AppState changes. It flushes on
reconnect, on app foreground, and on a 30-second interval while online. Failed operations have
their attempt count incremented; operations exceeding 5 attempts are dead-lettered to a separate
MMKV key for manual review.

```typescript
// lib/queueFlusher.ts
import NetInfo from '@react-native-community/netinfo';
import { AppState, AppStateStatus } from 'react-native';
import { enqueue, readQueue, dequeueByIds, bumpAttempts, QueuedOperation } from './offlineQueue';
import { getAnonId } from './anonId';

const WORKER_URL = 'https://api.example.com/sync/batch';
const MAX_ATTEMPTS = 5;
const BATCH_SIZE = 50;

class QueueFlusher {
  private timer: ReturnType<typeof setInterval> | null = null;
  private isOnline = false;

  start(): void {
    NetInfo.addEventListener((state) => {
      const wasOffline = !this.isOnline;
      this.isOnline = !!state.isConnected && !!state.isInternetReachable;
      if (wasOffline && this.isOnline) void this.flush();
    });

    AppState.addEventListener('change', (status: AppStateStatus) => {
      if (status === 'active' && this.isOnline) void this.flush();
    });

    this.timer = setInterval(() => {
      if (this.isOnline) void this.flush();
    }, 30_000);
  }

  async flush(): Promise<void> {
    const queue = readQueue().filter((op) => op.attempts < MAX_ATTEMPTS);
    if (queue.length === 0) return;

    const batch = queue.slice(0, BATCH_SIZE);
    const anonId = await getAnonId();

    try {
      const res = await fetch(WORKER_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Anon-Id': anonId },
        body: JSON.stringify({ operations: batch }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const { results } = (await res.json()) as {
        results: { id: string; status: string }[];
      };

      const succeeded = results
        .filter((r) => r.status === 'ok' || r.status === 'duplicate')
        .map((r) => r.id);

      const failed = results.filter((r) => r.status === 'error').map((r) => r.id);

      dequeueByIds(succeeded);
      if (failed.length > 0) bumpAttempts(failed);
    } catch {
      bumpAttempts(batch.map((op) => op.id));
    }
  }
}

export const queueFlusher = new QueueFlusher();
```

## D1 Schema for Idempotency Tracking

```sql
-- migrations/0005_processed_ops.sql
CREATE TABLE IF NOT EXISTS processed_ops (
  op_id        TEXT NOT NULL,
  anon_id      TEXT NOT NULL,
  processed_at INTEGER NOT NULL,
  PRIMARY KEY (op_id, anon_id)
);

CREATE INDEX IF NOT EXISTS idx_processed_ops_anon ON processed_ops (anon_id, processed_at);

-- TTL cleanup: run via Cron Trigger daily
-- DELETE FROM processed_ops WHERE processed_at < (unixepoch('now') - 86400) * 1000;
```

## Anti-patterns
- Storing the queue in AsyncStorage — it is async-only and slower than MMKV for tight read-write
  loops during flush; also not byte-safe for large payloads.
- Flushing one operation at a time — round-trip latency on mobile makes individual calls
  expensive; always batch up to `BATCH_SIZE`.
- Using device timestamp as the idempotency key — clocks are not monotonic across app restarts;
  UUIDv4 is the correct choice.
- Treating `isConnected: true` as proof of internet reachability — always check `isInternetReachable`
  to avoid flushing over captive portals.
- Retrying indefinitely — dead-letter operations beyond `MAX_ATTEMPTS` to avoid queue bloat.

## Gotchas
- `NetInfo` on Android can briefly report `isInternetReachable: null` before the first real check
  completes; guard against that.
- Background app refresh on iOS may be suspended; `AppState` transitions to `active` are the
  reliable trigger for flush there.
- The `processed_ops` table grows unboundedly without the Cron Trigger cleanup; wire it up
  in `wrangler.toml` as a scheduled handler.
- MMKV writes are synchronous on the JS thread — keep the in-memory queue footprint small by
  capping `BATCH_SIZE` and dead-lettering aggressively.

## Verification
1. Enable airplane mode on a device.
2. Perform 3–5 actions (post a wam, follow a user, react).
3. Check MMKV outbox via Flipper MMKV plugin — operations should be visible.
4. Re-enable connectivity; within 30 s the queue should flush.
5. Query D1 via `wrangler d1 execute example project-db --command "SELECT * FROM processed_ops LIMIT 10;"` to
   confirm idempotency records exist.
6. Re-send the same batch manually via `curl` — Worker should respond `"status":"duplicate"` for
   all operations.

## Related
- `/documentation/categories/mobile/react-native-offline-first.md`
- `/documentation/categories/mobile/react-native-mmkv-storage.md`
- `/documentation/categories/mobile/mobile-offline-first-sync-cloudflare-queues.md`
- `/documentation/categories/mobile/android-workmanager-workers-sync.md`

## Sources
- https://developers.cloudflare.com/d1/
- https://github.com/mrousavy/react-native-mmkv
- https://github.com/react-native-netinfo/react-native-netinfo
- https://developers.cloudflare.com/workers/runtime-apis/request/
