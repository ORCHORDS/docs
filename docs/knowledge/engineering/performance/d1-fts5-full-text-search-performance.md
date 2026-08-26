# D1 FTS5 Full-Text Search Query Performance

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers endpoint runs `SELECT * FROM products WHERE description LIKE '%wireless headphones%'` against a 200,000-row D1 table. The query takes 400–800 ms, pegs CPU time, and returns in unsorted relevance order. Switching to `LIKE` with a leading wildcard forces a full table scan every time. The fix is SQLite's FTS5 virtual table, which D1 supports and which reduces search queries to 5–20 ms with ranked results.

## Context

D1 exposes SQLite's FTS5 extension. An FTS5 virtual table maintains an inverted index of tokenized text columns. Queries use the `MATCH` operator and support phrase search, prefix search, column filters, and BM25 relevance ranking via the `bm25()` auxiliary function. The index is stored in shadow tables alongside the main table and is updated synchronously on `INSERT`/`UPDATE`/`DELETE`. The primary cost is index creation (one-time, offline) and slightly higher write latency; read query latency drops by 10–50× compared to `LIKE`.

---

## Creating an FTS5 Virtual Table

FTS5 tables are external content tables — they reference the real row data and store only the inverted index.

```sql
-- Main content table (normal D1 table)
CREATE TABLE IF NOT EXISTS products (
  id       INTEGER PRIMARY KEY,
  name     TEXT    NOT NULL,
  description TEXT NOT NULL,
  brand    TEXT    NOT NULL
);

-- FTS5 virtual table with content= pointing to the real table
CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
  name,
  description,
  brand,
  content='products',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 2'
);

-- Populate the FTS index from existing rows (run once during migration)
INSERT INTO products_fts(rowid, name, description, brand)
  SELECT id, name, description, brand FROM products;
```

## Keeping the FTS Index in Sync via Triggers

External content tables do not auto-update — triggers maintain the index.

```sql
-- Insert trigger
CREATE TRIGGER IF NOT EXISTS products_fts_insert
  AFTER INSERT ON products
BEGIN
  INSERT INTO products_fts(rowid, name, description, brand)
    VALUES (new.id, new.name, new.description, new.brand);
END;

-- Delete trigger (FTS5 delete requires inserting a negative row)
CREATE TRIGGER IF NOT EXISTS products_fts_delete
  AFTER DELETE ON products
BEGIN
  INSERT INTO products_fts(products_fts, rowid, name, description, brand)
    VALUES ('delete', old.id, old.name, old.description, old.brand);
END;

-- Update trigger
CREATE TRIGGER IF NOT EXISTS products_fts_update
  AFTER UPDATE ON products
BEGIN
  INSERT INTO products_fts(products_fts, rowid, name, description, brand)
    VALUES ('delete', old.id, old.name, old.description, old.brand);
  INSERT INTO products_fts(rowid, name, description, brand)
    VALUES (new.id, new.name, new.description, new.brand);
END;
```

## Querying FTS5 with BM25 Ranking from Workers

```typescript
const SEARCH_STMT = env.DB.prepare(`
  SELECT
    p.id,
    p.name,
    p.brand,
    p.description,
    bm25(products_fts) AS score
  FROM products_fts
  JOIN products p ON p.id = products_fts.rowid
  WHERE products_fts MATCH ?
  ORDER BY score
  LIMIT 20
`);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const q = new URL(request.url).searchParams.get('q') ?? '';
    if (!q.trim()) return Response.json([]);

    // Sanitize: FTS5 MATCH syntax can throw on unbalanced quotes/operators
    const safeQuery = sanitizeFtsQuery(q);

    const results = await SEARCH_STMT.bind(safeQuery).all();
    return Response.json(results.results);
  },
};

function sanitizeFtsQuery(input: string): string {
  // Escape double-quotes, wrap in phrase-match quotes if multi-word
  const escaped = input.replace(/"/g, '""');
  // For prefix search, append * to the last token
  const tokens = escaped.trim().split(/\s+/);
  return tokens.map((t, i) => (i === tokens.length - 1 ? `"${t}"*` : `"${t}"`)).join(' ');
}
```

## Column Filters and Prefix Search

Restrict search to specific columns to improve precision and index hit rate.

```typescript
// Search only in name and brand columns, not description
const COLUMN_SEARCH = env.DB.prepare(`
  SELECT p.id, p.name, bm25(products_fts, 10, 0, 5) AS score
  FROM products_fts
  JOIN products p ON p.id = products_fts.rowid
  WHERE products_fts MATCH 'name:? OR brand:?'
  ORDER BY score
  LIMIT 10
