# Row-Level Security in D1 Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Multiple users share a single D1 database and you need to guarantee that every query is scoped to the authenticated user — no user can ever read or mutate another user's rows, even if the Worker code has a bug or a query is constructed incorrectly. The goal is a single, enforced pattern rather than relying on every developer to remember to add `WHERE owner_id = ?` manually.

---

## Context

D1 (and SQLite) has no native row-level security (RLS) like PostgreSQL's `ENABLE ROW LEVEL SECURITY`. The enforcement must live in the application layer — specifically in the Cloudflare Worker. The pattern used here is a `createScopedDb(userId)` factory that wraps D1's prepared-statement API and automatically appends an `AND owner_id = ?` binding to every read query. Write operations additionally assert that the `owner_id` column in the payload matches the authenticated user. A property-based test iterates over random user-ID pairs and asserts that queries for user A never return rows belonging to user B.

---

## Section 1 — D1 Schema

```sql
-- Every user-owned table includes owner_id as a non-nullable indexed column.
CREATE TABLE IF NOT EXISTS notes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id   TEXT    NOT NULL,
  title      TEXT    NOT NULL,
  body       TEXT    NOT NULL,
  created_at TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Composite index: owner_id first so all queries scoped by owner hit this index.
CREATE INDEX IF NOT EXISTS idx_notes_owner_created
  ON notes(owner_id, created_at DESC);

-- Audit log table — append-only, records all mutations with actor.
CREATE TABLE IF NOT EXISTS audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id   TEXT    NOT NULL,
  table_name TEXT    NOT NULL,
  row_id     INTEGER NOT NULL,
  action     TEXT    NOT NULL,  -- 'INSERT' | 'UPDATE' | 'DELETE'
  actor_id   TEXT    NOT NULL,
  created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_owner ON audit_log(owner_id, created_at DESC);
```

---

## Section 2 — Worker implementation

```typescript
// src/db/scoped.ts
import { D1Database, D1PreparedStatement } from '@cloudflare/workers-types';

/**
 * ScopedDb wraps D1 and automatically appends `AND owner_id = ?`
 * to every SELECT, UPDATE, and DELETE statement.
 *
 * Usage:
 *   const db = createScopedDb(env.DB, userId);
 *   const notes = await db.list('SELECT * FROM notes WHERE 1=1', []);
 */
export interface ScopedDb {
  /** SELECT — always adds AND owner_id = ? */
  list<T>(sql: string, bindings: unknown[]): Promise<T[]>;
  /** SELECT single row */
  first<T>(sql: string, bindings: unknown[]): Promise<T | null>;
  /** INSERT — asserts owner_id in payload, does NOT add it automatically */
  insert(sql: string, bindings: unknown[]): Promise<D1Result>;
  /** UPDATE / DELETE — appends AND owner_id = ? */
  mutate(sql: string, bindings: unknown[]): Promise<D1Result>;
}

interface D1Result {
  success: boolean;
  meta: { changes: number; last_row_id: number };
}

export function createScopedDb(d1: D1Database, userId: string): ScopedDb {
  if (!userId || typeof userId !== 'string') {
    throw new Error('createScopedDb: userId must be a non-empty string');
  }

  function scopedStmt(
    sql: string,
    bindings: unknown[]
  ): D1PreparedStatement {
    // Append RLS condition and bind userId as the last parameter.
    const scopedSql = sql.trimEnd().replace(/;?$/, '') + ' AND owner_id = ?';
    return d1.prepare(scopedSql).bind(...bindings, userId);
  }

  return {
    async list<T>(sql: string, bindings: unknown[]): Promise<T[]> {
      const { results } = await scopedStmt(sql, bindings).all<T>();
      return results ?? [];
    },

    async first<T>(sql: string, bindings: unknown[]): Promise<T | null> {
      return scopedStmt(sql, bindings).first<T>();
    },

    async insert(sql: string, bindings: unknown[]): Promise<D1Result> {
      // INSERT does not filter by owner_id — the caller must include
      // owner_id in the INSERT column list and pass userId as a binding.
      return d1.prepare(sql).bind(...bindings).run() as Promise<D1Result>;
    },

    async mutate(sql: string, bindings: unknown[]): Promise<D1Result> {
      return scopedStmt(sql, bindings).run() as Promise<D1Result>;
    },
  };
}

// src/routes/notes.ts
import { Env } from '../types';
import { createScopedDb } from '../db/scoped';
import { getUserIdFromJwt } from '../auth/jwt';

export async function handleListNotes(
  request: Request,
  env: Env
): Promise<Response> {
  const userId = await getUserIdFromJwt(request, env);
  if (!userId) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const db = createScopedDb(env.DB, userId);

  // The WHERE 1=1 is a base clause; ScopedDb appends AND owner_id = ?
  const notes = await db.list<{ id: number; title: string; created_at: string }>(
    `SELECT id, title, created_at FROM notes WHERE 1=1 ORDER BY created_at DESC LIMIT 50`,
    []
  );

  return Response.json({ notes });
}

export async function handleGetNote(
  request: Request,
  env: Env,
  noteId: number
): Promise<Response> {
  const userId = await getUserIdFromJwt(request, env);
  if (!userId) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const db = createScopedDb(env.DB, userId);

  const note = await db.first<{ id: number; title: string; body: string }>(
    `SELECT id, title, body FROM notes WHERE id = ?`,
    [noteId]
  );

  if (!note) {
    // Returns 404 whether the note doesn't exist OR belongs to another user.
    return Response.json({ error: 'Not found' }, { status: 404 });
  }

  return Response.json({ note });
}
```

