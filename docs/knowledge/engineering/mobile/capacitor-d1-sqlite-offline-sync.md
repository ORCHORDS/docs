# Capacitor SQLite + Cloudflare D1: Bidirectional Offline Sync

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

Your Capacitor app stores data locally in SQLite via `@capacitor-community/sqlite` and your backend runs on Cloudflare D1 (SQLite at the edge). When the device is offline, users continue making changes. When connectivity returns you need those changes to sync to D1 and remote changes to sync down, without conflicts destroying data. You want a lightweight sync protocol that does not require a third-party backend or a dedicated sync server.

---

## Context

Both the mobile SQLite database (via `@capacitor-community/sqlite`) and Cloudflare D1 are SQLite-dialect databases, which simplifies the protocol: you can use the same table schemas on both sides and the same SQL query patterns. The sync strategy implemented here is Last-Write-Wins (LWW) with a vector clock extension — sufficient for most CRUD mobile apps. For collaborative/multi-author scenarios consider CRDT-based approaches (Automerge, Yjs).

The sync protocol has three layers:

1. **Change tracking**: every table has `updated_at` (Unix ms) and `deleted_at` columns. Mutations always set `updated_at = Date.now()`.
2. **Outbound sync**: on connectivity restore the client sends all rows where `updated_at > last_sync_ts` to a Cloudflare Worker, which applies them to D1.
3. **Inbound sync**: the Worker returns all rows in D1 where `updated_at > last_sync_ts` that the client has not yet seen.

---

## 1. Schema Design (Both Local and D1)

```sql
-- applied on both the local Capacitor SQLite DB and D1

CREATE TABLE IF NOT EXISTS todos (
  id          TEXT    PRIMARY KEY,     -- UUID, generated client-side
  title       TEXT    NOT NULL,
  completed   INTEGER NOT NULL DEFAULT 0,
  owner_id    TEXT    NOT NULL,
  updated_at  INTEGER NOT NULL,        -- Unix milliseconds
  deleted_at  INTEGER,                 -- NULL = not deleted; soft-delete
  synced_at   INTEGER                  -- local only: timestamp of last successful sync
);

CREATE INDEX IF NOT EXISTS idx_todos_updated_at ON todos (updated_at);
CREATE INDEX IF NOT EXISTS idx_todos_owner     ON todos (owner_id);
```

Store the last sync checkpoint per table:

```sql
CREATE TABLE IF NOT EXISTS sync_checkpoints (
  table_name    TEXT PRIMARY KEY,
  last_sync_ts  INTEGER NOT NULL DEFAULT 0
);
```

---

## 2. Local Database Service (Capacitor SQLite)

```typescript
// src/db/local.ts
import { CapacitorSQLite, SQLiteConnection, SQLiteDBConnection } from "@capacitor-community/sqlite";

const sqlite = new SQLiteConnection(CapacitorSQLite);
let db: SQLiteDBConnection | null = null;

export async function openDb(): Promise<SQLiteDBConnection> {
  if (db) return db;
  db = await sqlite.createConnection("app_db", false, "no-encryption", 1, false);
  await db.open();
  await db.execute(SCHEMA_SQL);  // the CREATE TABLE statements above
  return db;
}

export async function upsertTodo(
  conn: SQLiteDBConnection,
  todo: {
    id: string;
    title: string;
    completed: boolean;
    ownerId: string;
  }
): Promise<void> {
  await conn.run(
    `INSERT INTO todos (id, title, completed, owner_id, updated_at)
     VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET
       title      = excluded.title,
       completed  = excluded.completed,
       updated_at = excluded.updated_at`,
    [todo.id, todo.title, todo.completed ? 1 : 0, todo.ownerId, Date.now()]
  );
}

export async function softDeleteTodo(
  conn: SQLiteDBConnection,
  id: string
): Promise<void> {
  await conn.run(
    "UPDATE todos SET deleted_at = ?, updated_at = ? WHERE id = ?",
    [Date.now(), Date.now(), id]
  );
}

export async function getPendingChanges(
  conn: SQLiteDBConnection,
  tableName: string,
  since: number
): Promise<unknown[]> {
  const result = await conn.query(
    `SELECT * FROM ${tableName} WHERE updated_at > ? ORDER BY updated_at ASC LIMIT 1000`,
    [since]
  );
  return result.values ?? [];
}

export async function getCheckpoint(
  conn: SQLiteDBConnection,
  tableName: string
): Promise<number> {
  const result = await conn.query(
    "SELECT last_sync_ts FROM sync_checkpoints WHERE table_name = ?",
    [tableName]
  );
  return (result.values?.[0]?.last_sync_ts as number) ?? 0;
}

export async function setCheckpoint(
  conn: SQLiteDBConnection,
  tableName: string,
  ts: number
): Promise<void> {
  await conn.run(
    `INSERT INTO sync_checkpoints (table_name, last_sync_ts)
     VALUES (?, ?)
     ON CONFLICT(table_name) DO UPDATE SET last_sync_ts = excluded.last_sync_ts`,
    [tableName, ts]
  );
}
```

