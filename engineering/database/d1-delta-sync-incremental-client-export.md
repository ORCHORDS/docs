# D1 Delta Sync: Incremental Client Export with Row Versions

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Mobile or offline-capable clients need to sync only the rows that changed since their last sync, rather than re-downloading the full dataset on every request. D1's monotonically increasing row version column enables efficient delta sync with minimal query overhead.

## Context
Delta sync is the backbone of offline-first apps: the client sends its last known `sync_cursor` (a row version or high-water-mark timestamp), and the server returns only rows created or modified after that point. SQLite's `unixepoch()` function provides millisecond-precision timestamps when combined with `strftime`, but a monotonically increasing integer `row_version` driven by a trigger is more reliable because it is immune to clock skew and back-dated timestamps. D1's edge deployment means clients can sync against a geographically close replica with sub-50ms latency for typical delta payloads.

## Schema: Row Version Column and Trigger

```sql
-- migrations/0040_row_versioning.sql

-- Global monotonic version counter (one row)
CREATE TABLE IF NOT EXISTS version_counter (
  id      INTEGER PRIMARY KEY CHECK (id = 1), -- enforce single row
  current INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO version_counter (id, current) VALUES (1, 0);

-- Add row_version to every synced table
ALTER TABLE posts  ADD COLUMN row_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users  ADD COLUMN row_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE comments ADD COLUMN row_version INTEGER NOT NULL DEFAULT 0;

-- Trigger: bump global counter and stamp row_version on every INSERT/UPDATE
CREATE TRIGGER posts_version_on_insert
AFTER INSERT ON posts
BEGIN
  UPDATE version_counter SET current = current + 1 WHERE id = 1;
  UPDATE posts SET row_version = (SELECT current FROM version_counter WHERE id = 1)
  WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER posts_version_on_update
AFTER UPDATE ON posts
BEGIN
  UPDATE version_counter SET current = current + 1 WHERE id = 1;
  UPDATE posts SET row_version = (SELECT current FROM version_counter WHERE id = 1)
  WHERE rowid = NEW.rowid;
END;

-- Repeat for users and comments tables...

-- Index for efficient delta queries
CREATE INDEX idx_posts_row_version    ON posts    (row_version);
CREATE INDEX idx_users_row_version    ON users    (row_version);
CREATE INDEX idx_comments_row_version ON comments (row_version);
```

## Delta Query Helper

```typescript
// src/sync/delta-query.ts
export interface DeltaPage<T> {
  rows:       T[];
  nextCursor: number | null; // null when caught up
  serverVersion: number;
}

export async function queryDelta<T extends { row_version: number }>(
  db: D1Database,
  table: string,
  allowedColumns: string[],
  fromVersion: number,
  limit = 200,
): Promise<DeltaPage<T>> {
  const cols = allowedColumns.join(', ');

  // Validate table name against an allowlist (never interpolate untrusted input)
  const ALLOWED_TABLES = new Set(['posts', 'users', 'comments']);
  if (!ALLOWED_TABLES.has(table)) throw new Error(`Table ${table} not allowed for sync`);

  const [rowResult, versionResult] = await db.batch([
    db.prepare(
      `SELECT ${cols}
       FROM   ${table}
       WHERE  row_version > ?
       ORDER  BY row_version ASC
       LIMIT  ?`
    ).bind(fromVersion, limit),
    db.prepare(
      `SELECT current AS ver FROM version_counter WHERE id = 1`
    ),
  ]);

  const rows = rowResult.results as T[];
  const serverVersion = (versionResult.results[0] as { ver: number }).ver;
  const lastRow = rows[rows.length - 1];
  const nextCursor = rows.length === limit && lastRow
    ? lastRow.row_version
    : null;

  return { rows, nextCursor, serverVersion };
}
```

## Sync Endpoint — Full Multi-Table Delta

```typescript
// src/routes/sync.ts
import { queryDelta } from '../sync/delta-query';

interface SyncRequest {
  cursors: Record<string, number>; // { posts: 142, users: 89, comments: 0 }
}

interface SyncResponse {
  deltas: Record<string, { rows: unknown[]; nextCursor: number | null }>;
  serverVersion: number;
}

export async function handleSync(
  request: Request,
  env: { DB: D1Database },
): Promise<Response> {
  const body = await request.json<SyncRequest>();
  const cursors = body.cursors ?? {};

  const TABLE_CONFIGS: Array<{ table: string; cols: string[] }> = [
    { table: 'posts',    cols: ['id', 'user_id', 'title', 'body', 'created_at', 'row_version'] },
    { table: 'users',   cols: ['id', 'email', 'display_name', 'created_at', 'row_version'] },
    { table: 'comments', cols: ['id', 'post_id', 'user_id', 'body', 'created_at', 'row_version'] },
  ];

  const results = await Promise.all(
    TABLE_CONFIGS.map(({ table, cols }) =>
      queryDelta(env.DB, table, cols, cursors[table] ?? 0)
    )
  );

  const deltas: SyncResponse['deltas'] = {};
  let serverVersion = 0;

  TABLE_CONFIGS.forEach(({ table }, i) => {
    deltas[table] = { rows: results[i].rows, nextCursor: results[i].nextCursor };
    serverVersion = Math.max(serverVersion, results[i].serverVersion);
  });

  return new Response(JSON.stringify({ deltas, serverVersion }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## Handling Soft Deletes in Delta Sync

Deletions must be communicated to clients. A tombstone pattern prevents rows from disappearing silently.

```sql
-- Add deleted_at to synced tables
ALTER TABLE posts ADD COLUMN deleted_at INTEGER;