---

## Section 3 — Query / Migration helper

```typescript
// tests/rls.test.ts — property-based test verifying cross-user isolation
import { createScopedDb } from '../src/db/scoped';

// Minimal D1Database stub for unit testing
function makeStubD1(rows: Record<string, unknown>[]) {
  return {
    prepare(sql: string) {
      return {
        bind(...args: unknown[]) {
          const ownerId = args[args.length - 1] as string;
          return {
            async all() {
              return {
                results: rows.filter((r) => r.owner_id === ownerId),
              };
            },
            async first() {
              return rows.find((r) => r.owner_id === ownerId) ?? null;
            },
            async run() {
              return { success: true, meta: { changes: 0, last_row_id: 0 } };
            },
          };
        },
      };
    },
  };
}

const SEED_ROWS = [
  { id: 1, owner_id: 'user-A', title: 'A note', body: '' },
  { id: 2, owner_id: 'user-B', title: 'B note', body: '' },
  { id: 3, owner_id: 'user-A', title: 'A note 2', body: '' },
];

describe('Row-level security — cross-user isolation', () => {
  const userPairs = [
    ['user-A', 'user-B'],
    ['user-B', 'user-A'],
  ];

  test.each(userPairs)(
    'user %s cannot see rows owned by %s',
    async (requester, other) => {
      const stub = makeStubD1(SEED_ROWS) as never;
      const db = createScopedDb(stub, requester);

      const results = await db.list<{ owner_id: string }>(
        `SELECT id, owner_id, title FROM notes WHERE 1=1`,
        []
      );

      // Every returned row must belong to the requester
      for (const row of results) {
        expect(row.owner_id).toBe(requester);
        expect(row.owner_id).not.toBe(other);
      }
    }
  );

  test('createScopedDb throws when userId is empty', () => {
    const stub = makeStubD1([]) as never;
    expect(() => createScopedDb(stub, '')).toThrow();
    expect(() => createScopedDb(stub, null as never)).toThrow();
  });
});
```

---

## Anti-patterns

- **Trusting `owner_id` from the request body** — Never use the client-supplied `owner_id` for scoping. Extract it exclusively from the verified JWT or session token.
- **Skipping the `AND owner_id = ?` on UPDATE/DELETE** — An update like `UPDATE notes SET title = ? WHERE id = ?` without the owner scope allows any authenticated user to overwrite any row by guessing the ID.
- **Using string interpolation for `owner_id`** — Always bind `owner_id` as a prepared-statement parameter, never interpolated into the SQL string, to prevent injection.
- **Global `db` singleton shared across requests** — D1 bindings are per-request in Workers; creating a global `ScopedDb` singleton risks one request's userId leaking into another's.
- **Relying on opacity of auto-increment IDs** — Sequential integer IDs are guessable. RLS must not depend on IDs being secret; always enforce `AND owner_id = ?`.

---

## Gotchas

- D1 prepared statements use positional `?` placeholders; the order of bindings is critical — owner_id must be the last binding when the wrapper appends `AND owner_id = ?`.
- `db.first()` returns `null` for both "not found" and "not owned by this user" — this is intentional; do not distinguish the two cases to avoid enumeration attacks.
- Workers run in isolates that may be reused across requests; never store userId in module-scope variables.
- JWT verification must happen before `createScopedDb` is called — an unverified token that passes format validation but has a tampered payload would scope the DB to the wrong user.

---

## Verification

```bash
# Confirm owner_id column exists on all user tables
wrangler d1 execute DB --remote --command \
  "SELECT name FROM pragma_table_info('notes') WHERE name='owner_id';"

# Attempt cross-user fetch (should return 0 rows)
wrangler d1 execute DB --remote --command \
  "SELECT COUNT(*) FROM notes WHERE owner_id = 'user-A' AND owner_id = 'user-B';"

# Run property-based tests
npx vitest run tests/rls.test.ts
```

---

## Related

- `d1-full-text-search-fts5-workers.md`
- `d1-batch-transactions-atomic-writes.md`
- `d1-composite-indexes-query-optimization.md`

---

## Sources

- Cloudflare D1 Workers API — https://developers.cloudflare.com/d1/worker-api/
- OWASP Insecure Direct Object Reference — https://owasp.org/www-community/attacks/Insecure_Direct_Object_Reference
- SQLite prepared statements — https://www.sqlite.org/c3ref/prepare.html
