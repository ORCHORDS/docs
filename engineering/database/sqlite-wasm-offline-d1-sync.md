# sqlite-wasm-offline-d1-sync

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

example project mobile users lose connectivity on trains and in basements. When
the network drops, the entire app becomes read-only or non-functional:
post drafts are lost, voted items revert on reload, and the community
feed shows a spinner indefinitely. Users on iOS Safari in particular
hit quota errors when attempting large caches via the Cache API.

## Context

SQLite compiled to WebAssembly (WASM) can run entirely in the browser,
providing a full SQL engine without a network call. The
`@sqlite.org/sqlite-wasm` package (the official, Origin Private File
System–backed build) persists data to the browser's OPFS (Origin
Private File System) in Chrome/Edge and to IndexedDB-backed VFS in
Firefox and Safari. This local DB acts as a client-side cache and
offline write buffer. A sync layer—implemented as a Cloudflare Worker—
reconciles the local WASM database with Cloudflare D1 when connectivity
resumes.

This pattern is specifically useful for example project because:

- Posts and votes created offline must not be lost on reconnect.
- The community feed can be served from the local WASM DB while offline.
- Conflict resolution is simple: last-write-wins on votes; no two users
  share the same anonymous session, so post conflicts are rare.

## Architecture Overview

```
Browser (mobile PWA / desktop SPA)
┌────────────────────────────────────────────┐
│  App Layer  ──────────►  SQLite WASM (OPFS)│
│                                            │
│  Sync Manager (background SW / periodic)   │
│    - reads pending_ops table               │
│    - POSTs delta to /api/sync endpoint     │
│    - applies server delta to local DB      │
└──────────────────────┬─────────────────────┘
                       │ HTTPS (when online)
┌──────────────────────▼─────────────────────┐
│  Cloudflare Worker  /api/sync              │
│    - reads pending ops from request body   │
│    - applies to D1 with conflict check     │
│    - returns server delta since client_ts  │
└──────────────────────┬─────────────────────┘
                       │
┌──────────────────────▼─────────────────────┐
│  Cloudflare D1  (source of truth)          │
└────────────────────────────────────────────┘
```

## SQLite WASM Setup

Install the official package and initialise with OPFS VFS (Chrome/Edge)
with an IndexedDB fallback for Safari:

