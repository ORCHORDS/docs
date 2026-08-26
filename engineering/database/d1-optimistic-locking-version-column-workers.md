# D1 Optimistic Concurrency Control with Version Columns

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
Two API clients read the same D1 row at the same time, both modify it, and both attempt to
write it back — the last writer wins and silently overwrites the first writer's changes,
creating a lost-update bug with no error surfaced to the client.

## Context
Pessimistic locking (SELECT … FOR UPDATE) does not exist in SQLite/D1. The standard SQLite
alternative is optimistic concurrency control (OCC): each row carries a monotonically
increasing `version` integer. A writer reads the current `version`, performs its computation,
and issues an UPDATE that includes `WHERE id = ? AND version = <read_version>`. If another
writer already incremented the version, the UPDATE matches 0 rows and the application retries
or surfaces a 409 Conflict. This is safe to implement in D1 because D1 serializes all writes
within a single request and the `rows_written` field of `D1Result` reports whether the UPDATE
actually matched. The approach requires no extra infrastructure and scales to the edge.

## Schema

```sql
-- migrations/0001_documents.sql
CREATE TABLE IF NOT EXISTS documents (
  id          TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  tenant_id   TEXT    NOT NULL,
  title       TEXT    NOT NULL,
  body        TEXT    NOT NULL DEFAULT '',
  version     INTEGER NOT NULL DEFAULT 1,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_documents_tenant
  ON documents (tenant_id, updated_at DESC);

-- Optional: conflict audit trail
CREATE TABLE IF NOT EXISTS document_conflicts (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id      TEXT    NOT NULL,
  attempted_version INTEGER NOT NULL,
  current_version  INTEGER NOT NULL,
  rejected_at      INTEGER NOT NULL DEFAULT (unixepoch())
);
```

## TypeScript OCC Helper

```typescript
// src/occ.ts

export class OptimisticLockError extends Error {
  constructor(
    public readonly documentId: string,
    public readonly attemptedVersion: number,
    public readonly currentVersion: number
  ) {
    super(
      `Optimistic lock conflict on ${documentId}: ` +
      `attempted version ${attemptedVersion}, current version ${currentVersion}`
    );
    this.name = 'OptimisticLockError';
  }
}

export interface Document {
  id: string;
  tenant_id: string;
  title: string;
  body: string;
  version: number;
  updated_at: number;
}

export async function getDocument(
  db: D1Database,
  id: string,
  tenantId: string
): Promise<Document | null> {
  return db
    .prepare('SELECT id, tenant_id, title, body, version, updated_at FROM documents WHERE id = ?1 AND tenant_id = ?2')
    .bind(id, tenantId)
    .first<Document>();
}

export async function updateDocument(
  db: D1Database,
  id: string,
  tenantId: string,
  expectedVersion: number,
  patch: Partial<Pick<Document, 'title' | 'body'>>
): Promise<Document> {
  const result = await db
    .prepare(`
      UPDATE documents
         SET title      = COALESCE(?3, title),
             body       = COALESCE(?4, body),
             version    = version + 1,
             updated_at = unixepoch()
       WHERE id        = ?1
         AND tenant_id = ?2
         AND version   = ?5
      RETURNING id, tenant_id, title, body, version, updated_at
    `)
    .bind(id, tenantId, patch.title ?? null, patch.body ?? null, expectedVersion)
    .first<Document>();

  if (!result) {
    // The WHERE matched 0 rows — either the document is gone or the version changed.
    const current = await db
      .prepare('SELECT version FROM documents WHERE id = ?1 AND tenant_id = ?2')
      .bind(id, tenantId)
      .first<{ version: number }>();

    if (!current) throw new Error(`Document ${id} not found`);

    throw new OptimisticLockError(id, expectedVersion, current.version);
  }

  return result;
}
```

## Worker Entrypoint

```typescript
// src/index.ts
import { getDocument, updateDocument, OptimisticLockError } from './occ';

export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url     = new URL(request.url);
    const tenantId = request.headers.get('X-Tenant-Id') ?? 'anon';
    const match   = url.pathname.match(/^\/documents\/([^/]+)$/);
    if (!match) return new Response('Not found', { status: 404 });
    const docId = match[1];

    if (request.method === 'GET') {
      const doc = await getDocument(env.DB, docId, tenantId);
      if (!doc) return new Response('Not found', { status: 404 });
      // Return ETag from version so HTTP clients can use If-Match
      return Response.json(doc, {
        headers: { 'ETag': `"${doc.version}"` },
      });
    }

    if (request.method === 'PATCH') {
      // Client sends the version it read in the If-Match header
      const ifMatch = request.headers.get('If-Match');
      if (!ifMatch) {
        return new Response('If-Match header required', { status: 428 });
      }
      const expectedVersion = parseInt(ifMatch.replace(/"/g, ''), 10);
      if (Number.isNaN(expectedVersion)) {
        return new Response('Invalid If-Match value', { status: 400 });
      }

      const body = await request.json<{ title?: string; body?: string }>();

      try {
        const updated = await updateDocument(
          env.DB, docId, tenantId, expectedVersion, body
        );
        return Response.json(updated, {
          headers: { 'ETag': `"${updated.version}"` },
        });
      } catch (err) {
        if (err instanceof OptimisticLockError) {
          return Response.json(
            { error: 'conflict', currentVersion: err.currentVersion },
            { status: 409 }
          );
        }
        throw err;
      }
    }

    return new Response('Method not allowed', { status: 405 });
  },
};
```

