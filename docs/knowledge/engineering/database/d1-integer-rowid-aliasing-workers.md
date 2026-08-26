# D1 INTEGER PRIMARY KEY as Rowid Alias: Performance and Design

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A D1 table has a UUID `TEXT PRIMARY KEY` and lookups by primary key are measurably slower
than expected. Adding an `INTEGER` surrogate key dramatically speeds up point reads and
range scans. You need to understand *why* this happens and how to design schemas that exploit
SQLite's rowid architecture for maximum D1 performance.

## Context

Every SQLite table (and therefore every D1 table) that is not declared `WITHOUT ROWID` has
an implicit 64-bit integer row identifier called the **rowid**. The B-tree that stores the
table's data is physically ordered by rowid — it is the clustering key.

When you declare a column as `INTEGER PRIMARY KEY`, SQLite does not create a separate index
for that column. Instead it **aliases the column to the rowid itself**. Lookups by that
column walk the main B-tree directly — the fastest possible access path.

When you declare any other type as `PRIMARY KEY` (including `TEXT`, `UUID`, `BLOB`, or a
composite key), SQLite:
1. Creates the main B-tree ordered by rowid (an auto-assigned opaque integer).
2. Creates a **separate B-tree index** on the declared primary key column(s).
3. Every primary-key lookup first searches the PK index (one B-tree traversal), retrieves the
   rowid, then searches the main B-tree (a second traversal).

This double-traversal makes TEXT primary key lookups roughly 2× more expensive than INTEGER
PRIMARY KEY lookups, especially as the table grows.

## The Rowid Alias Rule

```sql
-- These all create a rowid alias — one B-tree, one traversal:
CREATE TABLE a (id INTEGER PRIMARY KEY);          -- classic rowid alias
CREATE TABLE b (id INTEGER PRIMARY KEY ASC);      -- explicitly ascending, same thing
CREATE TABLE c (id INT PRIMARY KEY);              -- "INT" contains "INT" → affinity INTEGER → alias

-- These do NOT create a rowid alias — two B-trees, two traversals:
CREATE TABLE d (id TEXT PRIMARY KEY);             -- TEXT affinity → separate index
CREATE TABLE e (id BLOB PRIMARY KEY);             -- BLOB affinity → separate index
CREATE TABLE f (id BIGINT PRIMARY KEY);           -- "BIGINT" → INTEGER affinity BUT
                                                  -- type name != "INTEGER" or "INT" exactly
                                                  -- → separate index (not an alias)

-- Composite PKs never alias the rowid:
CREATE TABLE g (tenant_id INTEGER, id INTEGER, PRIMARY KEY (tenant_id, id));
```

The exact rule: a column is a rowid alias if and only if its declared type is exactly
`INTEGER` (case-insensitive) and it is the sole primary key column.

## Performance Demonstration

```typescript
// workers/rowid-demo.ts — illustrate lookup cost difference

export default {
  async fetch(_req: Request, env: Env): Promise<Response> {
    // Setup (run once, not in request path)
    await env.DB.exec(`
      CREATE TABLE IF NOT EXISTS int_pk  (id INTEGER PRIMARY KEY, data TEXT);
      CREATE TABLE IF NOT EXISTS text_pk (id TEXT    PRIMARY KEY, data TEXT);
    `);

    // Populate with 10k rows if empty
    const count = await env.DB.prepare("SELECT COUNT(*) AS n FROM int_pk").first<{ n: number }>();
    if (!count || count.n === 0) {
      const batch: D1PreparedStatement[] = [];
      for (let i = 1; i <= 10_000; i++) {
        batch.push(
          env.DB.prepare("INSERT INTO int_pk  VALUES (?, ?)").bind(i, `data-${i}`),
          env.DB.prepare("INSERT INTO text_pk VALUES (?, ?)").bind(`uuid-${i.toString().padStart(6,"0")}`, `data-${i}`)
        );
        if (batch.length >= 100) {
          await env.DB.batch(batch.splice(0));
        }
      }
      if (batch.length) await env.DB.batch(batch);
    }

    // Benchmark: 100 random point lookups each
    const ids = Array.from({ length: 100 }, () => Math.floor(Math.random() * 10_000) + 1);

    const t1 = Date.now();
    for (const id of ids) {
      await env.DB.prepare("SELECT data FROM int_pk WHERE id = ?").bind(id).first();
    }
    const intTime = Date.now() - t1;

    const t2 = Date.now();
    for (const id of ids) {
      const textId = `uuid-${id.toString().padStart(6, "0")}`;
      await env.DB.prepare("SELECT data FROM text_pk WHERE id = ?").bind(textId).first();
    }
    const textTime = Date.now() - t2;

    return Response.json({
      int_pk_100_lookups_ms: intTime,
      text_pk_100_lookups_ms: textTime,
      overhead_pct: (((textTime - intTime) / intTime) * 100).toFixed(1) + "%",
    });
  },
};
```

