# D1 WITHOUT ROWID Table Design and Performance

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You have lookup tables, many-to-many junction tables, or small configuration tables in D1 where the primary key is a composite or a short text/integer that already uniquely identifies every row. Each table carries the hidden `rowid` column by default, adding overhead from a second B-tree. You want tighter storage and faster full-PK lookups without the rowid bookkeeping cost.

---

## Context

SQLite (and therefore D1) stores every ordinary table as a B-tree keyed on `rowid`. When you declare an `INTEGER PRIMARY KEY`, that column becomes an alias for `rowid` — one B-tree, fast. For every other primary-key type, SQLite maintains two B-trees: the rowid B-tree (the data store) plus a secondary index B-tree for your declared PK. `WITHOUT ROWID` collapses these into a single clustered B-tree keyed directly on the declared PK, eliminating the indirection and shrinking on-disk size. D1 supports the `WITHOUT ROWID` clause fully.

Best candidates:
- Junction / association tables (`user_id + role_id`, `post_id + tag_id`)
- Small reference/enum tables with short string PKs
- Tables with composite PKs where every non-PK column is narrow
- Tables that are read-mostly via exact PK lookups

Poor candidates:
- Tables with wide non-PK columns (the full row is stored in the PK B-tree leaf — large rows increase internal-node fan-out cost)
- Tables where you need `last_insert_rowid()` or auto-increment behaviour
- Tables that are frequently accessed via range scans on non-PK columns

---

## Declaring a WITHOUT ROWID Table

```sql
-- Migration: 0012_create_user_roles.sql
CREATE TABLE user_roles (
  user_id  TEXT    NOT NULL,
  role_id  TEXT    NOT NULL,
  granted_at INTEGER NOT NULL DEFAULT (unixepoch()),
  PRIMARY KEY (user_id, role_id)
) WITHOUT ROWID;
```

```typescript
// src/db/migrate.ts
import type { D1Database } from '@cloudflare/workers-types';

export async function applyMigration(db: D1Database): Promise<void> {
  await db.exec(`
    CREATE TABLE IF NOT EXISTS user_roles (
      user_id     TEXT    NOT NULL,
      role_id     TEXT    NOT NULL,
      granted_at  INTEGER NOT NULL DEFAULT (unixepoch()),
      PRIMARY KEY (user_id, role_id)
    ) WITHOUT ROWID;
  `);
}
```

---

## PK Lookup Performance

Because the full row lives in the PK B-tree, an exact PK lookup retrieves data in one traversal instead of two (rowid lookup → secondary index lookup → rowid lookup for data).

```typescript
// src/handlers/roles.ts
export async function getUserRoles(
  db: D1Database,
  userId: string
): Promise<string[]> {
  // Range scan on leading PK column — still efficient with WITHOUT ROWID
  const { results } = await db
    .prepare('SELECT role_id FROM user_roles WHERE user_id = ?')
    .bind(userId)
    .all<{ role_id: string }>();

  return results.map((r) => r.role_id);
}

export async function hasRole(
  db: D1Database,
  userId: string,
  roleId: string
): Promise<boolean> {
  // Full PK point lookup — single B-tree traversal
  const row = await db
    .prepare(
      'SELECT 1 FROM user_roles WHERE user_id = ? AND role_id = ? LIMIT 1'
    )
    .bind(userId, roleId)
    .first<{ 1: number }>();

  return row !== null;
}
```

---

## Junction Table Pattern

```sql
-- Many-to-many: posts ↔ tags
CREATE TABLE post_tags (
  post_id  INTEGER NOT NULL,
  tag_id   INTEGER NOT NULL,
  PRIMARY KEY (post_id, tag_id)
) WITHOUT ROWID;

CREATE INDEX idx_post_tags_tag ON post_tags (tag_id, post_id);
```

```typescript
// src/handlers/tags.ts
export async function addTagToPost(
  db: D1Database,
  postId: number,
  tagId: number
): Promise<void> {
  await db
    .prepare(
      'INSERT OR IGNORE INTO post_tags (post_id, tag_id) VALUES (?, ?)'
    )
    .bind(postId, tagId)
    .run();
}

export async function getPostsByTag(
  db: D1Database,
  tagId: number
): Promise<number[]> {
  // Uses the secondary index on (tag_id, post_id)
  const { results } = await db
    .prepare('SELECT post_id FROM post_tags WHERE tag_id = ?')
    .bind(tagId)
    .all<{ post_id: number }>();

  return results.map((r) => r.post_id);
}
```

---

## Reference / Enum Table Pattern

