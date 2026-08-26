# D1 FTS5 BM25 Custom Ranking Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Cloudflare Worker search endpoint backed by D1 FTS5 returns results that feel irrelevant: short-body matches outrank documents where the search term appears in the title, and high-traffic stale documents score above freshly updated ones. The default FTS5 ranking does not account for field importance or recency.

## Context

FTS5's built-in `bm25()` auxiliary function computes a BM25 score per matched row. It accepts per-column weight multipliers: `bm25(fts_table, w0, w1, w2 …)` where each weight corresponds to a column declared in the FTS5 `CREATE VIRTUAL TABLE`. A negative-sign score convention means more-negative = higher relevance (SQLite `ORDER BY rank` ascending by default). Custom hybrid scoring combines BM25 with application-specific signals (recency, popularity, exact-match bonus) inside a CTE using standard arithmetic on the raw score.

D1 ships with SQLite 3.38+ which includes a stable `bm25()` implementation. The `highlight()` and `snippet()` auxiliary functions are also available for result excerpts.

## FTS5 Table Setup with Column Weights

Create the FTS5 virtual table declaring columns in priority order — the weight index in `bm25()` matches the column declaration order:

```sql
-- migrations/0020_fts5_articles.sql

-- Base content table
CREATE TABLE IF NOT EXISTS articles (
  id          TEXT    PRIMARY KEY,
  tenant_id   TEXT    NOT NULL,
  title       TEXT    NOT NULL,
  summary     TEXT    NOT NULL DEFAULT '',
  body        TEXT    NOT NULL DEFAULT '',
  tags        TEXT    NOT NULL DEFAULT '',   -- space-separated
  score       INTEGER NOT NULL DEFAULT 0,    -- upvotes or engagement
  published   INTEGER,                       -- unixepoch, NULL = draft
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

-- FTS5 virtual table with content= pointing to the base table
-- Column order: title(0), summary(1), body(2), tags(3)
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
  title,
  summary,
  body,
  tags,
  content     = 'articles',
  content_rowid = 'rowid'
);

-- Keep FTS in sync via triggers
CREATE TRIGGER articles_ai AFTER INSERT ON articles BEGIN
  INSERT INTO articles_fts(rowid, title, summary, body, tags)
  VALUES (new.rowid, new.title, new.summary, new.body, new.tags);
END;

CREATE TRIGGER articles_ad AFTER DELETE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, title, summary, body, tags)
  VALUES ('delete', old.rowid, old.title, old.summary, old.body, old.tags);
END;

CREATE TRIGGER articles_au AFTER UPDATE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, title, summary, body, tags)
  VALUES ('delete', old.rowid, old.title, old.summary, old.body, old.tags);
  INSERT INTO articles_fts(rowid, title, summary, body, tags)
  VALUES (new.rowid, new.title, new.summary, new.body, new.tags);
END;
```

## BM25 Weighted Ranking Query

Pass per-column weights to `bm25()` to boost title matches over body matches:

```typescript
// src/search/articles.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface SearchResult {
  id: string;
  title: string;
  summary: string;
  bm25_score: number;
  published: number | null;
}

/**
 * BM25 weighted search.
 *
 * Column weights in bm25(table, w0, w1, w2, w3):
 *   w0 = title   weight = 10.0  (highest — title match is most relevant)
 *   w1 = summary weight =  5.0
 *   w2 = body    weight =  1.0
 *   w3 = tags    weight =  8.0  (tag match is high signal)
 *
 * bm25() returns a negative float; ORDER BY rank ASC = most relevant first.
 */
export async function searchArticles(
  db: D1Database,
  tenantId: string,
  query: string,
  limit = 20
): Promise<SearchResult[]> {
  const { results } = await db
    .prepare(
      `SELECT
         a.id,
         a.title,
         a.summary,
         bm25(articles_fts, 10.0, 5.0, 1.0, 8.0) AS bm25_score,
         a.published
       FROM articles_fts
       JOIN articles a ON a.rowid = articles_fts.rowid
       WHERE articles_fts MATCH ?
         AND a.tenant_id = ?
         AND a.published IS NOT NULL
       ORDER BY bm25_score ASC
       LIMIT ?`
    )
    .bind(query, tenantId, limit)
    .all<SearchResult>();

  return results;
}
```

## Hybrid Scoring: BM25 + Recency + Popularity

Combine BM25 with application signals in a CTE to produce a single hybrid relevance score:

