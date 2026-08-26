# IndexedDB Offline Sync with Cloudflare D1 via Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your web app must work fully offline — creating, editing, and deleting records while disconnected — then automatically synchronise those changes to a Cloudflare D1 SQLite database through a Workers API when connectivity resumes. You need last-write-wins or vector-clock conflict resolution, a durable mutation queue in IndexedDB, and a reliable sync loop that retries on failure without duplicating writes.

---

## Context

IndexedDB provides a persistent, transactional client-side store. Cloudflare D1 is a SQLite-backed distributed database accessible from Workers. The sync pattern stores pending mutations in an IndexedDB "outbox" table, processes them when online, and updates a local "shadow" copy of the server state for fast reads. A Service Worker background-sync event ensures mutations drain even if the user navigates away before the connection recovers.

---

## IndexedDB Schema and Helpers

```typescript
// db/local.ts

const DB_NAME = "myapp";
const DB_VERSION = 1;

export interface LocalRecord {
  id: string;          // client-generated UUID
  data: unknown;
  updatedAt: number;   // epoch ms — used for last-write-wins
  synced: boolean;
}

export interface OutboxItem {
  id: string;          // UUID for the mutation itself
  op: "upsert" | "delete";
  recordId: string;
  payload: unknown;
  createdAt: number;
  attempts: number;
}

let _db: IDBDatabase | null = null;

export async function openDb(): Promise<IDBDatabase> {
  if (_db) return _db;
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = (e.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains("records")) {
        const store = db.createObjectStore("records", { keyPath: "id" });
        store.createIndex("updatedAt", "updatedAt");
        store.createIndex("synced", "synced");
      }
      if (!db.objectStoreNames.contains("outbox")) {
        const outbox = db.createObjectStore("outbox", { keyPath: "id" });
        outbox.createIndex("createdAt", "createdAt");
      }
    };
    req.onsuccess = () => {
      _db = req.result;
      resolve(_db);
    };
    req.onerror = () => reject(req.error);
  });
}

export async function idbPut<T>(
  storeName: string,
  value: T
): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, "readwrite");
    tx.objectStore(storeName).put(value);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function idbDelete(
  storeName: string,
  key: string
): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, "readwrite");
    tx.objectStore(storeName).delete(key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function idbGetAll<T>(storeName: string): Promise<T[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const req = db.transaction(storeName, "readonly")
      .objectStore(storeName).getAll();
    req.onsuccess = () => resolve(req.result as T[]);
    req.onerror = () => reject(req.error);
  });
}
```

---

## Writing to the Outbox (Offline-Safe Mutations)

```typescript
// db/mutations.ts

import { idbPut, idbGetAll, OutboxItem, LocalRecord } from "./local";

export async function upsertRecord(
  recordId: string,
  data: unknown
): Promise<void> {
  const now = Date.now();

  // Write to local shadow store immediately (optimistic)
  await idbPut<LocalRecord>("records", {
    id: recordId,
    data,
    updatedAt: now,
    synced: false,
  });

  // Enqueue mutation in outbox
  await idbPut<OutboxItem>("outbox", {
    id: crypto.randomUUID(),
    op: "upsert",
    recordId,
    payload: data,
    createdAt: now,
    attempts: 0,
  });

  // Kick off sync if online
  if (navigator.onLine) {
    syncOutbox().catch(console.error);
  }
}
```

---

## Draining the Outbox (Sync Loop)

```typescript
// db/sync.ts

import {
  idbGetAll,
  idbPut,
  idbDelete,
  OutboxItem,
  LocalRecord,
} from "./local";

const SYNC_ENDPOINT = "/api/sync";
const MAX_ATTEMPTS = 5;

export async function syncOutbox(): Promise<void> {
  const outbox = await idbGetAll<OutboxItem>("outbox");
  // Process in insertion order
  const sorted = outbox.sort((a, b) => a.createdAt - b.createdAt);

  for (const item of sorted) {
    if (item.attempts >= MAX_ATTEMPTS) continue; // give up after 5 tries

    try {
      const res = await fetch(SYNC_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          op: item.op,
          recordId: item.recordId,
          payload: item.payload,
          clientUpdatedAt: item.createdAt,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      // Mark local record as synced
      if (item.op === "upsert") {
        const records = await idbGetAll<LocalRecord>("records");
        const existing = records.find((r) => r.id === item.recordId);
        if (existing) {
          await idbPut<LocalRecord>("records", { ...existing, synced: true });
        }
      }

      // Remove from outbox
      await idbDelete("outbox", item.id);
    } catch {
      // Increment attempts for exponential back-off on next try
      await idbPut<OutboxItem>("outbox", {
        ...item,
        attempts: item.attempts + 1,
      });
    }
  }
}

// Listen for connectivity restoration
window.addEventListener("online", () => {
  syncOutbox().catch(console.error);
});
```

---

## Cloudflare Workers Sync Endpoint with D1