## Surrogate INTEGER Key + UUID Public Identifier Pattern

For APIs that expose identifiers externally, you typically want UUIDs for security (no
enumeration) while still benefiting from rowid performance internally. Use a surrogate
integer as the physical key and a UUID as the public API identifier.

```sql
-- migration: 0001_surrogate_key.sql
CREATE TABLE IF NOT EXISTS articles (
  -- Physical primary key: rowid alias, single B-tree
  id          INTEGER PRIMARY KEY,

  -- Public-facing identifier: separate unique index (one extra B-tree traversal on lookup)
  public_id   TEXT NOT NULL UNIQUE,

  title       TEXT NOT NULL,
  body        TEXT NOT NULL,
  author_id   INTEGER NOT NULL REFERENCES users(id),
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_articles_author ON articles (author_id, created_at DESC);
```

```typescript
// lib/articles.ts
import type { Env } from "./env";

export interface Article {
  id: number;        // internal — never expose in API responses
  publicId: string;  // expose this as "id" in API responses
  title: string;
  body: string;
  authorId: number;
  createdAt: number;
}

export async function createArticle(
  db: D1Database,
  input: { title: string; body: string; authorId: number }
): Promise<string> {
  const publicId = crypto.randomUUID();

  const result = await db
    .prepare(
      `INSERT INTO articles (public_id, title, body, author_id)
       VALUES (?, ?, ?, ?)
       RETURNING id, public_id`
    )
    .bind(publicId, input.title, input.body, input.authorId)
    .first<{ id: number; public_id: string }>();

  if (!result) throw new Error("insert failed");
  return result.public_id;
}

export async function getArticleByPublicId(
  db: D1Database,
  publicId: string
): Promise<Article | null> {
  // One index traversal (public_id → rowid) + one B-tree lookup (rowid → row)
  const row = await db
    .prepare(
      `SELECT id, public_id, title, body, author_id, created_at
       FROM articles WHERE public_id = ?`
    )
    .bind(publicId)
    .first<{
      id: number; public_id: string; title: string; body: string;
      author_id: number; created_at: number;
    }>();

  if (!row) return null;
  return {
    id: row.id,
    publicId: row.public_id,
    title: row.title,
    body: row.body,
    authorId: row.author_id,
    createdAt: row.created_at,
  };
}

export async function getArticlesByAuthor(
  db: D1Database,
  authorId: number,
  limit = 20,
  afterRowid?: number
): Promise<Article[]> {
  // Use the internal integer id for efficient keyset pagination — never expose in API
  const sql = afterRowid
    ? `SELECT id, public_id, title, body, author_id, created_at
       FROM articles
       WHERE author_id = ? AND id < ?
       ORDER BY id DESC LIMIT ?`
    : `SELECT id, public_id, title, body, author_id, created_at
       FROM articles
       WHERE author_id = ?
       ORDER BY id DESC LIMIT ?`;

  const stmt = afterRowid
    ? db.prepare(sql).bind(authorId, afterRowid, limit)
    : db.prepare(sql).bind(authorId, limit);

  const result = await stmt.all<{
    id: number; public_id: string; title: string; body: string;
    author_id: number; created_at: number;
  }>();

  return result.results.map((row) => ({
    id: row.id,
    publicId: row.public_id,
    title: row.title,
    body: row.body,
    authorId: row.author_id,
    createdAt: row.created_at,
  }));
}
```

## Using `last_insert_rowid()` to Retrieve the New Row's ID

```typescript
// Alternative to RETURNING when you need the auto-assigned rowid
async function insertAndGetRowid(db: D1Database, title: string): Promise<number> {
  const result = await db
    .prepare("INSERT INTO articles (public_id, title, body, author_id) VALUES (?, ?, '', 1)")
    .bind(crypto.randomUUID(), title)
    .run();

  // D1's run() result includes meta.last_row_id
  if (!result.success) throw new Error("insert failed");
  return result.meta.last_row_id;
}
```

## Autoincrement vs. Rowid Alias

`INTEGER PRIMARY KEY` and `INTEGER PRIMARY KEY AUTOINCREMENT` are subtly different:

| Feature | `INTEGER PRIMARY KEY` | `INTEGER PRIMARY KEY AUTOINCREMENT` |
|---|---|---|
| Rowid alias | Yes | Yes |
| Reuse of deleted rowids | Yes (picks max + 1 or fills gaps) | No (monotonically increasing, never reuses) |
| Extra B-tree (`sqlite_sequence`) | No | Yes (slight write overhead) |
| Max rowid collision risk | Theoretical (2^63 rows) | Error on overflow |

