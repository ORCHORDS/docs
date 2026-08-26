# React Native Expo SQLite ↔ Cloudflare D1 Offline Sync

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A React Native (Expo) app needs a fully offline-capable local database that syncs bidirectionally
with Cloudflare D1 when connectivity returns. The app must work without a network connection,
queue writes made offline, and resolve conflicts when the device reconnects — without pulling
in a heavy third-party sync platform.

## Context

Expo SQLite (`expo-sqlite` v14+) exposes a libSQL-compatible API with synchronous and
asynchronous query interfaces, WAL mode by default, and migration support. It runs on the
JS thread via a JSI binding and is production-ready on both iOS and Android.

The sync strategy here is **append-only event log**: every local mutation writes a row to a
`pending_changes` table. On reconnect, the device ships those rows to a Cloudflare Worker
which writes to D1 and returns a server delta. This avoids full-table conflict scans.

Stack: TypeScript, Expo SDK 52, `expo-sqlite ^14`, `@tanstack/react-query ^5`,
`expo-network-state`, Cloudflare Workers + D1.

## Database Setup and Migrations

```typescript
// db/database.ts
import * as SQLite from 'expo-sqlite'

let _db: SQLite.SQLiteDatabase | null = null

export function getDb(): SQLite.SQLiteDatabase {
  if (!_db) {
    _db = SQLite.openDatabaseSync('app.db')
    _db.execSync('PRAGMA journal_mode = WAL;')
    runMigrations(_db)
  }
  return _db
}

function runMigrations(db: SQLite.SQLiteDatabase) {
  db.execSync(`
    CREATE TABLE IF NOT EXISTS tasks (
      id          TEXT    PRIMARY KEY,
      title       TEXT    NOT NULL,
      done        INTEGER NOT NULL DEFAULT 0,
      updated_at  INTEGER NOT NULL,
      server_seq  INTEGER             -- NULL until synced
    );

    CREATE TABLE IF NOT EXISTS pending_changes (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      table_name  TEXT    NOT NULL,
      row_id      TEXT    NOT NULL,
      operation   TEXT    NOT NULL,   -- INSERT | UPDATE | DELETE
      payload     TEXT    NOT NULL,   -- JSON snapshot
      created_at  INTEGER NOT NULL
    );
  `)
}
```

## Local Mutations with Change Capture

```typescript
// db/taskRepository.ts
import { getDb } from './database'
import * as Crypto from 'expo-crypto'

export interface Task {
  id: string
  title: string
  done: boolean
  updated_at: number
  server_seq: number | null
}

export function createTask(title: string): Task {
  const db  = getDb()
  const now = Date.now()
  const id  = Crypto.randomUUID()

  const task: Task = { id, title, done: false, updated_at: now, server_seq: null }

  db.withTransactionSync(() => {
    db.runSync(
      'INSERT INTO tasks (id, title, done, updated_at) VALUES (?, ?, 0, ?)',
      [id, title, now],
    )
    db.runSync(
      `INSERT INTO pending_changes (table_name, row_id, operation, payload, created_at)
       VALUES ('tasks', ?, 'INSERT', ?, ?)`,
      [id, JSON.stringify(task), now],
    )
  })

  return task
}

export function updateTask(id: string, patch: Partial<Pick<Task, 'title' | 'done'>>): void {
  const db  = getDb()
  const now = Date.now()

  db.withTransactionSync(() => {
    if (patch.title !== undefined)
      db.runSync('UPDATE tasks SET title = ?, updated_at = ? WHERE id = ?', [patch.title, now, id])
    if (patch.done !== undefined)
      db.runSync('UPDATE tasks SET done = ?, updated_at = ? WHERE id = ?', [patch.done ? 1 : 0, now, id])

    const row = db.getFirstSync<Task>('SELECT * FROM tasks WHERE id = ?', [id])
    db.runSync(
      `INSERT INTO pending_changes (table_name, row_id, operation, payload, created_at)
       VALUES ('tasks', ?, 'UPDATE', ?, ?)`,
      [id, JSON.stringify(row), now],
    )
  })
}

export function listTasks(): Task[] {
  return getDb().getAllSync<Task>('SELECT * FROM tasks ORDER BY updated_at DESC')
}
```

## Sync Hook (React Query + Network State)