---

## 3. Cloudflare Worker Sync Endpoint

```typescript
// workers/sync/src/index.ts
export interface Env {
  DB: D1Database;
}

interface SyncRequest {
  tableName: "todos";
  ownerId: string;
  since: number;              // client's last sync timestamp
  changes: TodoRow[];         // rows the client wants to push
}

interface TodoRow {
  id: string;
  title: string;
  completed: number;
  owner_id: string;
  updated_at: number;
  deleted_at: number | null;
}

interface SyncResponse {
  serverChanges: TodoRow[];   // rows the server has that are newer than `since`
  serverTs: number;           // server's current timestamp — client uses this as next `since`
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/sync") {
      return new Response("Not found", { status: 404 });
    }

    // In production: validate JWT from Authorization header here
    const body = await request.json<SyncRequest>();

    const serverTs = Date.now();

    // 1. Apply client changes to D1 using Last-Write-Wins
    if (body.changes.length > 0) {
      await applyClientChanges(env.DB, body.tableName, body.changes, body.ownerId);
    }

    // 2. Fetch server changes the client doesn't have yet
    const serverChanges = await getServerChanges(
      env.DB,
      body.tableName,
      body.ownerId,
      body.since
    );

    const response: SyncResponse = { serverChanges, serverTs };
    return Response.json(response, {
      headers: { "Cache-Control": "no-store" },
    });
  },
};

async function applyClientChanges(
  db: D1Database,
  tableName: string,
  changes: TodoRow[],
  ownerId: string
): Promise<void> {
  // Batch into D1's 100-statement limit per batch
  const BATCH_SIZE = 50;
  for (let i = 0; i < changes.length; i += BATCH_SIZE) {
    const batch = changes.slice(i, i + BATCH_SIZE);
    const statements = batch
      .filter((row) => row.owner_id === ownerId)  // prevent overwriting other users' rows
      .map((row) =>
        db.prepare(
          `INSERT INTO ${tableName} (id, title, completed, owner_id, updated_at, deleted_at)
           VALUES (?1, ?2, ?3, ?4, ?5, ?6)
           ON CONFLICT(id) DO UPDATE SET
             title      = CASE WHEN excluded.updated_at > ${tableName}.updated_at THEN excluded.title      ELSE ${tableName}.title      END,
             completed  = CASE WHEN excluded.updated_at > ${tableName}.updated_at THEN excluded.completed  ELSE ${tableName}.completed  END,
             deleted_at = CASE WHEN excluded.updated_at > ${tableName}.updated_at THEN excluded.deleted_at ELSE ${tableName}.deleted_at END,
             updated_at = MAX(excluded.updated_at, ${tableName}.updated_at)`
        ).bind(
          row.id,
          row.title,
          row.completed,
          row.owner_id,
          row.updated_at,
          row.deleted_at ?? null
        )
      );

    if (statements.length > 0) {
      await db.batch(statements);
    }
  }
}

async function getServerChanges(
  db: D1Database,
  tableName: string,
  ownerId: string,
  since: number
): Promise<TodoRow[]> {
  const result = await db
    .prepare(
      `SELECT * FROM ${tableName}
       WHERE owner_id = ?1 AND updated_at > ?2
       ORDER BY updated_at ASC
       LIMIT 1000`
    )
    .bind(ownerId, since)
    .all<TodoRow>();

  return result.results ?? [];
}
```