```sql
CREATE TABLE currencies (
  code        TEXT    NOT NULL,  -- 'USD', 'EUR', …
  symbol      TEXT    NOT NULL,
  decimal_places INTEGER NOT NULL DEFAULT 2,
  PRIMARY KEY (code)
) WITHOUT ROWID;
```

```typescript
// src/db/seed.ts
export async function seedCurrencies(db: D1Database): Promise<void> {
  const batch = [
    ['USD', '$', 2],
    ['EUR', '€', 2],
    ['JPY', '¥', 0],
    ['BTC', '₿', 8],
  ].map(([code, symbol, dp]) =>
    db
      .prepare(
        'INSERT OR IGNORE INTO currencies (code, symbol, decimal_places) VALUES (?, ?, ?)'
      )
      .bind(code, symbol, dp)
  );

  await db.batch(batch);
}
```

---

## Checking Table Type at Runtime

```typescript
export async function isWithoutRowid(
  db: D1Database,
  tableName: string
): Promise<boolean> {
  // sqlite_master stores the original DDL
  const row = await db
    .prepare(
      "SELECT sql FROM sqlite_master WHERE type='table' AND name=?"
    )
    .bind(tableName)
    .first<{ sql: string }>();

  return (row?.sql ?? '').toUpperCase().includes('WITHOUT ROWID');
}
```

---

## Anti-patterns

- **Using `INTEGER PRIMARY KEY` with `WITHOUT ROWID`** — SQLite rejects this. `INTEGER PRIMARY KEY` is a rowid alias, which is incompatible. Use `INTEGER NOT NULL PRIMARY KEY` with an explicit type that is not the SQLite `INTEGER` affinity alias. In practice, composite PKs or `TEXT` PKs are the natural fit.
- **Wide non-PK columns** — Every full-row copy is stored in the PK B-tree leaf. Tables with `TEXT` blobs or large JSON columns become unwieldy; prefer normal tables with covering indexes instead.
- **Relying on `last_insert_rowid()`** — `WITHOUT ROWID` tables have no rowid, so this always returns `0`. Use `RETURNING id` or track the PK value in application code.
- **`AUTOINCREMENT`** — Not allowed on `WITHOUT ROWID` tables. Auto-increment semantics require the hidden `sqlite_sequence` table which depends on rowid.
- **`WITHOUT ROWID` on frequently-scanned large tables** — Full-table scans on a `WITHOUT ROWID` table read the entire PK B-tree including all column data; a normal table only reads the rowid B-tree (smaller) and fetches column pages on demand.

---

## Gotchas

- `WITHOUT ROWID` tables cannot be the target of `REFERENCES` constraints that omit a column list — always specify the referenced column(s) explicitly.
- D1's REST API does not expose `rowid` columns by default; this is usually not an issue, but confirm behaviour when migrating existing code that relied on implicit rowid access.
- `WITHOUT ROWID` tables support secondary indexes normally; secondary index entries contain the full PK value (not a rowid pointer), so composite PKs increase secondary index size.
- You cannot convert an existing table to or from `WITHOUT ROWID` without recreating it.
- `PRAGMA table_info` does not show `WITHOUT ROWID`; inspect `sqlite_master.sql` to confirm.

---

## Verification

```typescript
// Confirm query plan uses PK B-tree directly (no "SEARCH … USING INDEX")
export async function explainJunctionLookup(db: D1Database): Promise<void> {
  const rows = await db
    .prepare(
      'EXPLAIN QUERY PLAN SELECT role_id FROM user_roles WHERE user_id = ?'
    )
    .bind('usr_abc123')
    .all<{ detail: string }>();

  // Expected: "SEARCH user_roles USING PRIMARY KEY (user_id=?)"
  console.log(rows.results.map((r) => r.detail).join('\n'));
}
```

```typescript
// Measure storage savings — compare page count before/after migration
export async function tablePageCount(
  db: D1Database,
  tableName: string
): Promise<number> {
  const row = await db
    .prepare("SELECT pageno FROM dbstat WHERE name = ? ORDER BY pageno DESC LIMIT 1")
    .bind(tableName)
    .first<{ pageno: number }>();
  return row?.pageno ?? 0;
}
```

---

## Related

- `d1-batch-operations-performance.md`
- `composite-index-design.md`
- `covering-indexes.md`
- `d1-foreign-keys-referential-integrity.md`
- `d1-migrations-wrangler-ci-cd.md`

---

## Sources

- https://www.sqlite.org/withoutrowid.html
- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/rowidtable.html
- https://www.sqlite.org/fileformat2.html#b_tree_pages