`);

// Prefix search for autocomplete (appends * to the query term)
async function autocomplete(prefix: string, env: Env): Promise<string[]> {
  if (prefix.length < 2) return [];
  const stmt = env.DB.prepare(`
    SELECT p.name
    FROM products_fts
    JOIN products p ON p.id = products_fts.rowid
    WHERE products_fts MATCH ?
    ORDER BY bm25(products_fts)
    LIMIT 8
  `);
  const results = await stmt.bind(`name:"${prefix.replace(/"/g, '""')}"*`).all<{ name: string }>();
  return results.results.map(r => r.name);
}
```

## Optimizing with FTS5 `optimize` and `rebuild` Commands

After bulk imports, run `optimize` to merge FTS5 segment files, reducing query latency.

```typescript
// Run after a bulk import — do this in a Cron Trigger, not in a request handler
async function optimizeFtsIndex(db: D1Database): Promise<void> {
  await db.exec("INSERT INTO products_fts(products_fts) VALUES ('optimize')");
}

// Full rebuild from scratch (use after schema changes or index corruption)
async function rebuildFtsIndex(db: D1Database): Promise<void> {
  await db.exec("INSERT INTO products_fts(products_fts) VALUES ('rebuild')");
}
```

## Paginating FTS Results with Offset

```typescript
interface SearchOpts {
  query: string;
  page: number;    // 0-indexed
  pageSize: number;
}

async function searchPaginated(
  opts: SearchOpts,
  env: Env
): Promise<{ results: unknown[]; hasMore: boolean }> {
  const stmt = env.DB.prepare(`
    SELECT p.id, p.name, bm25(products_fts) AS score
    FROM products_fts
    JOIN products p ON p.id = products_fts.rowid
    WHERE products_fts MATCH ?
    ORDER BY score
    LIMIT ? OFFSET ?
  `);

  const limit = opts.pageSize + 1; // fetch one extra to detect hasMore
  const offset = opts.page * opts.pageSize;
  const rows = await stmt.bind(opts.query, limit, offset).all<{ id: number; name: string; score: number }>();

  const hasMore = rows.results.length > opts.pageSize;
  return {
    results: rows.results.slice(0, opts.pageSize),
    hasMore,
  };
}
```

---

## Anti-patterns

- **Using `LIKE '%term%'`**: Forces a full table scan; index cannot be used. Replace with FTS5 `MATCH`.
- **Unsanitized user input in `MATCH`**: Unescaped `"` or FTS5 operators (e.g., `NOT`, `AND`, bare `*`) can throw `SQLITE_ERROR`. Always sanitize or escape query terms before binding.
- **Running `optimize` or `rebuild` in a request handler**: These operations can take seconds on large indices and will hit the CPU time limit. Run them in a Cron Trigger or via `waitUntil()` with a separate Workers Cron.
- **Storing the FTS5 virtual table without triggers**: Content tables that fall out of sync with the source table return stale or missing results. Always add the three triggers (insert, update, delete) at migration time.
- **Joining back to the main table for every query**: If you only need indexed columns (name, brand), read them directly from the FTS5 table. Skip the JOIN when possible.

---

## Gotchas

- `bm25()` returns negative scores — lower (more negative) is more relevant. `ORDER BY bm25(...)` (ascending) sorts by relevance descending.
- D1 SQLite version may not expose all FTS5 auxiliary functions. `highlight()` and `snippet()` are available; verify `fts5vocab` and `fts5_tokenize` availability against the D1 changelog.
- Phrase queries (`"wireless headphones"`) require the exact token sequence in the document. Tokenization is case-insensitive and diacritic-normalized with `unicode61 remove_diacritics 2`.
- FTS5 shadow tables (`products_fts_data`, `products_fts_idx`, etc.) count toward D1 storage. An index on a 100 MB text column may add 30–80 MB of shadow table storage.
- `content=` external content tables do not store the actual text — they only store the index. If the main table row is deleted without firing the delete trigger, the FTS table returns a rowid with no matching main-table row (dangling rowid). Always use the triggers.

---

## Verification

```sql
-- Confirm FTS index is populated
SELECT count(*) FROM products_fts;

-- Test a sample query and check latency
EXPLAIN QUERY PLAN
  SELECT rowid FROM products_fts WHERE products_fts MATCH 'wireless headphones';
-- Should show "SCAN products_fts VIRTUAL TABLE INDEX" — not a full scan
```

```typescript
// Measure D1 query duration from Workers
const t0 = performance.now();
const res = await env.DB.prepare(
  `SELECT id FROM products_fts WHERE products_fts MATCH ? LIMIT 20`
).bind('wireless headphones').all();
console.log(`FTS5 query: ${(performance.now() - t0).toFixed(1)} ms, ${res.results.length} rows`);
```

Target: <20 ms for MATCH queries on 100k–500k row tables.

---

## Related

- `d1-query-performance-explain-index.md` — using EXPLAIN QUERY PLAN for D1 queries
- `d1-covering-index-multi-column.md` — covering indexes for non-FTS queries
- `d1-pragma-optimize-query-planner.md` — SQLite query planner settings in D1
- `d1-prepared-statement-reuse.md` — reusing prepared statements for search endpoints

---

## Sources

- SQLite FTS5 extension docs: https://www.sqlite.org/fts5.html
- Cloudflare D1 SQLite compatibility: https://developers.cloudflare.com/d1/reference/database-configuration/
- FTS5 external content tables: https://www.sqlite.org/fts5.html#external_content_tables
- BM25 scoring in FTS5: https://www.sqlite.org/fts5.html#the_bm25_function
