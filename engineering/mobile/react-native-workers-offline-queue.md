# React Native Offline-First Queue with Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your React Native app must continue accepting user mutations (creates, updates, deletes) even when the device has no connectivity, then reliably sync those mutations to your Cloudflare Workers backend once the network returns — with no duplicate writes.

## Context

- React Native 0.74+
- `@react-native-async-storage/async-storage` ^2.0 as the local queue store
- `@react-native-community/netinfo` ^11 for connectivity detection
- Cloudflare Workers backend with a D1 database
- Idempotency enforced via client-generated UUID `operationId` stored alongside each queued item
- Conflict resolution: last-write-wins using server-side `updated_at` timestamps from D1

## QueueManager Implementation

```typescript
// src/queue/QueueManager.ts
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo, { NetInfoState } from '@react-native-community/netinfo';
import { v4 as uuidv4 } from 'uuid';

const QUEUE_KEY = '@mutation_queue';
const WORKERS_URL = 'https://api.example.com/mutations/batch';

export interface QueuedMutation {
  operationId: string;   // idempotency key
  type: 'CREATE' | 'UPDATE' | 'DELETE';
  entity: string;
  payload: Record<string, unknown>;
  enqueuedAt: number;    // ms epoch
  attempts: number;
}

async function readQueue(): Promise<QueuedMutation[]> {
  const raw = await AsyncStorage.getItem(QUEUE_KEY);
  return raw ? JSON.parse(raw) : [];
}

async function writeQueue(queue: QueuedMutation[]): Promise<void> {
  await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
}

export async function enqueue(
  type: QueuedMutation['type'],
  entity: string,
  payload: Record<string, unknown>
): Promise<string> {
  const operationId = uuidv4();
  const item: QueuedMutation = {
    operationId,
    type,
    entity,
    payload,
    enqueuedAt: Date.now(),
    attempts: 0,
  };
  const queue = await readQueue();
  queue.push(item);
  await writeQueue(queue);
  return operationId;
}

export async function flushQueue(): Promise<void> {
  const queue = await readQueue();
  if (queue.length === 0) return;

  const res = await fetch(WORKERS_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mutations: queue }),
  });

  if (!res.ok) {
    // Increment attempt count; discard after 5 failures
    const updated = queue
      .map(m => ({ ...m, attempts: m.attempts + 1 }))
      .filter(m => m.attempts < 5);
    await writeQueue(updated);
    throw new Error(`Batch flush failed: ${res.status}`);
  }

  // On success clear only the operations the server accepted
  const { accepted }: { accepted: string[] } = await res.json();
  const remaining = queue.filter(m => !accepted.includes(m.operationId));
  await writeQueue(remaining);
}

// Subscribe once at app startup
export function startQueueSync(): () => void {
  const unsubscribe = NetInfo.addEventListener((state: NetInfoState) => {
    if (state.isConnected && state.isInternetReachable) {
      flushQueue().catch(console.warn);
    }
  });
  return unsubscribe;
}
```

## Cloudflare Workers Batch Endpoint

```typescript
// worker/src/mutations.ts
import { D1Database } from '@cloudflare/workers-types';

interface Mutation {
  operationId: string;
  type: 'CREATE' | 'UPDATE' | 'DELETE';
  entity: string;
  payload: Record<string, unknown>;
  enqueuedAt: number;
}

export async function handleBatch(
  req: Request,
  db: D1Database
): Promise<Response> {
  const { mutations }: { mutations: Mutation[] } = await req.json();
  const accepted: string[] = [];

  for (const m of mutations) {
    // Check idempotency — skip if already applied
    const exists = await db
      .prepare('SELECT 1 FROM applied_operations WHERE operation_id = ?')
      .bind(m.operationId)
      .first();
    if (exists) {
      accepted.push(m.operationId);
      continue;
    }

    try {
      if (m.type === 'CREATE') {
        await db
          .prepare(
            `INSERT INTO ${m.entity} (id, data, updated_at)
             VALUES (?, ?, datetime('now'))`
          )
          .bind(m.payload.id, JSON.stringify(m.payload))
          .run();
      } else if (m.type === 'UPDATE') {
        await db
          .prepare(
            `UPDATE ${m.entity} SET data = ?, updated_at = datetime('now')
             WHERE id = ? AND updated_at <= datetime(?, 'unixepoch')`
          )
          .bind(JSON.stringify(m.payload), m.payload.id, m.enqueuedAt / 1000)
          .run();
      } else if (m.type === 'DELETE') {
        await db
          .prepare(`DELETE FROM ${m.entity} WHERE id = ?`)
          .bind(m.payload.id)
          .run();
      }

      await db
        .prepare('INSERT INTO applied_operations (operation_id, applied_at) VALUES (?, datetime(\'now\'))')
        .bind(m.operationId)
        .run();

      accepted.push(m.operationId);
    } catch (err) {
      console.error('mutation failed', m.operationId, err);
    }
  }

  return Response.json({ accepted });
}
```

## React Native App Bootstrap

```typescript
// App.tsx
import React, { useEffect } from 'react';
import { startQueueSync } from './src/queue/QueueManager';

export default function App() {
  useEffect(() => {
    const stop = startQueueSync();
    return stop;
  }, []);
  // ...
}
```

## Anti-patterns

- **Flushing on every mutation** — only flush on connectivity change or explicit user action; continuous polling drains battery.
- **Storing sensitive data unencrypted in AsyncStorage** — use `react-native-encrypted-storage` for PII payloads.
- **Unbounded queue growth** — cap at 5 retry attempts (shown above) and surface a UI warning when items are dropped.
- **Trusting `enqueuedAt` for conflict resolution without clock sync** — rely on the D1 `updated_at` server timestamp, not the client clock.
- **Processing mutations in parallel** — send as an ordered batch; parallel sends can violate causal ordering.

## Gotchas

- `NetInfo.isInternetReachable` can be `null` on Android before the first network event; guard with `=== true`.
- D1 does not support `INSERT OR IGNORE` with returning clauses in the same statement on all runtime versions; use a separate `SELECT` for idempotency checks.
- `uuid` requires a polyfill for `crypto.getRandomValues` on React Native — add `react-native-get-random-values` before importing `uuid`.
- Workers batch endpoint must validate that the `entity` name is an allowlisted table to prevent SQL injection via the entity field.

## Verification

1. Enable airplane mode, perform 3 mutations in the app, verify `@mutation_queue` in AsyncStorage contains 3 items.
2. Re-enable network; observe `flushQueue` fires and queue drains to 0.
3. Re-send the same `operationId` to the batch endpoint; confirm the response `accepted` array includes the ID but the DB row count does not change.
4. Simulate a 500 from the Worker; confirm queue items increment `attempts` and are not discarded until attempt 5.

## Related

- `documentation/workers/d1-batch-writes.md`
- `documentation/categories/mobile/react-native-netinfo-patterns.md`
- `documentation/workers/idempotency-keys.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://github.com/react-native-async-storage/async-storage
- https://github.com/react-native-netinfo/react-native-netinfo
