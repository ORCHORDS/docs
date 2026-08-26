# Full-Text Search with D1 FTS5 and Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need fast, ranked full-text search over a `articles` table stored in Cloudflare D1. SQLite's built-in FTS5 extension is available in D1 and provides `MATCH` queries with `highlight()`, `snippet()`, and `bm25()` ranking out of the box. The challenge is wiring FTS5 virtual tables to your content table and keeping them in sync automatically.

---

## Context

SQLite FTS5 (Full-Text Search version 5) is a virtual table module that builds an inverted index over text columns. D1 exposes the full SQLite FTS5 API. A content-table FTS5 index references an external table (`content='articles'`) so FTS rows store only the index, not duplicate content, saving storage. Synchronisation triggers (`AFTER INSERT`, `AFTER UPDATE`, `AFTER DELETE`) keep the index current without application-level bookkeeping. `bm25()` is a standard relevance-ranking function; lower (more negative) scores mean higher relevance. Workers query the FTS table with parameterised `MATCH` expressions to avoid SQL injection.

---

## Section 1 — D1 Schema

```sql
-- Main content table
CREATE TABLE IF NOT EXISTS articles (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id  TEXT    NOT NULL,
  title     TEXT    NOT NULL,
  body      TEXT    NOT NULL,
  tags      TEXT,                     -- JSON array stored as text
  published INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- FTS5 virtual table (content mirror — stores no body data itself)
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
  title,
  body,
  content='articles',
  content_rowid='id'
);

-- Keep FTS in sync on INSERT
CREATE TRIGGER IF NOT EXISTS articles_ai
AFTER INSERT ON articles BEGIN
  INSERT INTO articles_fts(rowid, title, body)
  VALUES (new.id, new.title, new.body);
END;

-- Keep FTS in sync on UPDATE
CREATE TRIGGER IF NOT EXISTS articles_au
AFTER UPDATE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, title, body)
  VALUES ('delete', old.id, old.title, old.body);
  INSERT INTO articles_fts(rowid, title, body)
  VALUES (new.id, new.title, new.body);
END;

-- Keep FTS in sync on DELETE
CREATE TRIGGER IF NOT EXISTS articles_ad
AFTER DELETE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, title, body)
  VALUES ('delete', old.id, old.title, old.body);
END;

-- Indexes on the base table
CREATE INDEX IF NOT EXISTS idx_articles_owner ON articles(owner_id);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published, created_at DESC);
```

---

## Section 2 — Worker implementation

```typescript
import { Env } from './types';

interface SearchResult {
  id: number;
  owner_id: string;
  title: string;
  snippet: string;
  highlight_title: string;
  rank: number;
}

interface SearchResponse {
  results: SearchResult[];
  query: string;
  total: number;
}

/**
 * Escapes user input for FTS5 MATCH expressions.
 * Wraps each token in double-quotes to prevent injection via
 * FTS5 query syntax (AND/OR/NOT/-/*).
 */
function escapeFts5Query(raw: string): string {
  return raw
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((token) => `"${token.replace(/"/g, '""')}"`)
    .join(' ');
}

export async function handleSearch(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const rawQuery = url.searchParams.get('q') ?? '';
  const limitParam = parseInt(url.searchParams.get('limit') ?? '20', 10);
  const limit = Math.min(Math.max(limitParam, 1), 100);

  if (rawQuery.length < 2) {
    return Response.json(
      { error: 'Query must be at least 2 characters.' },
      { status: 400 }
    );
  }

  const ftsQuery = escapeFts5Query(rawQuery);

  // JOIN back to articles table to get owner_id and published state.
  // bm25() returns negative scores; ORDER ASC puts best matches first.
  const { results } = await env.DB.prepare(
    `
    SELECT
      a.id,
      a.owner_id,
      a.title,
      highlight(articles_fts, 0, '<mark>', '</mark>') AS highlight_title,
      snippet(articles_fts, 1, '<mark>', '</mark>', '…', 32) AS snippet,
      bm25(articles_fts) AS rank
    FROM articles_fts
    JOIN articles AS a ON a.id = articles_fts.rowid
    WHERE articles_fts MATCH ?
      AND a.published = 1
    ORDER BY rank
    LIMIT ?
    `
  )
    .bind(ftsQuery, limit)
    .all<SearchResult>();

  const response: SearchResponse = {
    results: results ?? [],
    query: rawQuery,
    total: results?.length ?? 0,
  };

  return Response.json(response, {
    headers: { 'Cache-Control': 'public, max-age=30' },
  });
}