```typescript
// src/search/hybrid-search.ts

export interface HybridResult {
  id: string;
  title: string;
  summary: string;
  hybrid_score: number;
  published: number | null;
  score: number;
}

/**
 * Hybrid relevance = BM25_component + recency_boost + popularity_boost
 *
 * BM25 component:   normalize by negating (higher = better, range roughly 0-20)
 * Recency boost:    articles updated within 7 days get +3.0
 * Popularity boost: log10(upvotes + 1) scaled by 0.5
 *
 * All components summed; ORDER BY hybrid_score DESC.
 */
export async function hybridSearch(
  db: D1Database,
  tenantId: string,
  query: string,
  limit = 20
): Promise<HybridResult[]> {
  const now = Math.floor(Date.now() / 1000);
  const weekAgo = now - 7 * 86_400;

  const { results } = await db
    .prepare(
      `WITH base AS (
         SELECT
           a.id,
           a.title,
           a.summary,
           a.published,
           a.score,
           a.updated_at,
           -- BM25: negate so higher = better; cap at 20 for normalization
           MIN(20.0, -bm25(articles_fts, 10.0, 5.0, 1.0, 8.0)) AS bm25_component
         FROM articles_fts
         JOIN articles a ON a.rowid = articles_fts.rowid
         WHERE articles_fts MATCH ?
           AND a.tenant_id = ?
           AND a.published IS NOT NULL
       )
       SELECT
         id,
         title,
         summary,
         published,
         score,
         ROUND(
           bm25_component
           + CASE WHEN updated_at >= ? THEN 3.0 ELSE 0.0 END
           + (LOG(MAX(score, 0) + 1) * 0.5),
           4
         ) AS hybrid_score
       FROM base
       ORDER BY hybrid_score DESC
       LIMIT ?`
    )
    .bind(query, tenantId, weekAgo, limit)
    .all<HybridResult>();

  return results;
}
```

> Note: SQLite 3.35+ includes `LOG()` as a math function. D1's SQLite build supports it; confirm with `SELECT LOG(10)` in `wrangler d1 execute`.

## Phrase Search and Column Filters

FTS5 supports phrase queries and column filters. Phrase matching is more precise but requires the exact sequence:

```typescript
// src/search/advanced.ts

/**
 * Exact phrase match in title column only.
 * FTS5 column filter syntax: {column_name}: query
 */
export async function exactTitleSearch(
  db: D1Database,
  tenantId: string,
  phrase: string,
  limit = 10
): Promise<SearchResult[]> {
  // Wrap user input in quotes for phrase match; escape internal quotes
  const safePhraseQuery = `{title}: "${phrase.replace(/"/g, '""')}"`;

  const { results } = await db
    .prepare(
      `SELECT
         a.id,
         a.title,
         a.summary,
         bm25(articles_fts, 10.0, 5.0, 1.0, 8.0) AS bm25_score,
         a.published
       FROM articles_fts
       JOIN articles a ON a.rowid = articles_fts.rowid
       WHERE articles_fts MATCH ?
         AND a.tenant_id = ?
         AND a.published IS NOT NULL
       ORDER BY bm25_score ASC
       LIMIT ?`
    )
    .bind(safePhraseQuery, tenantId, limit)
    .all<SearchResult>();

  return results;
}

/**
 * Highlighted excerpt using FTS5 snippet() function.
 * Returns the most relevant passage with <mark>…</mark> wrapping.
 */
export async function searchWithSnippet(
  db: D1Database,
  tenantId: string,
  query: string,
  limit = 10
): Promise<Array<SearchResult & { excerpt: string }>> {
  const { results } = await db
    .prepare(
      `SELECT
         a.id,
         a.title,
         bm25(articles_fts, 10.0, 5.0, 1.0, 8.0) AS bm25_score,
         a.published,
         a.summary,
         -- snippet(fts_table, column_index, open_tag, close_tag, ellipsis, num_tokens)
         snippet(articles_fts, 2, '<mark>', '</mark>', '…', 32) AS excerpt
       FROM articles_fts
       JOIN articles a ON a.rowid = articles_fts.rowid
       WHERE articles_fts MATCH ?
         AND a.tenant_id = ?
         AND a.published IS NOT NULL
       ORDER BY bm25_score ASC
       LIMIT ?`
    )
    .bind(query, tenantId, limit)
    .all<SearchResult & { excerpt: string }>();

  return results;
}
```

## Anti-patterns

- Using `ORDER BY rank` (the implicit FTS5 rank column) without specifying BM25 weights — `rank` is equivalent to `bm25(table)` with equal weights of 1.0 for all columns, ignoring field importance.
- Passing raw user input directly to `MATCH` without sanitization — FTS5 treats special characters (`"`, `*`, `(`, `)`, `-`, `^`, `OR`, `AND`, `NOT`) as query operators; unexpected syntax errors surface as D1 errors. Strip or escape unintended operators.
- Rebuilding the FTS5 index on every write instead of using content table + triggers — `INSERT INTO table_fts(table_fts) VALUES ('rebuild')` rescans the entire base table and blocks writes during rebuild; use incremental trigger maintenance instead.
- Ignoring the `content=` table and duplicating all text in the FTS5 shadow tables — with `content=articles`, FTS5 stores only the index structures and retrieves text from the base table on demand, halving storage use.
- Weighting all columns equally when field importance is domain-specific — title and tag matches almost always indicate higher relevance than body matches; encode domain knowledge in BM25 weights.