---

## 4. Sync Orchestrator on the Client

```typescript
// src/sync/syncEngine.ts
import NetInfo from "@react-native-community/netinfo";
import { openDb, getPendingChanges, getCheckpoint, setCheckpoint } from "../db/local";

const SYNC_URL = "https://sync.example.workers.dev/sync";
const TABLES_TO_SYNC = ["todos"] as const;
const SYNC_DEBOUNCE_MS = 3_000;

let syncTimer: ReturnType<typeof setTimeout> | null = null;

export function scheduleSyncDebounced() {
  if (syncTimer) clearTimeout(syncTimer);
  syncTimer = setTimeout(runSync, SYNC_DEBOUNCE_MS);
}

export async function runSync(): Promise<void> {
  const netState = await NetInfo.fetch();
  if (!netState.isConnected) return;

  const db = await openDb();

  for (const table of TABLES_TO_SYNC) {
    try {
      const since = await getCheckpoint(db, table);
      const changes = await getPendingChanges(db, table, since);

      const res = await fetch(SYNC_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${await getAuthToken()}`,
        },
        body: JSON.stringify({
          tableName: table,
          ownerId: getCurrentUserId(),
          since,
          changes,
        }),
      });

      if (!res.ok) {
        throw new Error(`Sync failed: ${res.status}`);
      }

      const { serverChanges, serverTs } = await res.json<{
        serverChanges: unknown[];
        serverTs: number;
      }>();

      // Apply server changes locally (LWW — server wins on tie)
      for (const row of serverChanges as { id: string; [k: string]: unknown }[]) {
        await db.run(
          `INSERT INTO ${table} (id, title, completed, owner_id, updated_at, deleted_at)
           VALUES (?1, ?2, ?3, ?4, ?5, ?6)
           ON CONFLICT(id) DO UPDATE SET
             title      = CASE WHEN excluded.updated_at >= ${table}.updated_at THEN excluded.title      ELSE ${table}.title      END,
             completed  = CASE WHEN excluded.updated_at >= ${table}.updated_at THEN excluded.completed  ELSE ${table}.completed  END,
             deleted_at = CASE WHEN excluded.updated_at >= ${table}.updated_at THEN excluded.deleted_at ELSE ${table}.deleted_at END,
             updated_at = MAX(excluded.updated_at, ${table}.updated_at)`,
          [
            row.id,
            row.title,
            row.completed,
            row.owner_id,
            row.updated_at,
            row.deleted_at ?? null,
          ]
        );
      }

      // Advance the checkpoint to the server's current time
      await setCheckpoint(db, table, serverTs);
    } catch (err) {
      console.error(`[sync] ${table} failed:`, err);
      // Leave checkpoint unchanged — will retry on next sync
    }
  }
}

function getCurrentUserId(): string {
  // Replace with your auth store
  return "user_abc123";
}

async function getAuthToken(): Promise<string> {
  // Replace with your token refresh logic
  return "eyJhbGci...";
}
```

---

## 5. Triggering Sync on Connectivity Restore

```typescript
// App.tsx
import { useEffect } from "react";
import NetInfo from "@react-native-community/netinfo";
import { scheduleSyncDebounced, runSync } from "./src/sync/syncEngine";
import { AppState } from "react-native";