```typescript
// src/db/local.ts
import { sqlite3Worker1Promiser } from '@sqlite.org/sqlite-wasm';

let db: Awaited<ReturnType<typeof openLocalDB>> | null = null;

export async function openLocalDB() {
  const promiser = await sqlite3Worker1Promiser();

  const { dbId } = await promiser('open', {
    filename: 'file:example project-local?vfs=opfs',  // OPFS-backed
    flags: 'c',                             // create if absent
  });

  // Bootstrap schema (idempotent)
  await promiser('exec', {
    dbId,
    sql: `
      CREATE TABLE IF NOT EXISTS posts (
        id          TEXT PRIMARY KEY,
        body        TEXT NOT NULL,
        community_id TEXT NOT NULL,
        created_at  INTEGER NOT NULL,
        score       INTEGER NOT NULL DEFAULT 0,
        synced      INTEGER NOT NULL DEFAULT 0  -- 0=pending, 1=synced
      );
      CREATE TABLE IF NOT EXISTS pending_ops (
        id          TEXT PRIMARY KEY,
        op_type     TEXT NOT NULL,  -- 'upsert_post' | 'record_vote'
        payload     TEXT NOT NULL,  -- JSON
        created_at  INTEGER NOT NULL,
        attempts    INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS sync_state (
        key         TEXT PRIMARY KEY,
        value       TEXT NOT NULL
      );
      INSERT OR IGNORE INTO sync_state VALUES ('last_sync_ts', '0');
    `,
  });

  return { promiser, dbId };
}
```

## Writing Offline (Pending Ops Queue)

Any write the app makes while offline (or before sync confirmation)
is recorded in `pending_ops` in addition to being optimistically applied
to the local `posts` table:

```typescript
export async function createPostOffline(
  post: { id: string; body: string; communityId: string },
  local: LocalDB
) {
  const now = Date.now();
  await local.promiser('exec', {
    dbId: local.dbId,
    sql: `
      INSERT OR IGNORE INTO posts
        (id, body, community_id, created_at, synced)
      VALUES (?, ?, ?, ?, 0);
      INSERT OR IGNORE INTO pending_ops
        (id, op_type, payload, created_at)
      VALUES (?, 'upsert_post', ?, ?);
    `,
    bind: [
      post.id, post.body, post.communityId, now,
      `op_${post.id}`, JSON.stringify(post), now,
    ],
  });
}
```

The `synced = 0` flag lets the UI show a "pending" indicator. The
`pending_ops` table survives page reload; the Sync Manager drains it on
next connectivity.

## Cloudflare Worker Sync Endpoint

```typescript
// Worker: POST /api/sync
export async function handleSync(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<{
    clientTs: number;
    ops: Array<{ id: string; op_type: string; payload: string }>;
  }>();

  const serverTs = Date.now();

  // 1. Apply client ops to D1 (idempotent via INSERT OR IGNORE)
  const stmts = body.ops.map(op => {
    const p = JSON.parse(op.payload);
    if (op.op_type === 'upsert_post') {
      return env.DB.prepare(`
        INSERT OR IGNORE INTO posts (id, body, community_id, created_at)
        VALUES (?, ?, ?, ?)
      `).bind(p.id, p.body, p.communityId, p.created_at);
    }
    if (op.op_type === 'record_vote') {
      return env.DB.prepare(`
        INSERT OR IGNORE INTO votes (post_id, fingerprint, direction)
        VALUES (?, ?, ?)
      `).bind(p.postId, p.fingerprint, p.direction);
    }
    throw new Error(`unknown op: ${op.op_type}`);
  });

  if (stmts.length > 0) await env.DB.batch(stmts);

  // 2. Return server delta since clientTs
  const { results: delta } = await env.DB.prepare(`
    SELECT id, body, community_id, created_at, score
    FROM   posts
    WHERE  created_at > ?
    ORDER  BY created_at ASC
    LIMIT  500
  `).bind(body.clientTs).all();

  return Response.json({ serverTs, delta });
}
```

`INSERT OR IGNORE` makes all ops idempotent—retrying a failed sync
never creates duplicates. The server returns only rows newer than
`clientTs`, keeping the delta payload small for mobile.

## Client-Side Sync Manager

```typescript
// src/db/sync.ts
export async function runSync(local: LocalDB) {
  if (!navigator.onLine) return;

  // Read pending ops
  const { rows: ops } = await local.promiser('exec', {
    dbId: local.dbId,
    sql: 'SELECT id, op_type, payload FROM pending_ops ORDER BY created_at LIMIT 50',
    returnValue: 'resultRows',
    rowMode: 'object',
  });

  // Read last sync timestamp
  const { rows: [[lastSyncTs]] } = await local.promiser('exec', {
    dbId: local.dbId,
    sql: "SELECT value FROM sync_state WHERE key = 'last_sync_ts'",
    returnValue: 'resultRows',
  });

  const res = await fetch('/api/sync', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clientTs: Number(lastSyncTs), ops }),
  });

  if (!res.ok) return; // retry on next connectivity

  const { serverTs, delta } = await res.json();

  // Apply server delta to local DB
  for (const row of delta) {
    await local.promiser('exec', {
      dbId: local.dbId,
      sql: `INSERT OR REPLACE INTO posts
              (id, body, community_id, created_at, score, synced)
            VALUES (?, ?, ?, ?, ?, 1)`,
      bind: [row.id, row.body, row.community_id, row.created_at, row.score],
    });
  }

  // Clear synced ops and update sync timestamp
  const opIds = ops.map((o: any) => `'${o.id}'`).join(',');
  await local.promiser('exec', {
    dbId: local.dbId,
    sql: `
      ${opIds.length ? `DELETE FROM pending_ops WHERE id IN (${opIds});` : ''}
      UPDATE sync_state SET value = ? WHERE key = 'last_sync_ts';
      UPDATE posts SET synced = 1 WHERE synced = 0;
    `,
    bind: [String(serverTs)],
  });
}

// Register online listener
window.addEventListener('online', () => runSync(localDB));
// Periodic sync every 60 s when tab is visible
setInterval(() => {
  if (document.visibilityState === 'visible') runSync(localDB);
}, 60_000);
```

## Conflict Resolution Strategy

example project's conflict rules are intentionally simple:

| Entity     | Conflict scenario                        | Resolution                     |
|------------|------------------------------------------|---------------------------------|
| Post       | Same post ID written offline by client   | `INSERT OR IGNORE`—first write wins (post IDs are UUIDs, collision probability ≈ 0) |
| Vote       | Same fingerprint + post_id voted twice   | `INSERT OR IGNORE`—first vote wins; idempotent |
| Score      | Server score diverges from local         | Server delta always overwrites local score via `INSERT OR REPLACE` |
| Feed order | Server has newer posts client missed     | Delta merge appends; client re-sorts by `created_at DESC` |

For richer conflict detection, add a `server_updated_at` column to D1
and compare it against the client's `created_at`; reject writes older
than the last server update.

## Mobile Storage Quota

| Browser            | OPFS / IDB storage          | Default quota              |
|--------------------|-----------------------------|----------------------------|
| Chrome (Android)   | OPFS (persistent)           | Up to 60 % of free storage |
| Safari (iOS)       | IndexedDB VFS               | ~1 GB per origin; Safari may evict after 7 days inactive |
| Firefox            | IndexedDB VFS               | Up to 50 % of free storage |

Mitigation for iOS Safari quota eviction:

```typescript
// Request persistent storage to prevent eviction
if (navigator.storage?.persist) {
  const granted = await navigator.storage.persist();
  if (!granted) console.warn('Persistent storage denied; data may be evicted');
}
```

Keep the local DB under 50 MB for mobile. Evict old synced posts beyond
a 30-day rolling window:

```typescript
await local.promiser('exec', {
  dbId: local.dbId,
  sql: `DELETE FROM posts WHERE synced = 1
        AND created_at < ? LIMIT 200`,
  bind: [Date.now() - 30 * 24 * 60 * 60 * 1000],
});
```

## Anti-Patterns

- Running SQLite WASM on the main thread—it blocks the UI during query
  execution. Always run it in a dedicated Worker thread via the
  `sqlite3Worker1Promiser` API.
- Storing the full OPFS-backed DB in `localStorage` or `sessionStorage`—
  these are not suitable for binary database files.
- Syncing the entire local DB to D1 on every online event—send only
  `pending_ops` (delta); never the full table.
- Using `Date.now()` as the sync clock on both client and server without
  accounting for clock skew; add ±5 s tolerance or use server-assigned
  timestamps as the authoritative value.
- Allowing `pending_ops` to grow unboundedly; cap retries at 5 and
  surface a "sync failed, please refresh" prompt to the user.

## Gotchas

- `@sqlite.org/sqlite-wasm` requires `Cross-Origin-Opener-Policy:
  same-origin` and `Cross-Origin-Embedder-Policy: require-corp` headers
  for SharedArrayBuffer support (needed by the OPFS VFS). Set these on
  the Worker serving the HTML:
  ```typescript
  response.headers.set('Cross-Origin-Opener-Policy', 'same-origin');
  response.headers.set('Cross-Origin-Embedder-Policy', 'require-corp');
  ```
- OPFS is not available in non-secure contexts (HTTP). example project must
  be served over HTTPS in production and localhost in dev.
- Safari 15 and earlier lack OPFS support; fall back to the
  `memory` VFS (non-persistent) with a toast warning for those users.
- `sqlite3Worker1Promiser` is asynchronous; all DB calls return
  Promises. Do not mix with synchronous SQLite WASM APIs.
- D1's `clientTs`-based delta can miss rows if the D1 clock and the
  client clock diverge significantly. Let the Worker assign `serverTs`
  and store it as `last_sync_ts`; never trust the client's `Date.now()`
  as the server timestamp.

## Verification

```bash
# In browser DevTools console, after loading the PWA offline:
# 1. Check OPFS file exists
const root = await navigator.storage.getDirectory();
for await (const [name] of root.entries()) console.log(name);
# Expected: "example project-local" (or similar OPFS file name)

# 2. Check pending_ops count after offline writes
# (from within the SQLite WASM worker context)
# Expected: ops accumulate while offline; drain to 0 after sync.

# Verify sync endpoint on the Worker side:
curl -X POST https://api.example project.example.com/api/sync \
  -H 'Content-Type: application/json' \
  -d '{"clientTs":0,"ops":[]}' | jq '.delta | length'
# Expected: number of posts since epoch (sanity check)
```

## Related

- `database/sqlite-production-wal-litestream-edge.md`
- `database/sqlite-wal-mode.md`
- `database/d1-batch-operations-performance.md`
- `database/eventual-consistency-patterns.md`
- `database/d1-read-replicas-mobile-latency.md`

## Sources

- https://sqlite.org/wasm/doc/trunk/index.md
- https://developer.mozilla.org/en-US/docs/Web/API/File_System_API/Origin_private_file_system
- https://developers.cloudflare.com/d1/worker-api/d1-database/
- https://developer.mozilla.org/en-US/docs/Web/API/StorageManager/persist
- https://web.dev/articles/storage-for-the-web