-- Soft delete trigger updates row_version so clients receive the tombstone
CREATE TRIGGER posts_soft_delete
AFTER UPDATE OF deleted_at ON posts
WHEN NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL
BEGIN
  UPDATE version_counter SET current = current + 1 WHERE id = 1;
  UPDATE posts SET row_version = (SELECT current FROM version_counter WHERE id = 1)
  WHERE rowid = NEW.rowid;
END;
```

```typescript
// Client-side: treat rows with deleted_at as deletions from the local cache
function applyDelta(localCache: Map<string, Post>, delta: Post[]): void {
  for (const row of delta) {
    if (row.deleted_at !== null) {
      localCache.delete(row.id);
    } else {
      localCache.set(row.id, row);
    }
  }
}
```

## Cursor Pagination for Large Deltas

When a client is far behind, a single sync response can exceed payload limits. Implement cursor-based pagination:

```typescript
// Client sync loop
async function fullSync(
  apiUrl: string,
  localCursors: Record<string, number>,
): Promise<Record<string, number>> {
  let cursors = { ...localCursors };
  let hasMore = true;

  while (hasMore) {
    const res = await fetch(`${apiUrl}/sync`, {
      method: 'POST',
      body: JSON.stringify({ cursors }),
      headers: { 'Content-Type': 'application/json' },
    });
    const data: SyncResponse = await res.json();

    // Apply and advance cursors
    hasMore = false;
    for (const [table, delta] of Object.entries(data.deltas)) {
      applyDeltaRows(table, delta.rows);
      if (delta.nextCursor !== null) {
        cursors[table] = delta.nextCursor;
        hasMore = true;
      }
    }
  }

  return cursors;
}
```

## Anti-patterns
- Using `updated_at` timestamps as sync cursors — clock skew between Workers or client devices can cause rows to be skipped if the server timestamp moves backwards
- Sending entire table dumps instead of deltas — bandwidth and latency scale with dataset size, not change volume
- Omitting deleted rows from the delta payload — clients will never learn about deletions and cache stale data indefinitely
- Interpolating table names directly from client input into SQL — always validate against a server-side allowlist

## Gotchas
- SQLite triggers run within the same transaction as the triggering statement; `version_counter` updates are atomic with the row update
- D1 triggers are supported as of the 2024 engine update; verify your database was created after that by checking `wrangler d1 info`
- `row_version` values are not gap-free — a rolled-back transaction increments the counter without persisting a row; clients must query `> cursor`, never `= cursor + 1`
- Very high write rates can cause trigger contention on the single-row `version_counter`; at extreme scale, switch to `unixepoch('subsec')` cast to INTEGER as a timestamp-based version

## Verification

```bash
# Seed and verify row_version stamping
wrangler d1 execute MY_DB --local --command \
  "INSERT INTO posts (id, user_id, title) VALUES ('p1', 'u1', 'Hello');"

wrangler d1 execute MY_DB --local --command \
  "SELECT id, title, row_version FROM posts;"
# row_version should be > 0

# Simulate delta query from cursor 0
wrangler d1 execute MY_DB --local --command \
  "SELECT id, title, row_version FROM posts WHERE row_version > 0 ORDER BY row_version LIMIT 10;"
```

## Related
- [d1-streaming-export-analytics-pipeline.md](d1-streaming-export-analytics-pipeline.md)
- [d1-triggers-computed-columns.md](d1-triggers-computed-columns.md)
- [d1-soft-delete-workers-middleware.md](d1-soft-delete-workers-middleware.md)
- [d1-crdt-offline-sync.md](d1-crdt-offline-sync.md)
- [d1-pagination-cursor-keyset.md](d1-pagination-cursor-keyset.md)

## Sources
- SQLite triggers: https://www.sqlite.org/lang_createtrigger.html
- Offline-first sync patterns: https://www.youtube.com/watch?v=WXYuI5TUHNs
- Cloudflare D1 triggers support: https://developers.cloudflare.com/d1/
