# Row-Level Security in Cloudflare D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker serves multiple tenants from a single D1 database. Without explicit per-row user filtering enforced at the SQL layer, a bug in application routing logic, a missing middleware check, or a confused request context can silently return rows belonging to another tenant. You need a guarantee that every query is structurally incapable of returning data outside the authenticated user's scope.

---

## Context

D1 is SQLite-compatible and has no native row-level security (RLS) primitive like PostgreSQL's `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`. All access control must be encoded directly in SQL `WHERE` clauses using bound parameters. The pattern is to thread a verified `user_id` (from a JWT, session, or Cloudflare Access identity) into every query as a parameterized binding — never as string interpolation — so SQLite's query planner enforces the predicate at the storage layer.

This is sometimes called "application-enforced RLS". When done consistently it is as safe as database-native RLS because:
- SQLite parameterized bindings cannot be escaped by user input.
- The `user_id` comes from a verified token, not a request body field.
- A composite index on `(user_id, id)` makes the filter free (index seek, not scan).

---

## Solution

```typescript
// src/types.ts
export interface Env {
  DB: D1Database;
}

export interface AuthContext {
  userId: string;
  email: string;
}

export interface Document {
  id: string;
  user_id: string;
  title: string;
  body: string;
  created_at: string;
  updated_at: string;
}

// src/auth.ts
/**
 * Extract and verify the caller identity.
 * In production this validates a signed JWT or Cloudflare Access JWT.
 * Returns null when the token is absent or invalid.
 */
export async function resolveAuth(
  request: Request
): Promise<AuthContext | null> {
  const authHeader = request.headers.get('Authorization');
  if (!authHeader?.startsWith('Bearer ')) return null;

  const token = authHeader.slice(7);
  // Replace with real JWT verification (e.g. using crypto.subtle).
  const payload = parseJwtPayload(token);
  if (!payload?.sub) return null;

  return { userId: payload.sub, email: payload.email ?? '' };
}

function parseJwtPayload(token: string): Record<string, string> | null {
  try {
    const [, b64] = token.split('.');
    const json = atob(b64.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

// src/documents.ts
/**
 * Data-access layer — every function requires an explicit userId.
 * The userId is ALWAYS bound as a SQL parameter, never interpolated.
 */
export class DocumentRepository {
  constructor(private db: D1Database) {}

  /** List all documents belonging to the caller. */
  async list(userId: string): Promise<Document[]> {
    const result = await this.db
      .prepare(
        `SELECT id, user_id, title, body, created_at, updated_at
         FROM documents
         WHERE user_id = ?
         ORDER BY created_at DESC
         LIMIT 100`
      )
      .bind(userId)
      .all<Document>();

    return result.results;
  }

  /** Fetch a single document — fails silently if it belongs to another user. */
  async get(userId: string, documentId: string): Promise<Document | null> {
    return this.db
      .prepare(
        `SELECT id, user_id, title, body, created_at, updated_at
         FROM documents
         WHERE id = ? AND user_id = ?`
      )
      .bind(documentId, userId)
      .first<Document>();
  }

  /** Update — the WHERE clause makes cross-user mutation structurally impossible. */
  async update(
    userId: string,
    documentId: string,
    patch: { title?: string; body?: string }
  ): Promise<boolean> {
    const now = new Date().toISOString();
    const result = await this.db
      .prepare(
        `UPDATE documents
         SET title = COALESCE(?, title),
             body  = COALESCE(?, body),
             updated_at = ?
         WHERE id = ? AND user_id = ?`
      )
      .bind(patch.title ?? null, patch.body ?? null, now, documentId, userId)
      .run();

    return result.meta.changes > 0;
  }

  /** Delete — same pattern, user_id in WHERE. */
  async delete(userId: string, documentId: string): Promise<boolean> {
    const result = await this.db
      .prepare('DELETE FROM documents WHERE id = ? AND user_id = ?')
      .bind(documentId, userId)
      .run();

    return result.meta.changes > 0;
  }

  /** Audit: count documents across all users (admin only). */
  async auditAccessLog(adminUserId: string): Promise<{ user_id: string; count: number }[]> {
    // Only call this from an admin-gated route.
    const result = await this.db
      .prepare(
        `SELECT user_id, COUNT(*) as count
         FROM documents
         GROUP BY user_id
         ORDER BY count DESC`
      )
      .all<{ user_id: string; count: number }>();

    return result.results;
  }
}

// src/worker.ts
import { DocumentRepository } from './documents';
import { resolveAuth } from './auth';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const auth = await resolveAuth(request);
    if (!auth) {
      return new Response('Unauthorized', { status: 401 });
    }

    const url = new URL(request.url);
    const repo = new DocumentRepository(env.DB);

    if (url.pathname === '/documents' && request.method === 'GET') {
      const docs = await repo.list(auth.userId);
      return Response.json(docs);
    }

    const match = url.pathname.match(/^\/documents\/([\w-]+)$/);
    if (match) {
      const documentId = match[1];

      if (request.method === 'GET') {
        const doc = await repo.get(auth.userId, documentId);
        if (!doc) return new Response('Not Found', { status: 404 });
        return Response.json(doc);
      }

      if (request.method === 'PATCH') {
        const patch = await request.json<{ title?: string; body?: string }>();
        const updated = await repo.update(auth.userId, documentId, patch);
        if (!updated) return new Response('Not Found', { status: 404 });
        return new Response(null, { status: 204 });
      }

      if (request.method === 'DELETE') {
        const deleted = await repo.delete(auth.userId, documentId);
        if (!deleted) return new Response('Not Found', { status: 404 });
        return new Response(null, { status: 204 });
      }
    }

    return new Response('Not Found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

**Schema with composite index:**
```sql
CREATE TABLE documents (
  id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id    TEXT NOT NULL,
  title      TEXT NOT NULL,
  body       TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Critical: composite index makes (user_id, id) lookups O(log n) instead of full-scan.
CREATE INDEX idx_documents_user_id_created
  ON documents (user_id, created_at DESC);

CREATE INDEX idx_documents_user_id_id
  ON documents (user_id, id);
```

**Repository constructor pattern:** Pass `userId` into every method rather than storing it on the instance. This makes it impossible to accidentally call a method without binding the user scope — the TypeScript type system enforces it.

**Middleware enforcement:** In a router (Hono, itty-router), attach auth resolution to every route group under `/documents/` so the `userId` is always present before reaching the repository layer.

---

## Anti-patterns

```typescript
// BAD: filtering in application code after fetching all rows
const all = await db.prepare('SELECT * FROM documents').all<Document>();
const mine = all.results.filter(d => d.user_id === userId); // Cross-tenant data hit the runtime

// BAD: string interpolation — SQL injection risk
const sql = `SELECT * FROM documents WHERE user_id = '${userId}'`;
await db.prepare(sql).all();

// BAD: trusting a user-supplied user_id from the request body
const { userId } = await request.json(); // Attacker controls this value
await repo.list(userId);
```

---

## Gotchas

- **`meta.changes === 0` is not an error.** For `GET` operations, a `null` result from `.first()` already means no row matched. For mutations, `changes === 0` means either the row doesn't exist OR it belongs to another user — return 404 either way; do not reveal which.
- **Admin routes need a separate access check** before calling `auditAccessLog`. Never derive admin status from a JWT field without verifying it with a secondary source (e.g., a KV allowlist of admin user IDs).
- **Batch queries:** When using `db.batch([...])`, each statement in the batch still needs its own parameterized `user_id` binding. The batch API does not share bindings across statements.
- **`EXPLAIN QUERY PLAN`** in the D1 dashboard should show `SEARCH documents USING INDEX` for your filtered queries. If it shows `SCAN documents`, the composite index is missing or not being used.

---

## Verification

```typescript
// test/rls.test.ts — vitest with miniflare
import { describe, it, expect, beforeEach } from 'vitest';
import { DocumentRepository } from '../src/documents';

describe('Row-level security isolation', () => {
  let db: D1Database;
  let repo: DocumentRepository;

  beforeEach(async () => {
    // Miniflare provides an in-memory D1 instance.
    db = getMiniflareD1('DB');
    await db.exec(SCHEMA_SQL);
    repo = new DocumentRepository(db);

    // Seed: user-A owns doc-1, user-B owns doc-2.
    await db
      .prepare("INSERT INTO documents (id, user_id, title) VALUES ('doc-1', 'user-a', 'A doc')")
      .run();
    await db
      .prepare("INSERT INTO documents (id, user_id, title) VALUES ('doc-2', 'user-b', 'B doc')")
      .run();
  });

  it('user-a cannot read user-b document via get()', async () => {
    const doc = await repo.get('user-a', 'doc-2');
    expect(doc).toBeNull();
  });

  it('user-b cannot delete user-a document', async () => {
    const deleted = await repo.delete('user-b', 'doc-1');
    expect(deleted).toBe(false);
    // Confirm doc-1 still exists
    const still = await repo.get('user-a', 'doc-1');
    expect(still).not.toBeNull();
  });

  it('list() returns only the calling user documents', async () => {
    const docs = await repo.list('user-a');
    expect(docs).toHaveLength(1);
    expect(docs[0].id).toBe('doc-1');
  });
});
```

---

## Related

- `workers-d1-soft-delete-pattern.md` — soft deletes require the same per-user WHERE clause plus `deleted_at IS NULL`
- `workers-d1-batch-writes.md` — batch insert patterns that preserve user_id bindings
- `hyperdrive-postgres.md` — Postgres native RLS as an alternative for Hyperdrive-backed workloads

---

## Sources

- Cloudflare D1 docs — Parameterized queries: https://developers.cloudflare.com/d1/worker-api/prepared-statements/
- SQLite EXPLAIN QUERY PLAN: https://www.sqlite.org/eqp.html
- OWASP — Insecure Direct Object Reference: https://owasp.org/www-community/attacks/IDOR
