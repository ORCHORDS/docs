# D1 Column Defaults and Autoincrement Patterns in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A Workers application inserts rows without supplying every column value, and the defaults either don't fire, produce NULL, or the primary-key strategy causes unexpected gaps or reuse of deleted IDs. You need reliable, predictable column defaults and a clear choice between `ROWID`, `AUTOINCREMENT`, and application-generated keys.

## Context
D1 is SQLite under the hood. SQLite's `DEFAULT` clause, `AUTOINCREMENT` keyword, and rowid aliasing all behave subtly differently from PostgreSQL sequences or MySQL AUTO_INCREMENT. The D1 Workers binding wraps SQLite's standard `prepare → bind → run` pipeline; there is no server-side sequence object, and `lastInsertRowid` is exposed on the `D1Result` type to let Workers recover the generated key after an insert.

---

## DEFAULT Expressions

SQLite supports a restricted set of expressions inside `DEFAULT (...)`. The following are valid:

```sql
CREATE TABLE events (
  id         INTEGER PRIMARY KEY,               -- rowid alias; no AUTOINCREMENT
  name       TEXT    NOT NULL,
  status     TEXT    NOT NULL DEFAULT 'pending',
  created_at TEXT    NOT NULL DEFAULT (datetime('now')),  -- UTC
  updated_at TEXT    NOT NULL DEFAULT (datetime('now')),
  metadata   TEXT    NOT NULL DEFAULT '{}',              -- valid JSON seed
  sort_order REAL    NOT NULL DEFAULT (julianday('now')) -- sortable float
);
```

Expressions inside `DEFAULT (...)` must be constant or built-in scalar functions with no arguments or `'now'` as the sole argument. You **cannot** reference other columns in a `DEFAULT` expression — use a trigger for that.

```sql
-- INVALID — reference to another column:
CREATE TABLE items (
  price   REAL,
  tax     REAL DEFAULT (price * 0.08)  -- syntax error in SQLite
);

-- VALID workaround: computed via AFTER INSERT trigger or a generated column
CREATE TABLE items (
  price REAL NOT NULL,
  tax   REAL GENERATED ALWAYS AS (price * 0.08) VIRTUAL
);
```

---

## INTEGER PRIMARY KEY vs AUTOINCREMENT

These two are meaningfully different in SQLite:

| Strategy | Behaviour on delete + reinsert |
|---|---|
| `INTEGER PRIMARY KEY` | Reuses the highest existing rowid + 1; can recycle deleted IDs if the max rowid was deleted |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | Tracks the historical maximum in `sqlite_sequence`; never reuses a deleted ID |

```sql
-- Safe for most use-cases; lighter weight
CREATE TABLE sessions (
  id      INTEGER PRIMARY KEY,
  token   TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL
);

-- Use AUTOINCREMENT only when ID reuse would cause a correctness bug
-- (e.g. append-only audit logs, foreign keys that outlive the parent)
CREATE TABLE audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  action     TEXT NOT NULL,
  actor_id   INTEGER,
  recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

`AUTOINCREMENT` adds a write to the `sqlite_sequence` system table on every insert and is slightly slower. Prefer plain `INTEGER PRIMARY KEY` unless reuse of IDs is genuinely dangerous in your domain.

---

## Recovering the Generated ID in a Worker

`D1Result` exposes `lastInsertRowid` as a `number | bigint`. For tables with `INTEGER PRIMARY KEY`, this is the rowid assigned to the inserted row:

```typescript
import type { Env } from './types';

interface NewEvent {
  name: string;
  status?: string;
}

async function createEvent(db: D1Database, event: NewEvent): Promise<number> {
  const result = await db
    .prepare(
      `INSERT INTO events (name, status)
       VALUES (?, ?)
       RETURNING id, created_at`
    )
    .bind(event.name, event.status ?? 'pending')
    .first<{ id: number; created_at: string }>();

  if (!result) throw new Error('Insert did not return a row');
  return result.id;
}

// Alternative without RETURNING — use lastInsertRowid
async function createEventAlt(db: D1Database, event: NewEvent): Promise<number> {
  const result = await db
    .prepare(`INSERT INTO events (name) VALUES (?)`)
    .bind(event.name)
    .run();

  return Number(result.meta.last_row_id);
}
```

Prefer `RETURNING id` when you also need other generated columns (e.g. `created_at`). Use `last_row_id` from `meta` when you only need the key and want to avoid a second round-trip.

---

## Application-Generated Keys: UUIDs and ULID

For distributed inserts (multiple Workers, queues, Durable Objects) integer rowids from different D1 regions can collide if rows are merged. Application-generated unique keys eliminate this risk:

```typescript
// UUID v4 — built into the Workers runtime
function newUUID(): string {
  return crypto.randomUUID();
}

// ULID-style: timestamp prefix + random suffix (sortable, no dependency)
function newULID(): string {
  const ts = Date.now().toString(36).padStart(9, '0').toUpperCase();
  const rand = crypto.getRandomValues(new Uint8Array(10));
  const chars = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
  const suffix = Array.from(rand).map(b => chars[b % 32]).join('');
  return ts + suffix;
}

