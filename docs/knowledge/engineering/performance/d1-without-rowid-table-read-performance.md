# D1 WITHOUT ROWID Table Read Performance

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

Point-lookup queries on a D1 table are slower than expected even with a primary key index. The table stores wide rows with a short, non-integer primary key (UUID, slug, short hash). CPU time per request is measurably higher than comparable tables with integer primary keys. You want sub-millisecond D1 reads for hot-path Workers requests.

---

## Context

D1 runs on SQLite, and every ordinary SQLite table has a hidden 64-bit integer `rowid`. When you declare `INTEGER PRIMARY KEY`, that column becomes an alias for the rowid and the table is stored in a single B-tree keyed by the integer — one tree traversal per lookup.

For any other primary key type (TEXT, BLOB, composite), SQLite creates **two** B-trees: the table heap (keyed by rowid) and the primary key index. A point-lookup traverses the index B-tree to find the rowid, then traverses the table B-tree to fetch the row — two round-trips through the page cache.

Declaring `WITHOUT ROWID` eliminates the rowid entirely. The table is stored directly in the primary key B-tree (a "covering clustered index"). One traversal fetches the full row. For small-to-medium rows with TEXT or composite primary keys this routinely cuts read CPU time by 20–40 % and reduces page reads by roughly half.

---

## When WITHOUT ROWID Helps

`WITHOUT ROWID` pays off when:

- The primary key is TEXT, BLOB, or composite (not `INTEGER PRIMARY KEY` / `ROWID` alias).
- Rows are not excessively wide (< ~200 bytes per row is the sweet spot).
- The workload is **read-heavy point lookups or short range scans** by primary key.
- You do **not** need `sqlite_sequence` auto-increment or `last_insert_rowid()`.

It hurts when rows are very wide (e.g., storing multi-KB JSON blobs), because the entire row sits in the primary key B-tree leaf; large rows cause more page splits and cache churn than the two-tree layout.

---

## Schema Design

```sql
-- Ordinary table: two B-tree traversals per slug lookup
CREATE TABLE articles (
  slug    TEXT    NOT NULL,
  title   TEXT    NOT NULL,
  body    TEXT    NOT NULL,
  updated INTEGER NOT NULL,
  PRIMARY KEY (slug)
);

-- WITHOUT ROWID: one traversal, clustered on slug
CREATE TABLE articles (
  slug    TEXT    NOT NULL,
  title   TEXT    NOT NULL,
  body    TEXT    NOT NULL,
  updated INTEGER NOT NULL,
  PRIMARY KEY (slug)
) WITHOUT ROWID;
```

There is no syntax change for `INSERT`, `SELECT`, `UPDATE`, or `DELETE` — the difference is invisible to application SQL.

---

## Creating the Table via Workers

```typescript
// migrations/001_articles_without_rowid.sql  (run once via wrangler d1 execute)
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return new Response("use wrangler d1 execute for migrations");
  },
};
```

```sql
-- migrations/001_articles_without_rowid.sql
CREATE TABLE IF NOT EXISTS articles (
  slug      TEXT    NOT NULL,
  title     TEXT    NOT NULL,
  summary   TEXT    NOT NULL,
  published INTEGER NOT NULL DEFAULT (unixepoch()),
  PRIMARY KEY (slug)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS articles_published ON articles (published DESC);
```

```bash
wrangler d1 execute MY_DB --file=migrations/001_articles_without_rowid.sql
```

---

## Point-Lookup Worker Pattern

```typescript
interface Env {
  DB: D1Database;
}

// Prepared statements are reused across requests in the same isolate lifetime.
let getArticle: D1PreparedStatement | undefined;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const slug = url.pathname.slice(1); // e.g. /my-article-slug

    if (!slug || slug.includes("/")) {
      return new Response("Not Found", { status: 404 });
    }

    // Initialise once per isolate cold-start.
    getArticle ??= env.DB.prepare(
      "SELECT slug, title, summary, published FROM articles WHERE slug = ?1 LIMIT 1"
    );

    const row = await getArticle.bind(slug).first<{
      slug: string;
      title: string;
      summary: string;
      published: number;
    }>();

    if (!row) return new Response("Not Found", { status: 404 });

    return Response.json(row);
  },
};
```

---

## Composite Primary Key WITHOUT ROWID

The biggest win for WITHOUT ROWID comes from composite primary keys, where an ordinary table would need three B-trees (heap + composite PK index).