export function useSyncLifecycle() {
  useEffect(() => {
    // Sync on app foreground
    const appStateSub = AppState.addEventListener("change", (state) => {
      if (state === "active") scheduleSyncDebounced();
    });

    // Sync on network reconnect
    const netSub = NetInfo.addEventListener((netState) => {
      if (netState.isConnected) scheduleSyncDebounced();
    });

    // Initial sync on mount
    runSync();

    return () => {
      appStateSub.remove();
      netSub();
    };
  }, []);
}
```

---

## Anti-Patterns

- **Using auto-increment integer primary keys.** Two offline devices can assign the same integer ID. Always use UUIDs generated client-side with `crypto.randomUUID()`.
- **Deleting rows instead of soft-deleting.** Hard-deleted rows cannot be synced to other devices. Once a row is gone the sync protocol has nothing to send.
- **Using wall-clock `Date.now()` for LWW without awareness of clock drift.** A device with the clock set to the future will always win. For high-stakes data, use a server-authoritative timestamp returned from the sync endpoint rather than the client's `updated_at`.
- **Syncing entire tables on every run.** For large datasets, always use the `since` checkpoint to send only the delta. Full-table syncs at scale will exceed D1's 10 MB response limit per query.
- **Not batching D1 writes.** `db.prepare().bind().run()` in a loop issues one HTTP round-trip per statement. Always use `db.batch()` for write-heavy sync operations.

---

## Gotchas

- **D1 has a 10 MB response size limit per query.** If `LIMIT 1000` still exceeds this, reduce the limit and implement cursor-based pagination using the last `updated_at` as the cursor.
- **`@capacitor-community/sqlite` requires a web polyfill for PWA mode.** In PWA/browser environments the plugin shims to `sql.js`. The schema and queries must be SQLite-compatible (no MySQL-isms).
- **D1 `ON CONFLICT` requires all inserted columns to be named.** Unlike desktop SQLite, D1 rejects `INSERT OR REPLACE` patterns that omit nullable columns. Always provide explicit values for every column, even if `null`.
- **Sync during backgrounding on iOS.** iOS suspends JS execution within a few seconds of backgrounding. If a sync is in progress when the app is backgrounded, it may be cut off. Use a `beginBackgroundTask` native module (or Capacitor Background Runner) to request a short background window.
- **Clock skew between client and server.** If the device clock is behind the server clock by more than the sync interval, the `since` checkpoint will be ahead of the client's real last-sync time and changes will be re-sent. Normalise by using `serverTs` (returned from the sync response) as the next `since`, never the local clock.

---

## Verification

```bash
# 1. Run the D1 schema
wrangler d1 execute my-d1-db --file schema.sql

# 2. Deploy the sync Worker
wrangler deploy

# 3. Seed D1 with a test row
wrangler d1 execute my-d1-db \
  --command "INSERT INTO todos (id, title, completed, owner_id, updated_at) VALUES ('t1', 'Buy milk', 0, 'user_abc123', $(date +%s)000)"

# 4. Curl the sync endpoint directly
curl -X POST "https://sync.example.workers.dev/sync" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"tableName":"todos","ownerId":"user_abc123","since":0,"changes":[]}'

# 5. Verify the seeded row is returned in serverChanges
```

---

## Related

- `mobile-offline-first-sync-cloudflare-queues.md`
- `mobile-offline-sync-conflict-resolution.md`
- `mobile-local-database-schema-migration.md`
- `capacitor-native-bridge-plugin-development.md`
- `react-native-offline-first.md`

---

## Sources

- `@capacitor-community/sqlite` — https://github.com/capacitor-community/sqlite
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- D1 batch statements — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
- Cloudflare Workers REST API — https://developers.cloudflare.com/workers/
- Martin Kleppmann — Designing Data-Intensive Applications (conflict resolution patterns)