## Gotchas

- `bm25()` returns negative values in SQLite's FTS5 implementation; `ORDER BY rank ASC` (not DESC) puts the best match first. `ORDER BY bm25(...) ASC` is explicit and avoids confusion.
- The `content=` (content table) mode means FTS5 does not store the original text itself. If the base `articles` table row is deleted without the `AFTER DELETE` trigger running (e.g., via a `DELETE FROM articles` bulk wipe without triggers), the FTS5 index holds stale entries. Always confirm triggers exist before bulk deletes.
- FTS5 `MATCH` is case-insensitive for ASCII by default but does not fold Unicode — a search for "café" will not match "cafe" without a custom Unicode tokenizer. D1 does not ship the `unicode61` tokenizer enabled by default in all builds; test accented character handling.
- `snippet()` column index is zero-based and matches the column order in the FTS5 table declaration, not the base table. `snippet(articles_fts, 2, …)` returns a snippet from column 2 = `body`.
- BM25 weight values do not have an absolute scale; only relative ratios matter. Weights `10, 5, 1, 8` produce the same ranking order as `100, 50, 10, 80`. Use ratios, not magnitudes.

## Verification

```typescript
// tests/fts5-bm25.test.ts
import { env } from 'cloudflare:test';

describe('FTS5 BM25 weighted search', () => {
  beforeAll(async () => {
    await env.DB.exec(`
      INSERT INTO articles (id, tenant_id, title, summary, body, tags, published)
      VALUES
        ('a1', 't1', 'SQLite FTS5 Guide', 'Overview', 'Detailed body about FTS5', 'sqlite', 1000),
        ('a2', 't1', 'Getting Started',   'FTS5 intro', 'Basic overview', 'sqlite fts5', 1001),
        ('a3', 't1', 'Unrelated Topic',   'Other stuff', 'No relevant content here', 'misc', 1002)
    `);
  });

  it('title match outranks body-only match', async () => {
    const results = await searchArticles(env.DB, 't1', 'FTS5');
    expect(results.length).toBeGreaterThan(0);
    // a1 has FTS5 in title — should rank above a3 (no match)
    expect(results[0].id).not.toBe('a3');
    // a2 has FTS5 in tags and summary — should appear before a3
    const ids = results.map((r) => r.id);
    expect(ids.indexOf('a3')).toBe(-1); // a3 has no FTS5 match
  });

  it('bm25_score is negative', async () => {
    const results = await searchArticles(env.DB, 't1', 'sqlite');
    expect(results.every((r) => r.bm25_score < 0)).toBe(true);
  });
});
```

```bash
# Confirm bm25() is available and returns expected sign
wrangler d1 execute MY_DB --command \
  "SELECT id, bm25(articles_fts, 10, 5, 1, 8) AS score FROM articles_fts WHERE articles_fts MATCH 'sqlite' ORDER BY score ASC LIMIT 5"
```

## Related

- `database/d1-full-text-search-fts5.md` — FTS5 table setup, basic MATCH queries
- `database/d1-fts5-trigram-tokenizer.md` — custom tokenizer for substring/fuzzy search
- `database/d1-vector-hybrid-search-vectorize.md` — combining FTS5 with vector embeddings
- `database/d1-json-aggregation-analytics.md` — post-processing search results with JSON aggregation
- `database/d1-covering-index-composite-key-workers.md` — index strategies for non-FTS queries

## Sources

- https://www.sqlite.org/fts5.html
- https://www.sqlite.org/fts5.html#the_bm25_function
- https://developers.cloudflare.com/d1/platform/limits/