```typescript
// functions/api/sync.ts

interface SyncPayload {
  op: "upsert" | "delete";
  recordId: string;
  payload: unknown;
  clientUpdatedAt: number;
}

export const onRequestPost: PagesFunction<Env> = async (ctx) => {
  const body = await ctx.request.json<SyncPayload>();
  const db = ctx.env.DB; // D1 binding

  if (body.op === "upsert") {
    // Last-write-wins: only apply if client timestamp is newer than server
    const existing = await db
      .prepare("SELECT updated_at FROM records WHERE id = ?")
      .bind(body.recordId)
      .first<{ updated_at: number }>();

    if (existing && existing.updated_at > body.clientUpdatedAt) {
      // Server has a newer version — return it for client merge
      const serverRow = await db
        .prepare("SELECT * FROM records WHERE id = ?")
        .bind(body.recordId)
        .first();
      return Response.json({ conflict: true, serverRecord: serverRow });
    }

    await db
      .prepare(`
        INSERT INTO records (id, data, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          data = excluded.data,
          updated_at = excluded.updated_at
      `)
      .bind(
        body.recordId,
        JSON.stringify(body.payload),
        body.clientUpdatedAt
      )
      .run();
  } else if (body.op === "delete") {
    await db
      .prepare("DELETE FROM records WHERE id = ?")
      .bind(body.recordId)
      .run();
  }

  return Response.json({ ok: true });
};
```

D1 schema:

```sql
CREATE TABLE IF NOT EXISTS records (
  id         TEXT PRIMARY KEY,
  data       TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
```

---

## Background Sync via Service Worker

```typescript
// public/sw.js

self.addEventListener("sync", (event) => {
  if (event.tag === "sync-outbox") {
    event.waitUntil(drainOutboxFromSW());
  }
});

async function drainOutboxFromSW() {
  // Reuse the same fetch-based sync logic
  await fetch("/api/sync-trigger", { method: "POST" });
}
```

Register the sync tag after writing a mutation:

```typescript
// In the main thread after upsertRecord()
if ("serviceWorker" in navigator && "SyncManager" in window) {
  const reg = await navigator.serviceWorker.ready;
  await reg.sync.register("sync-outbox");
}
```

---

## Anti-patterns

- **Syncing on every keystroke**: Debounce writes to the outbox; batch rapid edits into a single mutation before enqueuing.
- **Not handling conflicts**: A simple online-check before writing causes silent data loss when two tabs edit the same record. Always implement last-write-wins or return the server record for client-side merge.
- **Clearing the outbox before confirmation**: Remove an outbox item only after the server returns 2xx. Removing on send means a network failure drops the mutation permanently.
- **Storing large binary blobs in outbox without chunking**: IndexedDB has no per-record size limit but browsers impose a storage quota. Large payloads should be stored as references (File IDs in R2) not inline.
- **Omitting `updatedAt` timestamps**: Without a timestamp, last-write-wins is impossible and you fall back to last-sync-wins, which depends on network timing.

---

## Gotchas

- IndexedDB transactions auto-commit when there are no pending requests and the call stack unwinds. Never `await` an unrelated promise inside a transaction callback — use a request-chaining pattern or the `idb` library wrapper.
- Background Sync (`SyncManager`) is only available in Chromium-based browsers (2026). Safari supports it from 16.4 under `navigator.serviceWorker.ready` but the API surface is limited. Always fall back to the `window.online` listener.
- D1's `ON CONFLICT DO UPDATE` requires that the conflicting column is declared as `PRIMARY KEY` or has a `UNIQUE` constraint.
- Cloudflare Pages Functions run at the edge closest to the user, but D1 reads may be served from a regional replica while writes always go to the primary. Under high write contention, `clientUpdatedAt` comparisons may behave unexpectedly across regions.

---

## Verification

```typescript
// Vitest integration test (happy-dom + fake-indexeddb)
import "fake-indexeddb/auto";
import { upsertRecord } from "./db/mutations";
import { idbGetAll, OutboxItem } from "./db/local";

test("upsertRecord enqueues to outbox", async () => {
  await upsertRecord("rec-1", { title: "Hello" });
  const outbox = await idbGetAll<OutboxItem>("outbox");
  expect(outbox).toHaveLength(1);
  expect(outbox[0].op).toBe("upsert");
  expect(outbox[0].recordId).toBe("rec-1");
});
```

Test the Workers endpoint with `wrangler d1 execute` in local mode:

```bash
wrangler d1 execute DB --local --command \
  "SELECT * FROM records ORDER BY updated_at DESC LIMIT 5"
```

---

## Related

- `browser-indexeddb-patterns.md` — foundational IndexedDB helpers and cursor iteration
- `browser-service-worker-cache.md` — Service Worker caching strategies
- `pwa-service-worker-cloudflare-pages.md` — PWA setup on Pages
- `hono-cloudflare-workers-frontend-api.md` — structuring the Workers API layer

---

## Sources

- MDN IndexedDB API: https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API
- Cloudflare D1 Documentation: https://developers.cloudflare.com/d1/
- Background Sync API: https://developer.mozilla.org/en-US/docs/Web/API/Background_Synchronization_API
- CRDT and OT overview (Martin Kleppmann): https://martin.kleppmann.com/2020/07/06/crdt-hard-parts-hydra.html