## Client-Side Retry Loop

```typescript
// Example TypeScript fetch client with automatic OCC retry
async function patchWithRetry(
  url: string,
  tenantId: string,
  patch: { title?: string; body?: string },
  maxRetries = 3
): Promise<unknown> {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    // 1. Fetch fresh copy to get current version via ETag
    const getRes = await fetch(url, { headers: { 'X-Tenant-Id': tenantId } });
    const etag   = getRes.headers.get('ETag') ?? '"1"';

    // 2. Attempt update with the current ETag
    const patchRes = await fetch(url, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-Id': tenantId,
        'If-Match': etag,
      },
      body: JSON.stringify(patch),
    });

    if (patchRes.ok) return patchRes.json();

    if (patchRes.status === 409 && attempt < maxRetries - 1) {
      // Exponential back-off: 50ms, 100ms, 200ms
      await new Promise((r) => setTimeout(r, 50 * 2 ** attempt));
      continue;
    }

    throw new Error(`Update failed: ${patchRes.status}`);
  }
  throw new Error('Max retries exceeded');
}
```

## Anti-patterns
- Incrementing `version` unconditionally in application code without checking `rows_written` — you lose the conflict signal.
- Using `timestamp` instead of `version` as the optimistic lock column — two updates in the same second have the same timestamp and no conflict is detected.
- Retrying inside the Worker without re-reading the row — the retry applies the patch on top of an already-stale snapshot.
- Not surfacing 409 to the client — silently swallowing the conflict and applying the update anyway defeats the purpose entirely.
- Using OCC for high-contention hot rows (e.g. a global view counter) — the conflict rate will be very high; use a Durable Object or atomic SQL expression instead.

## Gotchas
- D1's `RETURNING` clause on an UPDATE that matches 0 rows returns no rows but does not throw — always check `result === null` rather than `result.meta.rows_written`.
- `version` column must be `NOT NULL` — a `NULL` version makes `version = ?5` evaluate to `NULL` (unknown), which never matches, causing every update to fail silently.
- In a D1 batch, OCC updates must be the last statement; use `batch.run()` and check `results[n].meta.rows_written` individually.
- Multi-row OCC (updating multiple related rows atomically) requires a transaction with savepoints; a failed version check on row N must roll back rows 0–N-1.
- ETag via HTTP `If-Match` is the REST standard for OCC; use it to avoid inventing a custom `?version=` query-param protocol.

## Verification

```bash
npx wrangler deploy

# Create a document
DOC_ID=$(curl -s -X POST https://<worker>.workers.dev/documents \
  -H 'X-Tenant-Id: t1' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Hello","body":"World"}' | jq -r .id)

# Read it — note the ETag
curl -v "https://<worker>.workers.dev/documents/$DOC_ID" \
  -H 'X-Tenant-Id: t1' 2>&1 | grep -E 'ETag|version'

# Successful update with correct version
curl -X PATCH "https://<worker>.workers.dev/documents/$DOC_ID" \
  -H 'X-Tenant-Id: t1' \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "1"' \
  -d '{"title":"Updated"}'
# => 200 with version:2

# Stale-version conflict
curl -X PATCH "https://<worker>.workers.dev/documents/$DOC_ID" \
  -H 'X-Tenant-Id: t1' \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "1"' \
  -d '{"title":"Conflict"}'
# => 409 {"error":"conflict","currentVersion":2}
```

## Related
- [d1-durable-objects-serialized-writes-workers.md](d1-durable-objects-serialized-writes-workers.md)
- [d1-upsert-conflict-resolution-workers.md](d1-upsert-conflict-resolution-workers.md)
- [d1-returning-clause-upsert-workers.md](d1-returning-clause-upsert-workers.md)
- [optimistic-locking-version-column.md](optimistic-locking-version-column.md)
- [d1-savepoint-nested-transaction-workers.md](d1-savepoint-nested-transaction-workers.md)

## Sources
- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/lang_update.html
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/If-Match
- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