// Rebuild FTS index from scratch (admin endpoint)
export async function rebuildFtsIndex(env: Env): Promise<Response> {
  await env.DB.prepare(
    `INSERT INTO articles_fts(articles_fts) VALUES ('rebuild')`
  ).run();
  return Response.json({ ok: true, message: 'FTS index rebuilt.' });
}
```

---

## Section 3 — Query / Migration helper

```typescript
// migrations/0003_add_fts.sql should be applied via wrangler:
// wrangler d1 migrations apply DB --remote

// Helper: populate FTS for existing rows (run once after adding the virtual table)
export async function backfillFts(env: Env): Promise<void> {
  // 'rebuild' rescans the content table and re-populates the FTS index.
  await env.DB.prepare(
    `INSERT INTO articles_fts(articles_fts) VALUES ('rebuild')`
  ).run();
  console.log('FTS backfill complete.');
}

// Helper: verify FTS row count matches base table
export async function verifyFtsIntegrity(
  env: Env
): Promise<{ base: number; fts: number; ok: boolean }> {
  const [baseRow, ftsRow] = await env.DB.batch([
    env.DB.prepare(`SELECT COUNT(*) AS cnt FROM articles WHERE published = 1`),
    env.DB.prepare(`SELECT COUNT(*) AS cnt FROM articles_fts`),
  ]);

  const base = (baseRow.results[0] as { cnt: number }).cnt;
  const fts = (ftsRow.results[0] as { cnt: number }).cnt;
  return { base, fts, ok: base === fts };
}
```

---

## Anti-patterns

- **Storing duplicate text in FTS5** — Omitting `content=` forces FTS5 to copy all text into its own table; for large corpora this doubles storage. Always use `content='articles'` with `content_rowid='id'`.
- **Unescaped MATCH expressions** — Passing raw user input directly to `MATCH` lets users inject FTS5 operators (`NOT`, `-`, `*`). Wrap each token in double-quotes.
- **Missing triggers** — Skipping `AFTER UPDATE` / `AFTER DELETE` triggers causes stale FTS results. All three lifecycle triggers are required.
- **Querying FTS without the base table JOIN** — FTS5 returns `rowid` only; joining back to `articles` is mandatory to filter by `owner_id` or `published`.
- **Not calling `rebuild` after bulk import** — Inserting rows bypassing triggers (e.g. `wrangler d1 execute` with raw SQL) leaves the FTS index stale. Always call `rebuild` after bulk loads.

---

## Gotchas

- `bm25()` column indices (0, 1, …) map to the order columns appear in `CREATE VIRTUAL TABLE`, not the base table.
- `highlight()` and `snippet()` require `articles_fts` to be the driving table in the query; they fail if you query `articles` and join FTS as a filter.
- The `'delete'` command to FTS (`INSERT INTO articles_fts(articles_fts, rowid, …) VALUES ('delete', …)`) is FTS5-specific and differs from FTS4.
- D1 FTS5 `rank` is only available when the query contains `MATCH`; selecting `bm25()` without a `MATCH` clause throws.
- Phrase queries require double-quotes: `MATCH '"cloudflare workers"'` — single tokens do not need quoting.

---

## Verification

```bash
# Check virtual table exists
wrangler d1 execute DB --remote --command \
  "SELECT name, type FROM sqlite_master WHERE type='table' AND name LIKE '%fts%';"

# Run a test search
wrangler d1 execute DB --remote --command \
  "SELECT rowid, title FROM articles_fts WHERE articles_fts MATCH 'workers' LIMIT 5;"

# Check trigger existence
wrangler d1 execute DB --remote --command \
  "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='articles';"

# Integrity check
wrangler d1 execute DB --remote --command \
  "INSERT INTO articles_fts(articles_fts) VALUES ('integrity-check');"
```

---

## Related

- `d1-schema-migration-wrangler-workflow.md`
- `d1-composite-indexes-query-optimization.md`
- `d1-row-level-security-workers.md`

---

## Sources

- SQLite FTS5 documentation — https://www.sqlite.org/fts5.html
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- Cloudflare Workers + D1 binding — https://developers.cloudflare.com/d1/worker-api/
