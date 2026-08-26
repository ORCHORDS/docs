# R2 Object Metadata Indexing with D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You store files in R2 but need to query them by size, content-type, custom tag, or full-text description. R2's native `list()` API returns a flat listing with limited server-side filtering — no SQL predicates, no text search. Listing 100 000 objects to find the ones tagged `type=invoice` is unworkable. You need a queryable index.

---

## Context

The pattern: maintain a D1 table that mirrors R2 object metadata. Every upload/delete operation writes to both R2 and D1 in the same Worker invocation. D1 becomes the query layer; R2 stays the storage layer. A Cron Trigger periodically detects orphans (rows in D1 with no matching R2 object, or R2 objects not in D1).

This is a dual-write architecture. The write order matters: write to R2 first (durable), then write to D1 (index). If the D1 write fails, the Cron Trigger repairs the index. Never write D1 first — a failed R2 upload would leave a phantom index row pointing to nothing.

---

## Solution

```typescript
// src/types.ts
export interface Env {
  DB: D1Database;
  BUCKET: R2Bucket;
}

export interface ObjectMeta {
  key: string;
  size: number;
  content_type: string;
  etag: string;
  description: string;
  tags: string;         // JSON array stored as TEXT
  owner_id: string;
  created_at: string;
  last_modified: string;
}

// src/object-store.ts
/**
 * Dual-write layer: R2 for bytes, D1 for queryable metadata.
 */
export class ObjectStore {
  constructor(
    private bucket: R2Bucket,
    private db: D1Database
  ) {}

  async put(
    key: string,
    body: ReadableStream | ArrayBuffer,
    options: {
      contentType: string;
      description?: string;
      tags?: string[];
      ownerId: string;
    }
  ): Promise<ObjectMeta> {
    const now = new Date().toISOString();

    // 1. Write to R2 first (durable storage).
    const r2Object = await this.bucket.put(key, body, {
      httpMetadata: { contentType: options.contentType },
      customMetadata: {
        description: options.description ?? '',
        owner_id: options.ownerId,
        tags: JSON.stringify(options.tags ?? []),
      },
    });

    const meta: ObjectMeta = {
      key,
      size: r2Object.size,
      content_type: options.contentType,
      etag: r2Object.etag,
      description: options.description ?? '',
      tags: JSON.stringify(options.tags ?? []),
      owner_id: options.ownerId,
      created_at: now,
      last_modified: now,
    };

    // 2. Index in D1 (queryable layer). Use INSERT OR REPLACE for idempotency.
    await this.db
      .prepare(
        `INSERT OR REPLACE INTO r2_index
         (key, size, content_type, etag, description, tags, owner_id, created_at, last_modified)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .bind(
        meta.key,
        meta.size,
        meta.content_type,
        meta.etag,
        meta.description,
        meta.tags,
        meta.owner_id,
        meta.created_at,
        meta.last_modified
      )
      .run();

    return meta;
  }

  async delete(key: string): Promise<void> {
    // Delete from R2 first.
    await this.bucket.delete(key);
    // Then remove from index.
    await this.db
      .prepare('DELETE FROM r2_index WHERE key = ?')
      .bind(key)
      .run();
  }

  /** Query by owner and optional content-type filter. */
  async listByOwner(
    ownerId: string,
    filter?: { contentType?: string; minSize?: number }
  ): Promise<ObjectMeta[]> {
    let sql = `SELECT * FROM r2_index WHERE owner_id = ?`;
    const bindings: (string | number)[] = [ownerId];

    if (filter?.contentType) {
      sql += ` AND content_type = ?`;
      bindings.push(filter.contentType);
    }
    if (filter?.minSize !== undefined) {
      sql += ` AND size >= ?`;
      bindings.push(filter.minSize);
    }
    sql += ` ORDER BY created_at DESC`;

    const result = await this.db
      .prepare(sql)
      .bind(...bindings)
      .all<ObjectMeta>();

    return result.results;
  }

  /** Full-text search on descriptions using FTS5. */
  async search(ownerId: string, query: string): Promise<ObjectMeta[]> {
    const result = await this.db
      .prepare(
        `SELECT r.*
         FROM r2_index r
         JOIN r2_index_fts f ON r.key = f.key
         WHERE f.r2_index_fts MATCH ?
           AND r.owner_id = ?
         ORDER BY rank
         LIMIT 50`
      )
      .bind(query, ownerId)
      .all<ObjectMeta>();

    return result.results;
  }

  /** Presigned-style access: get the R2 object directly. */
  async get(key: string): Promise<R2ObjectBody | null> {
    return this.bucket.get(key);
  }
}