// Schema using TEXT primary key
// CREATE TABLE documents (
//   id         TEXT PRIMARY KEY DEFAULT '',  -- supplied by application
//   title      TEXT NOT NULL,
//   created_at TEXT NOT NULL DEFAULT (datetime('now'))
// );

async function createDocument(db: D1Database, title: string): Promise<string> {
  const id = newUUID();
  await db
    .prepare(`INSERT INTO documents (id, title) VALUES (?, ?)`)
    .bind(id, title)
    .run();
  return id;
}
```

Store UUIDs as `TEXT` in D1 (SQLite has no native UUID type). Avoid storing them as `BLOB` unless you have a measured size constraint, as the tooling ergonomics around hex encoding add overhead.

---

## Default Timestamps: UTC Discipline

D1's SQLite instance always returns `datetime('now')` in UTC. However, if you construct a timestamp in JavaScript and bind it as a parameter, you must normalize it yourself:

```typescript
// Safe: let the database generate the timestamp
await db.prepare(`INSERT INTO events (name) VALUES (?)`).bind('launch').run();
// created_at will be populated by DEFAULT (datetime('now')) in UTC

// Risky: binding a JS Date — ensure UTC
const now = new Date().toISOString(); // always UTC ISO-8601
await db
  .prepare(`INSERT INTO events (name, created_at) VALUES (?, ?)`)
  .bind('launch', now)
  .run();
// Store as '2026-08-23T14:00:00.000Z' — TEXT comparison sorts correctly
```

Mixing database-generated `datetime('now')` (which returns `'2026-08-23 14:00:00'`, no `T` or `Z`) with JavaScript `Date.toISOString()` (which returns `'2026-08-23T14:00:00.000Z'`) in the same column breaks `ORDER BY` and range scans. Pick one format and enforce it.

---

## Sentinel Defaults for Nullable Avoidance

SQLite's NULL propagates through arithmetic and comparisons in surprising ways. Use explicit non-null defaults to keep aggregation queries predictable:

```sql
CREATE TABLE product_stats (
  product_id   INTEGER PRIMARY KEY,
  view_count   INTEGER NOT NULL DEFAULT 0,
  purchase_count INTEGER NOT NULL DEFAULT 0,
  rating_sum   REAL    NOT NULL DEFAULT 0,
  rating_count INTEGER NOT NULL DEFAULT 0
  -- avoid nullable rating; compute AVG in application as rating_sum / rating_count
);
```

---

## Anti-patterns

- **Using `AUTOINCREMENT` on every table** — it adds a write to `sqlite_sequence` on every insert and is only necessary when ID recycling is a real correctness risk.
- **Mixing timestamp formats** (`datetime('now')` vs `.toISOString()`) in the same column — breaks lexicographic range queries.
- **Binding `undefined` or `null` to a column that has a `DEFAULT`** — D1's binding layer converts `null` to SQL `NULL`, which overrides the `DEFAULT` expression. Always omit the column from the `INSERT` column list if you want the default to fire.
- **Using `DEFAULT CURRENT_TIMESTAMP`** — this is equivalent to `DEFAULT (datetime('now'))` in SQLite but is not accepted by all D1 migration tooling. Prefer the explicit function form.

---

## Gotchas

- **`lastInsertRowid` and `db.batch()`** — when you batch multiple inserts, `meta.last_row_id` on the batch result reflects the rowid of the *last* statement in the batch, not each individual statement. Use `RETURNING` clauses inside batch statements if you need per-row IDs.
- **`INTEGER PRIMARY KEY AUTOINCREMENT` and `sqlite_sequence`** — the `sqlite_sequence` table is created the first time an `AUTOINCREMENT` table receives a row. Schema introspection scripts must handle its absence in empty databases.
- **Default expression evaluation time** — `DEFAULT (datetime('now'))` is evaluated at insert time, not at table creation time. This is the expected behaviour, but differs from some RDBMS where defaults can be bound to a sequence evaluated at DDL time.
- **`WITHOUT ROWID` tables and `lastInsertRowid`** — if you use `WITHOUT ROWID`, `last_row_id` in `meta` is always 0. Use `RETURNING` instead.

---

## Verification

```sql
-- Verify DEFAULT fires when column is omitted
INSERT INTO events (name) VALUES ('test-event');
SELECT id, name, status, created_at FROM events WHERE name = 'test-event';
-- status should be 'pending'; created_at should be a UTC datetime string

-- Inspect sqlite_sequence for AUTOINCREMENT tables
SELECT * FROM sqlite_sequence WHERE name = 'audit_log';

-- Confirm AUTOINCREMENT does not reuse IDs after a delete
INSERT INTO audit_log (action) VALUES ('a'), ('b'), ('c');
DELETE FROM audit_log WHERE action = 'c';
INSERT INTO audit_log (action) VALUES ('d');
SELECT id, action FROM audit_log;
-- 'd' should have id=4, not id=3
```

---

## Related

- `d1-returning-clause-upsert-workers.md`
- `d1-without-rowid-table-design.md`
- `d1-upsert-conflict-resolution-workers.md`
- `d1-generated-columns-virtual-workers.md`
- `d1-schema-introspection-sqlite-master-workers.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/autoinc.html
- https://www.sqlite.org/lang_createtable.html#the_default_clause
- https://www.sqlite.org/rowidtable.html
