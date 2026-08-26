# Optimistic Locking in D1 with a Version Column

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Two Workers requests concurrently read a row, compute an update, and write back. Without coordination, the second write silently overwrites the first — a lost-update anomaly. D1's SQLite does not support SELECT FOR UPDATE, so pessimistic locking is unavailable. Optimistic locking with a `version` column prevents lost updates without holding locks.

## Context

Optimistic locking appends `AND version = <expected>` to every `UPDATE`. If another writer incremented the version between your read and write, your update affects 0 rows. You detect the conflict via `meta.changes === 0` and either retry or surface a 409 to the client. This is safe because D1 executes each statement atomically.

---

## Schema

```sql
CREATE TABLE IF NOT EXISTS documents (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  title       TEXT    NOT NULL,
  body        TEXT    NOT NULL,
  owner_id    INTEGER NOT NULL,
  version     INTEGER NOT NULL DEFAULT 1,   -- incremented on every write
  updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_docs_owner ON documents(owner_id);
```

---

## Read–Modify–Write Pattern

```typescript
// src/optimistic.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface Document {
  id:         number;
  title:      string;
  body:       string;
  owner_id:   number;
  version:    number;
  updated_at: string;
}

export class ConflictError extends Error {
  constructor(public readonly id: number, public readonly observedVersion: number) {
    super(`Conflict on document ${id} at version ${observedVersion}`);
    this.name = 'ConflictError';
  }
}

/** Read the current document. */
export async function getDocument(
  db: D1Database,
  id: number
): Promise<Document | null> {
  return db
    .prepare('SELECT * FROM documents WHERE id = ?')
    .bind(id)
    .first<Document>();
}

/**
 * Update a document using optimistic locking.
 * Pass the `version` value you read earlier.
 * Throws ConflictError if the row was updated by someone else.
 */
export async function updateDocument(
  db: D1Database,
  id: number,
  patch: { title?: string; body?: string },
  expectedVersion: number
): Promise<Document> {
  const fields: string[] = [];
  const values: unknown[] = [];

  if (patch.title !== undefined) { fields.push('title = ?');      values.push(patch.title); }
  if (patch.body  !== undefined) { fields.push('body = ?');       values.push(patch.body);  }

  if (fields.length === 0) throw new Error('No fields to update');

  // Always bump version and updated_at
  fields.push('version = version + 1');
  fields.push("updated_at = datetime('now')");

  // Bind positional params: patch values + id + expected version
  const { meta } = await db
    .prepare(
      `UPDATE documents
       SET ${fields.join(', ')}
       WHERE id = ? AND version = ?`
    )
    .bind(...values, id, expectedVersion)
    .run();

  if (meta.changes === 0) {
    // Either row doesn't exist, or version mismatch — treat as conflict
    throw new ConflictError(id, expectedVersion);
  }

  // Return the updated row
  const updated = await getDocument(db, id);
  return updated!;
}
```

---

## Retry Logic in Workers

```typescript
// src/optimistic.ts (continued)

export interface RetryOptions {
  maxAttempts?: number;   // default 3
  backoffMs?:   number;   // initial backoff in ms, doubles each retry
}

/**
 * Retry updateDocument on ConflictError: re-read the row and recompute the patch.
 * `patchFn` receives the latest document and returns the patch to apply.
 */
export async function updateWithRetry(
  db: D1Database,
  id: number,
  patchFn: (doc: Document) => { title?: string; body?: string },
  { maxAttempts = 3, backoffMs = 20 }: RetryOptions = {}
): Promise<Document> {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const doc = await getDocument(db, id);
    if (!doc) throw new Error(`Document ${id} not found`);

    const patch = patchFn(doc);

    try {
      return await updateDocument(db, id, patch, doc.version);
    } catch (err) {
      if (!(err instanceof ConflictError)) throw err;   // unexpected error, re-throw
      if (attempt === maxAttempts) throw err;           // out of retries

      // Exponential back-off using a non-blocking pause
      await new Promise<void>((res) => setTimeout(res, backoffMs * 2 ** (attempt - 1)));
    }
  }
  /* istanbul ignore next — loop always returns or throws */
  throw new Error('unreachable');
}
```