// src/cron.ts
/**
 * Orphan detection: run in a Cron Trigger (e.g., every 6 hours).
 *
 * Finds D1 index rows with no corresponding R2 object and removes them.
 * Also finds R2 objects not in the D1 index and re-indexes them.
 */
export async function syncIndex(env: Env): Promise<{ removed: number; repaired: number }> {
  let removed = 0;
  let repaired = 0;

  // Phase 1: Find index rows whose R2 object no longer exists.
  const indexRows = await env.DB
    .prepare('SELECT key FROM r2_index ORDER BY created_at DESC LIMIT 500')
    .all<{ key: string }>();

  const orphanKeys: string[] = [];
  await Promise.all(
    indexRows.results.map(async ({ key }) => {
      const head = await env.BUCKET.head(key);
      if (!head) orphanKeys.push(key);
    })
  );

  if (orphanKeys.length > 0) {
    // Batch delete orphan index rows.
    const statements = orphanKeys.map(key =>
      env.DB.prepare('DELETE FROM r2_index WHERE key = ?').bind(key)
    );
    await env.DB.batch(statements);
    removed = orphanKeys.length;
  }

  // Phase 2: List R2 objects missing from the index (up to 1000 per run).
  const listed = await env.BUCKET.list({ limit: 1000 });
  const indexedKeys = new Set(
    (await env.DB.prepare('SELECT key FROM r2_index').all<{ key: string }>()).results.map(r => r.key)
  );

  const missing = listed.objects.filter(obj => !indexedKeys.has(obj.key));
  for (const obj of missing) {
    const full = await env.BUCKET.head(obj.key);
    if (!full) continue;
    const now = new Date().toISOString();
    await env.DB
      .prepare(
        `INSERT OR IGNORE INTO r2_index
         (key, size, content_type, etag, description, tags, owner_id, created_at, last_modified)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .bind(
        obj.key,
        obj.size,
        full.httpMetadata?.contentType ?? 'application/octet-stream',
        obj.etag,
        full.customMetadata?.description ?? '',
        full.customMetadata?.tags ?? '[]',
        full.customMetadata?.owner_id ?? 'unknown',
        full.uploaded.toISOString(),
        now
      )
      .run();
    repaired++;
  }

  return { removed, repaired };
}

// src/worker.ts
import { ObjectStore } from './object-store';
import { syncIndex } from './cron';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const store = new ObjectStore(env.BUCKET, env.DB);

    if (url.pathname === '/upload' && request.method === 'POST') {
      const key = url.searchParams.get('key');
      const ownerId = request.headers.get('X-Owner-Id');
      if (!key || !ownerId) return new Response('Bad Request', { status: 400 });

      const contentType = request.headers.get('Content-Type') ?? 'application/octet-stream';
      const description = request.headers.get('X-Description') ?? '';
      const tags = request.headers.get('X-Tags')?.split(',').map(t => t.trim()) ?? [];

      const meta = await store.put(key, request.body!, {
        contentType,
        description,
        tags,
        ownerId,
      });
      return Response.json(meta, { status: 201 });
    }

    if (url.pathname === '/search' && request.method === 'GET') {
      const ownerId = request.headers.get('X-Owner-Id');
      const query = url.searchParams.get('q');
      if (!ownerId || !query) return new Response('Bad Request', { status: 400 });
      const results = await store.search(ownerId, query);
      return Response.json(results);
    }

    return new Response('Not Found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const stats = await syncIndex(env);
    console.log('Index sync complete', stats);
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

**Schema:**
```sql
CREATE TABLE r2_index (
  key           TEXT PRIMARY KEY,
  size          INTEGER NOT NULL,
  content_type  TEXT NOT NULL,
  etag          TEXT NOT NULL,
  description   TEXT NOT NULL DEFAULT '',
  tags          TEXT NOT NULL DEFAULT '[]',
  owner_id      TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  last_modified TEXT NOT NULL
);

CREATE INDEX idx_r2_owner_created ON r2_index (owner_id, created_at DESC);
CREATE INDEX idx_r2_content_type  ON r2_index (content_type);

-- FTS5 virtual table for description search.
CREATE VIRTUAL TABLE r2_index_fts
  USING fts5(key UNINDEXED, description, content='r2_index', content_rowid='rowid');

-- Triggers to keep FTS in sync.
CREATE TRIGGER r2_index_ai AFTER INSERT ON r2_index BEGIN
  INSERT INTO r2_index_fts(rowid, key, description) VALUES (new.rowid, new.key, new.description);
END;
CREATE TRIGGER r2_index_ad AFTER DELETE ON r2_index BEGIN
  INSERT INTO r2_index_fts(r2_index_fts, rowid, key, description)
    VALUES ('delete', old.rowid, old.key, old.description);
END;
CREATE TRIGGER r2_index_au AFTER UPDATE ON r2_index BEGIN
  INSERT INTO r2_index_fts(r2_index_fts, rowid, key, description)
    VALUES ('delete', old.rowid, old.key, old.description);
  INSERT INTO r2_index_fts(rowid, key, description) VALUES (new.rowid, new.key, new.description);
END;
```

**`wrangler.toml` bindings:**
```toml
[[r2_buckets]]
binding = "BUCKET"
bucket_name = "my-assets"

[[d1_databases]]
binding = "DB"
database_name = "metadata-index"
database_id = "<uuid>"

[triggers]
crons = ["0 */6 * * *"]
```

---

## Anti-patterns

```typescript
// BAD: writing D1 before R2 — phantom index rows if R2 put fails
await db.prepare('INSERT INTO r2_index ...').run();
await bucket.put(key, body); // If this throws, the index has a ghost row.

// BAD: using R2.list() to filter objects at query time
const all = await bucket.list();
const invoices = all.objects.filter(o => o.customMetadata?.type === 'invoice');
// ^ O(n) cost, not paginated, extremely slow on large buckets.

// BAD: trusting R2 size from the client instead of r2Object.size
const meta = { size: parseInt(request.headers.get('Content-Length') ?? '0') };
// ^ Use r2Object.size from the put() return value — it's the actual bytes stored.
```

---

## Gotchas

- **FTS5 content tables** (`content='r2_index'`) are not self-updating — the triggers above are mandatory. Without them, `MATCH` queries return stale results.
- **R2 `list()` pagination:** In `syncIndex`, the example is simplified to `limit: 1000`. For large buckets, iterate with `cursor` until `listed.truncated === false`.
- **`INSERT OR REPLACE` vs `INSERT OR IGNORE`:** Use `REPLACE` in the upload path (an re-upload of the same key should update the index). Use `IGNORE` in the repair path (the index row may already exist from a concurrent upload).
- **`bucket.head()` costs money.** Head requests are billed per-call. In the sync Cron, batch the R2 existence checks — do not call `head()` for every row on every run; use change-detection via `etag` or `last_modified` to skip unchanged objects.

---

## Verification

```typescript
// test/r2-index.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { ObjectStore } from '../src/object-store';

describe('R2 metadata index', () => {
  let store: ObjectStore;

  beforeEach(async () => {
    const db = getMiniflareD1('DB');
    const bucket = getMiniflareR2('BUCKET');
    await db.exec(SCHEMA_SQL);
    store = new ObjectStore(bucket, db);
  });

  it('indexes metadata after put', async () => {
    await store.put('invoices/2026-01.pdf', new Uint8Array([1, 2, 3]), {
      contentType: 'application/pdf',
      description: 'January 2026 invoice',
      tags: ['invoice', 'finance'],
      ownerId: 'user-a',
    });
    const results = await store.listByOwner('user-a', { contentType: 'application/pdf' });
    expect(results).toHaveLength(1);
    expect(results[0].key).toBe('invoices/2026-01.pdf');
  });

  it('removes index row on delete', async () => {
    await store.put('tmp/file.txt', new Uint8Array([42]), {
      contentType: 'text/plain',
      ownerId: 'user-b',
    });
    await store.delete('tmp/file.txt');
    const results = await store.listByOwner('user-b');
    expect(results).toHaveLength(0);
  });
});
```

---

## Related

- `workers-d1-full-text-search.md` — FTS5 setup and query patterns used by the search method above
- `workers-d1-row-level-security.md` — `owner_id` scoping in WHERE clauses
- `workers-d1-soft-delete-pattern.md` — apply soft-delete to the index instead of hard-delete to enable trash/recovery

---

## Sources

- Cloudflare R2 Workers API: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- D1 FTS5 support: https://developers.cloudflare.com/d1/sql-api/sql-sqlite/#fts5-full-text-search
- SQLite FTS5 content tables: https://www.sqlite.org/fts5.html#external_content_tables
