# Optimistic Locking with Cloudflare D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Two Workers handle concurrent `PATCH /resource/:id` requests. Without a concurrency guard, the second write silently overwrites the first — a lost update. You need a lightweight mechanism that detects conflicts and returns `409 Conflict` so clients can re-read and re-apply their changes, without reaching for distributed locks or serializable transactions.

---

## Context

Optimistic locking assumes conflicts are rare. Each row carries a monotonic `version` integer (or an opaque `etag` string). The client reads the row and receives the current version. On update, the client sends `version` back. The SQL `UPDATE` statement includes `AND version = ?` in its `WHERE` clause, so the update only lands if nobody else changed the row in the interim. D1's `meta.changes` property tells you whether the update matched any rows. Zero changes means a conflict occurred.

Because D1 runs SQLite, which serializes all writes within a single session, this pattern is safe: two concurrent Workers will serialize at the database, and the second writer's `meta.changes` will be `0`.

---

## Solution

```typescript
// src/types.ts
export interface Env {
  DB: D1Database;
}

export interface Resource {
  id: string;
  name: string;
  payload: string;
  version: number;
  updated_at: string;
}

export type ConflictError = { type: 'conflict'; currentVersion: number };
export type NotFoundError = { type: 'not_found' };
export type UpdateResult =
  | { type: 'ok'; resource: Resource }
  | ConflictError
  | NotFoundError;

// src/repository.ts
export class ResourceRepository {
  constructor(private db: D1Database) {}

  async get(id: string): Promise<Resource | null> {
    return this.db
      .prepare(
        `SELECT id, name, payload, version, updated_at
         FROM resources
         WHERE id = ?`
      )
      .bind(id)
      .first<Resource>();
  }

  /**
   * Attempt an optimistic update.
   *
   * The UPDATE only matches when `version` equals the client's expected value.
   * `meta.changes === 0` means either the row is gone or a concurrent writer
   * incremented the version first — we distinguish these with a follow-up read.
   */
  async update(
    id: string,
    patch: { name?: string; payload?: string },
    expectedVersion: number
  ): Promise<UpdateResult> {
    const now = new Date().toISOString();

    const result = await this.db
      .prepare(
        `UPDATE resources
         SET name       = COALESCE(?, name),
             payload    = COALESCE(?, payload),
             version    = version + 1,
             updated_at = ?
         WHERE id = ? AND version = ?`
      )
      .bind(
        patch.name    ?? null,
        patch.payload ?? null,
        now,
        id,
        expectedVersion
      )
      .run();

    if (result.meta.changes > 0) {
      // Success path — re-read so caller gets the new version number.
      const updated = await this.get(id);
      return { type: 'ok', resource: updated! };
    }

    // Zero changes: distinguish 404 from 409.
    const current = await this.get(id);
    if (!current) return { type: 'not_found' };
    return { type: 'conflict', currentVersion: current.version };
  }

  async create(name: string, payload: string): Promise<Resource> {
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    await this.db
      .prepare(
        `INSERT INTO resources (id, name, payload, version, updated_at)
         VALUES (?, ?, ?, 1, ?)`
      )
      .bind(id, name, payload, now)
      .run();

    return { id, name, payload, version: 1, updated_at: now };
  }
}

// src/worker.ts
import { ResourceRepository } from './repository';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const repo = new ResourceRepository(env.DB);

    // GET /resources/:id
    const getMatch = url.pathname.match(/^\/resources\/([\w-]+)$/);
    if (getMatch && request.method === 'GET') {
      const resource = await repo.get(getMatch[1]);
      if (!resource) return new Response('Not Found', { status: 404 });
      return Response.json(resource, {
        headers: { ETag: `"${resource.version}"` },
      });
    }

    // PATCH /resources/:id  —  requires If-Match: "<version>"
    const patchMatch = url.pathname.match(/^\/resources\/([\w-]+)$/);
    if (patchMatch && request.method === 'PATCH') {
      const id = patchMatch[1];

      // Client sends the version it read as an HTTP ETag / If-Match header.
      const ifMatch = request.headers.get('If-Match');
      if (!ifMatch) {
        return Response.json(
          { error: 'If-Match header required' },
          { status: 428 }
        );
      }
      const expectedVersion = parseInt(ifMatch.replace(/"/g, ''), 10);
      if (isNaN(expectedVersion)) {
        return Response.json({ error: 'Invalid If-Match value' }, { status: 400 });
      }

      const patch = await request.json<{ name?: string; payload?: string }>();
      const result = await repo.update(id, patch, expectedVersion);

      switch (result.type) {
        case 'ok':
          return Response.json(result.resource, {
            status: 200,
            headers: { ETag: `"${result.resource.version}"` },
          });
        case 'conflict':
          return Response.json(
            {
              error: 'Conflict: resource was modified by another request',
              currentVersion: result.currentVersion,
            },
            { status: 409 }
          );
        case 'not_found':
          return new Response('Not Found', { status: 404 });
      }
    }

    return new Response('Not Found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;

// src/retry-client.ts
/**
 * Client-side helper: automatically re-read and retry on 409.
 * Retries up to `maxRetries` times with optional exponential backoff.
 */
export async function updateWithRetry(
  baseUrl: string,
  id: string,
  buildPatch: (current: Resource) => Partial<Resource>,
  maxRetries = 3
): Promise<Resource> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    // 1. Read current state.
    const getRes = await fetch(`${baseUrl}/resources/${id}`);
    if (!getRes.ok) throw new Error(`GET failed: ${getRes.status}`);
    const current: Resource = await getRes.json();

    // 2. Attempt the update.
    const patchRes = await fetch(`${baseUrl}/resources/${id}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'If-Match': `"${current.version}"`,
      },
      body: JSON.stringify(buildPatch(current)),
    });

    if (patchRes.ok) return patchRes.json();
    if (patchRes.status !== 409) throw new Error(`PATCH failed: ${patchRes.status}`);

    // 409 — wait with backoff, then retry.
    if (attempt < maxRetries) {
      await new Promise(r => setTimeout(r, 50 * 2 ** attempt + Math.random() * 50));
    }
  }
  throw new Error(`Optimistic lock conflict after ${maxRetries} retries`);
}
```

---

## Implementation Details

**Schema:**
```sql
CREATE TABLE resources (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  payload    TEXT NOT NULL DEFAULT '{}',
  version    INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**`meta.changes` is the key signal.** D1's `D1Result.meta.changes` is the SQLite `changes()` value — the number of rows affected by the most recent `INSERT`, `UPDATE`, or `DELETE`. A value of `0` after an `UPDATE ... WHERE id=? AND version=?` definitively means the predicate did not match.

**ETag convention:** Map `version` (integer) to the HTTP `ETag` response header and read it back via `If-Match` on write. This aligns with RFC 7232 conditional request semantics and lets standard HTTP caches participate in validation.

**Version 0 sentinel:** If you want to support "create-if-not-exists" semantics, use `version = 0` as the expected version for inserts and handle the conflict case with an `INSERT OR IGNORE`.

---

## Anti-patterns

```typescript
// BAD: reading version then updating in two round-trips without WHERE version=?
// The version check must be inside the UPDATE statement itself.
const row = await repo.get(id);
if (row.version !== expectedVersion) return new Response('Conflict', { status: 409 });
await db.prepare('UPDATE resources SET name=? WHERE id=?').bind(name, id).run();
// ^ Race condition: another update can land between the two statements.

// BAD: using a timestamp instead of a monotonic integer as the version
// Two writes within the same millisecond have equal timestamps — no conflict detected.
```

---

## Gotchas

- **Do not return `changes` from a batch.** `db.batch()` returns an array of `D1Result`, but the `meta.changes` of individual statements inside a batch may not reflect partial conflicts. Run the optimistic update as a single `.run()` call outside a batch for reliable `meta.changes` semantics.
- **The follow-up GET after zero changes costs one extra read.** In high-conflict scenarios you can skip it and always return `409`; clients that want the current version will read it themselves. Profile before optimizing.
- **`version` overflow:** SQLite INTEGER is 64-bit signed, so overflow is not a practical concern. If you use a TEXT `etag` (UUID per write), skip the `+1` arithmetic entirely.
- **Admin resets:** If you need to forcibly reset a row's version (e.g., after a migration), do it in a migration script that also resets `version = 1` consistently.

---

## Verification

```typescript
// test/optimistic-lock.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { ResourceRepository } from '../src/repository';

describe('Optimistic locking', () => {
  let repo: ResourceRepository;

  beforeEach(async () => {
    const db = getMiniflareD1('DB');
    await db.exec(SCHEMA_SQL);
    repo = new ResourceRepository(db);
  });

  it('returns ok when version matches', async () => {
    const created = await repo.create('item', '{}');
    const result = await repo.update(created.id, { name: 'updated' }, 1);
    expect(result.type).toBe('ok');
    if (result.type === 'ok') expect(result.resource.version).toBe(2);
  });

  it('returns conflict when version is stale', async () => {
    const created = await repo.create('item', '{}');
    // First update succeeds, bumps to version 2.
    await repo.update(created.id, { name: 'first' }, 1);
    // Second update with stale version 1 should conflict.
    const result = await repo.update(created.id, { name: 'second' }, 1);
    expect(result.type).toBe('conflict');
    if (result.type === 'conflict') expect(result.currentVersion).toBe(2);
  });

  it('returns not_found for missing id', async () => {
    const result = await repo.update('does-not-exist', { name: 'x' }, 1);
    expect(result.type).toBe('not_found');
  });
});
```

---

## Related

- `workers-d1-batch-writes.md` — batching non-conflicting writes efficiently
- `workers-d1-row-level-security.md` — combine user_id scoping with version checks in the same WHERE clause
- `workers-d1-schema-versioning.md` — schema migrations that reset version columns

---

## Sources

- D1 `meta.changes` documentation: https://developers.cloudflare.com/d1/worker-api/return-object/
- RFC 7232 — HTTP Conditional Requests: https://datatracker.ietf.org/doc/html/rfc7232
- Martin Fowler — Optimistic Offline Lock: https://martinfowler.com/eaaCatalog/optimisticOfflineLock.html