---

## Worker Handler

```typescript
// src/worker.ts
import { getDocument, updateDocument, updateWithRetry, ConflictError } from './optimistic';

export interface Env { DB: D1Database; }

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url  = new URL(req.url);
    const id   = Number(url.pathname.split('/')[2]);   // /docs/:id

    if (req.method === 'GET') {
      const doc = await getDocument(env.DB, id);
      if (!doc) return new Response('Not found', { status: 404 });
      return Response.json(doc);
    }

    if (req.method === 'PATCH') {
      const body = await req.json<{ title?: string; body?: string; version: number }>();
      const { version, ...patch } = body;

      try {
        const updated = await updateDocument(env.DB, id, patch, version);
        return Response.json(updated);
      } catch (err) {
        if (err instanceof ConflictError) {
          return Response.json(
            { error: 'conflict', message: err.message },
            { status: 409 }
          );
        }
        throw err;
      }
    }

    // Auto-retry endpoint (server-side merge)
    if (req.method === 'POST' && url.pathname.endsWith('/append')) {
      const { text } = await req.json<{ text: string }>();
      const updated = await updateWithRetry(
        env.DB,
        id,
        (doc) => ({ body: doc.body + '\n' + text })
      );
      return Response.json(updated);
    }

    return new Response('Method not allowed', { status: 405 });
  },
};
```

---

## Detecting Stale Reads on the Client

When a client sends a `PATCH` and receives a 409, the canonical response is:

```json
{
  "error": "conflict",
  "message": "Conflict on document 42 at version 7"
}
```

The client should:
1. Re-fetch the document (`GET /docs/42`) to get the latest version and content.
2. Show a merge UI or re-apply the user's change on top of the latest content.
3. Resubmit the `PATCH` with the new `version` value.

---

## Anti-patterns

- **Omitting the version check** — `UPDATE ... WHERE id = ?` without `AND version = ?` silently clobbers concurrent writes.
- **Using timestamps instead of integers** — clock skew between Workers instances makes timestamp comparisons unreliable; use a monotonically incrementing integer.
- **Infinite retry loops** — always cap retries (`maxAttempts`) and surface a 409 to the caller once retries are exhausted.
- **Bumping version in application code** — always use `version = version + 1` inside the SQL to avoid race conditions between the read and the write.

---

## Gotchas

- `meta.changes` is `0` both when the row does not exist and when the version does not match. Distinguish these cases if needed by first checking `getDocument()` returns non-null.
- D1's `db.batch()` runs statements sequentially but each statement is still independently atomic. For multi-row optimistic updates, batch all `UPDATE` statements and check each `meta.changes`.
- Workers have a 50 ms CPU time budget per request (Bundled plan) and 30 s wall-clock. Retries with `setTimeout` consume wall-clock but not CPU time, so up to 3 retries with exponential back-off is safe.

---

## Verification

```bash
# Seed a document
wrangler d1 execute MY_DB \
  --command "INSERT INTO documents (title, body, owner_id) VALUES ('Hello', 'World', 1);"

# Read it (note version=1)
curl https://my-worker.example.com/docs/1
# {"id":1,"title":"Hello","body":"World","owner_id":1,"version":1,...}

# Update with correct version
curl -X PATCH https://my-worker.example.com/docs/1 \
  -H 'Content-Type: application/json' \
  -d '{"body":"Updated body","version":1}'
# {"id":1,"version":2,...}

# Update with stale version (simulate conflict)
curl -X PATCH https://my-worker.example.com/docs/1 \
  -H 'Content-Type: application/json' \
  -d '{"body":"Lost update","version":1}'
# HTTP 409 {"error":"conflict",...}
```

---

## Related

- `d1-materialized-view-refresh-workers.md` — concurrent cron refreshes that need safe writes
- `d1-archive-hot-cold-partition.md` — archiving rows safely with version checks
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/worker-api/d1-database/#run

## Sources

- Optimistic locking overview: https://martinfowler.com/eaaCatalog/optimisticOfflineLock.html
- SQLite `changes()`: https://www.sqlite.org/lang_corefunc.html#changes