```sql
-- Use plain INTEGER PRIMARY KEY for most cases:
CREATE TABLE events (id INTEGER PRIMARY KEY, data TEXT);

-- Use AUTOINCREMENT only if you must guarantee monotonically increasing IDs
-- that never repeat (e.g., distributed audit logs where gap-filling would
-- create ambiguity after deletions):
CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT);
```

`AUTOINCREMENT` adds a write to the `sqlite_sequence` table on every insert. For
high-throughput insert workloads, avoid it unless the monotonicity guarantee is required.

## Anti-patterns

**Using `BIGINT PRIMARY KEY` expecting a rowid alias.** SQLite checks the *exact* type name
`INTEGER` (or `INT`). `BIGINT`, `INT8`, `INT64`, `TINYINT` — all have INTEGER affinity but
are NOT rowid aliases. They produce a separate index and a double-traversal.

**Exposing the internal integer ID in API responses.** Integer IDs are enumerable. An
attacker can iterate `?id=1`, `?id=2`, etc. Always map to a UUID public ID at the API layer.

**Relying on rowid ordering for globally unique event ordering.** Rowids are locally
auto-assigned per D1 database replica; they are not globally monotone across distributed
systems or after failover. Use `unixepoch()` or a UUIDv7 for time-ordered identifiers.

**Storing foreign keys as TEXT UUID.** If the parent table uses a surrogate INTEGER PK, the
child table's foreign key should also be INTEGER. A TEXT FK forces an unnecessary type
coercion on every JOIN and prevents the FK from participating in the rowid fast-path.

## Gotchas

- **`INTEGER PRIMARY KEY DESC` breaks the rowid alias.** A descending PK (`... ASC` is fine;
  `... DESC` is not) creates a separate index. Never add `DESC` to a rowid alias declaration.

- **`WITHOUT ROWID` tables have no rowid.** If you declare `WITHOUT ROWID`, the PRIMARY KEY
  becomes the clustering key directly. The rowid alias concept does not apply. See
  `d1-without-rowid-table-design.md` for when this is beneficial.

- **`RETURNING id` is the cleanest way to get the new rowid.** The `last_insert_rowid()`
  SQLite function is only valid in the same connection/session. In D1, use `RETURNING id`
  in the INSERT statement to avoid any ambiguity.

- **Rowids are signed 64-bit.** They range from −2^63 to 2^63−1. In practice you will
  exhaust storage long before exhausting rowids, but avoid using them as timestamps or
  sequence numbers in protocols that expect only positive values.

## Verification

```typescript
// Verify that INTEGER PK is aliasing rowid, not creating a separate index
async function verifyRowidAlias(db: D1Database): Promise<void> {
  await db.exec("CREATE TEMP TABLE IF NOT EXISTS rowid_test (id INTEGER PRIMARY KEY, v TEXT)");
  await db.prepare("INSERT INTO rowid_test VALUES (42, 'hello')").run();

  // rowid and id should return the same value
  const row = await db
    .prepare("SELECT id, rowid FROM rowid_test WHERE id = 42")
    .first<{ id: number; rowid: number }>();

  console.assert(row !== null, "row must exist");
  console.assert(row?.id === row?.rowid, `id (${row?.id}) must equal rowid (${row?.rowid})`);
  console.log("rowid alias verification: OK", row);

  // Query plan should show "SEARCH rowid_test USING INTEGER PRIMARY KEY" (not USING INDEX)
  const plan = await db
    .prepare("EXPLAIN QUERY PLAN SELECT * FROM rowid_test WHERE id = 42")
    .all<{ detail: string }>();

  const planText = plan.results.map((r) => r.detail).join("\n");
  console.assert(
    planText.includes("INTEGER PRIMARY KEY"),
    `Expected INTEGER PRIMARY KEY in plan, got:\n${planText}`
  );
  console.log("query plan:", planText);
}
```

## Related

- `d1-without-rowid-table-design.md` — when to opt out of the rowid B-tree entirely
- `d1-covering-index-composite-key-workers.md` — index design on top of rowid tables
- `d1-column-affinity-type-coercion-workers.md` — type affinity rules that govern rowid aliasing
- `d1-pagination-cursor-keyset.md` — using integer rowid for efficient cursor pagination
- `composite-keys.md` — composite primary key trade-offs

## Sources

- SQLite rowid tables documentation: https://sqlite.org/rowidtable.html
- SQLite INTEGER PRIMARY KEY specification: https://sqlite.org/lang_createtable.html#rowid
- SQLite AUTOINCREMENT keyword: https://sqlite.org/autoinc.html
- Cloudflare D1 schema design guide: https://developers.cloudflare.com/d1/reference/database-sizing/