```sql
-- Session tokens keyed by (user_id, token) — common auth lookup pattern
CREATE TABLE sessions (
  user_id   TEXT    NOT NULL,
  token     TEXT    NOT NULL,
  expires   INTEGER NOT NULL,
  metadata  TEXT,
  PRIMARY KEY (user_id, token)
) WITHOUT ROWID;
```

```typescript
const SESSION_QUERY = `
  SELECT expires, metadata
  FROM sessions
  WHERE user_id = ?1 AND token = ?2
    AND expires > unixepoch()
  LIMIT 1
`;

async function validateSession(
  db: D1Database,
  userId: string,
  token: string
): Promise<{ expires: number; metadata: string | null } | null> {
  return db.prepare(SESSION_QUERY).bind(userId, token).first();
}
```

---

## Measuring the Improvement with EXPLAIN QUERY PLAN

```typescript
async function explainQuery(db: D1Database, sql: string, ...bindings: unknown[]) {
  const plan = await db
    .prepare(`EXPLAIN QUERY PLAN ${sql}`)
    .bind(...bindings)
    .all();
  return plan.results;
}

// Without ROWID you should see exactly ONE "SEARCH" node using the primary key.
// Ordinary table will show two: "SEARCH ... USING INDEX" + "TABLE SCAN" or similar.
const plan = await explainQuery(
  env.DB,
  "SELECT title FROM articles WHERE slug = ?1",
  "my-slug"
);
console.log(JSON.stringify(plan));
```

---

## Anti-patterns

- **WITHOUT ROWID for tables with wide TEXT/JSON columns.** Rows > 400 bytes make the clustered leaf pages too large; page splits outweigh the traversal savings. Store large blobs in R2, keep only metadata in D1.
- **Using `last_insert_rowid()` after INSERT.** The function always returns 0 for WITHOUT ROWID tables. Use `RETURNING slug` instead.
- **Auto-increment surrogate keys on WITHOUT ROWID.** Auto-increment relies on the rowid mechanism. Use `INTEGER PRIMARY KEY` for auto-increment, which already gets the single-tree layout via the rowid alias.
- **Frequent full-table scans.** WITHOUT ROWID tables are slower for full-table scans because the primary key is stored in every leaf; ordinary rowid tables are slightly more compact for sequential reads. Add explicit secondary indexes for non-PK filter columns.

---

## Gotchas

- **Cannot add WITHOUT ROWID to an existing table.** You must create a new table and migrate data. Schedule a maintenance window or use a dual-write migration.
- **`sqlite_stat1` vacuuming.** ANALYZE does not automatically run in D1; query planner statistics may be stale after large bulk inserts. Run `PRAGMA optimize;` periodically via a cron trigger.
- **SQLite version shipped with D1.** D1 runs SQLite 3.x; WITHOUT ROWID has been stable since 3.8.2 (2013) and is fully supported.
- **Replication lag.** D1 read replicas may lag by a few hundred milliseconds. WITHOUT ROWID does not change replication behavior, but primary key ordering affects replica page ordering.
- **Triggers on WITHOUT ROWID tables.** `OLD.rowid` and `NEW.rowid` are always NULL in trigger bodies; adapt trigger logic accordingly.

---

## Verification

```typescript
// Confirm no rowid column exists
const info = await env.DB.prepare(
  "PRAGMA table_xinfo(articles)"
).all();
const hasRowid = info.results.some((col: any) => col.name === "rowid");
console.assert(!hasRowid, "articles must be WITHOUT ROWID");

// Benchmark: compare CPU time before/after migration
const t0 = performance.now();
await env.DB.prepare("SELECT slug FROM articles WHERE slug = ?1")
  .bind("test-slug")
  .first();
const elapsed = performance.now() - t0;
console.log(`lookup latency: ${elapsed.toFixed(2)}ms`);
```

Use Cloudflare Workers Metrics (CPU time percentiles) to compare P50/P99 before and after the migration.

---

## Related

- `d1-batch-query-performance-optimization.md`
- `d1-prepared-statement-reuse.md`
- `d1-query-optimization.md`
- `d1-query-performance-explain-index.md`
- `workers-memory-allocation-optimization.md`

---

## Sources

- SQLite WITHOUT ROWID Tables documentation: https://www.sqlite.org/withoutrowid.html
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- SQLite B-tree page format: https://www.sqlite.org/fileformat2.html
- D1 EXPLAIN QUERY PLAN: https://developers.cloudflare.com/d1/build-with-d1/use-d1-locally/#query-debugging