```typescript
// hooks/useSync.ts
import { useEffect, useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as Network from 'expo-network'
import { getDb } from '../db/database'

interface ServerDelta {
  upserts: Array<{ id: string; title: string; done: number; updated_at: number; server_seq: number }>
  lastServerSeq: number
}

async function pushAndPull(accessToken: string): Promise<ServerDelta> {
  const db = getDb()
  const pending = db.getAllSync<{
    id: number; row_id: string; operation: string; payload: string
  }>('SELECT * FROM pending_changes ORDER BY id ASC LIMIT 100')

  const localSeq = db.getFirstSync<{ seq: number }>(
    'SELECT COALESCE(MAX(server_seq), 0) AS seq FROM tasks'
  )?.seq ?? 0

  const res = await fetch('https://api.example.com/sync/tasks', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ changes: pending, lastKnownSeq: localSeq }),
  })

  if (!res.ok) throw new Error(`Sync failed: ${res.status}`)
  const delta: ServerDelta = await res.json()

  db.withTransactionSync(() => {
    // Apply server upserts
    for (const row of delta.upserts) {
      db.runSync(
        `INSERT INTO tasks (id, title, done, updated_at, server_seq)
         VALUES (?, ?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET
           title = excluded.title,
           done  = excluded.done,
           updated_at = excluded.updated_at,
           server_seq = excluded.server_seq
         WHERE excluded.updated_at >= tasks.updated_at`,
        [row.id, row.title, row.done, row.updated_at, row.server_seq],
      )
    }
    // Clear shipped pending changes
    if (pending.length > 0) {
      const ids = pending.map(r => r.id).join(',')
      db.execSync(`DELETE FROM pending_changes WHERE id IN (${ids})`)
    }
  })

  return delta
}

export function useSync(accessToken: string) {
  const queryClient = useQueryClient()
  const syncedRef   = useRef(false)

  const { mutate: sync, isPending } = useMutation({
    mutationFn: () => pushAndPull(accessToken),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      syncedRef.current = true
    },
  })

  useEffect(() => {
    let sub: Network.NetworkStateEvent | null = null

    Network.addNetworkStateListener(state => {
      if (state.isConnected && state.isInternetReachable) sync()
    })

    return () => { /* Network.removeNetworkStateListener(sub) in SDK 53+ */ }
  }, [sync])

  return { sync, isPending }
}
```

## Cloudflare Workers Sync Handler

```typescript
// worker.ts
interface SyncRequest {
  changes: Array<{ id: number; row_id: string; operation: string; payload: string }>
  lastKnownSeq: number
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

    const userId = await authenticate(request, env)
    if (!userId) return new Response('Unauthorized', { status: 401 })

    const { changes, lastKnownSeq }: SyncRequest = await request.json()

    // Apply client changes (last-write-wins by updated_at)
    const stmts = changes.map(change => {
      const row = JSON.parse(change.payload)
      if (change.operation === 'DELETE') {
        return env.DB.prepare(
          'DELETE FROM tasks WHERE id = ? AND user_id = ?'
        ).bind(row.id, userId)
      }
      return env.DB.prepare(
        `INSERT INTO tasks (id, user_id, title, done, updated_at)
         VALUES (?, ?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET
           title = excluded.title, done = excluded.done, updated_at = excluded.updated_at
         WHERE excluded.updated_at >= tasks.updated_at`
      ).bind(row.id, userId, row.title, row.done ? 1 : 0, row.updated_at)
    })

    if (stmts.length > 0) await env.DB.batch(stmts)

    // Return server delta since lastKnownSeq
    const delta = await env.DB.prepare(
      `SELECT id, title, done, updated_at, rowid AS server_seq
       FROM tasks WHERE user_id = ? AND rowid > ?
       ORDER BY rowid ASC LIMIT 500`
    ).bind(userId, lastKnownSeq).all<{
      id: string; title: string; done: number; updated_at: number; server_seq: number
    }>()

    return Response.json({
      upserts: delta.results,
      lastServerSeq: delta.results.at(-1)?.server_seq ?? lastKnownSeq,
    })
  },
}
```

## Anti-patterns

- **Replacing the entire local table on sync** — a full-replace wipes any writes made while
  the request was in-flight. The append-only change log is safer; reconcile row-by-row with
  `ON CONFLICT … DO UPDATE WHERE`.
- **Blocking the JS thread with synchronous queries** — `runSync` / `execSync` are acceptable
  in short-lived transactions but large scans should use the async `getAllAsync` variants to
  avoid dropped frames.
- **Storing access tokens in `AsyncStorage`** — use `expo-secure-store` for tokens; only
  non-sensitive sync metadata belongs in SQLite.
- **Unlimited pending_changes growth** — cap the retry count and prune permanently-rejected
  rows (`attempts > 5`) to avoid unbounded table growth on repeatedly offline devices.

## Gotchas

- `expo-sqlite` v14 changed the default database location on iOS to the application's Library
  directory (excluded from iCloud backup by default). Verify with `getDb().databasePath`.
- D1's `batch()` has a 100-statement limit per call. Chunk client changes in batches of 100
  before sending to the Worker.
- `ON CONFLICT(id) DO UPDATE WHERE` requires SQLite 3.39+. All Expo-managed libSQL builds
  include this version, but check custom native builds.
- `expo-network` `addNetworkStateListener` only detects OS-level connectivity, not actual
  internet reachability. Gate the sync start on both `isConnected` and `isInternetReachable`.

## Verification

```bash
# Inspect the local SQLite file on a connected Android device
adb shell run-as com.example.app \
  sqlite3 /data/data/com.example.app/files/app.db \
  "SELECT COUNT(*) FROM pending_changes;"

# D1 – check server-side row count
npx wrangler d1 execute app-db --remote \
  --command "SELECT COUNT(*) FROM tasks WHERE user_id = 'test-user';"

# Run integration test with Expo
npx expo run:android --variant debug && npx jest --testPathPattern=sync
```

## Related

- `capacitor-d1-sqlite-offline-sync.md`
- `mobile-offline-sync-conflict-resolution.md`
- `mobile-offline-first-sync-cloudflare-queues.md`
- `react-native-async-storage.md`
- `react-native-mmkv-storage.md`

## Sources

- expo-sqlite v14 docs — docs.expo.dev/versions/latest/sdk/sqlite
- Cloudflare D1 batch — developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
- SQLite ON CONFLICT — sqlite.org/lang_conflict.html
- TanStack Query mutations — tanstack.com/query/latest/docs/framework/react/guides/mutations
