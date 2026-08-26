# Full-Text Search in D1 Using SQLite FTS5

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need fast, relevance-ranked full-text search over a D1 table — product names, article bodies, user-generated content — without shipping a separate search service. SQLite's built-in FTS5 extension is available in D1 and gives you BM25 ranking, phrase queries, prefix queries, and highlight/snippet functions entirely inside the database.

## Context

D1 is Cloudflare's managed SQLite service. SQLite ships with FTS5 compiled in, and D1 exposes it. FTS5 stores a separate inverted index in shadow tables alongside your content table. You keep the two in sync either by copying data into the FTS table directly (content='' mode) or by pointing FTS5 at your real table and using triggers to propagate inserts, updates, and deletes.

BM25 scoring in FTS5 is negative by default (more negative = better match), so you ORDER BY rank ASC or negate it.

## Solution

### 1. Schema: content table + FTS5 virtual table

```sql
-- Real content table
CREATE TABLE IF NOT EXISTS articles (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  title     TEXT    NOT NULL,
  body      TEXT    NOT NULL,
  author    TEXT    NOT NULL,
  created_at TEXT   NOT NULL DEFAULT (datetime('now'))
);

-- FTS5 virtual table that mirrors articles
-- content='' means FTS5 owns its own copy of the text
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
  title,
  body,
  author,
  content='articles',
  content_rowid='id'
);

-- Keep FTS index in sync via triggers
CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
  INSERT INTO articles_fts(rowid, title, body, author)
  VALUES (new.id, new.title, new.body, new.author);
END;

CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, title, body, author)
  VALUES ('delete', old.id, old.title, old.body, old.author);
END;

CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, title, body, author)
  VALUES ('delete', old.id, old.title, old.body, old.author);
  INSERT INTO articles_fts(rowid, title, body, author)
  VALUES (new.id, new.title, new.body, new.author);
END;
```

### 2. Migration runner (TypeScript / Cloudflare Workers)

```typescript
// src/migrations/001_fts5_setup.ts
export const up = async (db: D1Database): Promise<void> => {
  await db.batch([
    db.prepare(`
      CREATE TABLE IF NOT EXISTS articles (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        title      TEXT NOT NULL,
        body       TEXT NOT NULL,
        author     TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
      )
    `),
    db.prepare(`
      CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
        title, body, author,
        content='articles',
        content_rowid='id'
      )
    `),
    db.prepare(`
      CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
        INSERT INTO articles_fts(rowid, title, body, author)
        VALUES (new.id, new.title, new.body, new.author);
      END
    `),
    db.prepare(`
      CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
        INSERT INTO articles_fts(articles_fts, rowid, title, body, author)
        VALUES ('delete', old.id, old.title, old.body, old.author);
      END
    `),
    db.prepare(`
      CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
        INSERT INTO articles_fts(articles_fts, rowid, title, body, author)
        VALUES ('delete', old.id, old.title, old.body, old.author);
        INSERT INTO articles_fts(rowid, title, body, author)
        VALUES (new.id, new.title, new.body, new.author);
      END
    `),
  ]);
};
```

### 3. Search service (BM25 ranking)

```typescript
// src/services/search.ts
export interface SearchResult {
  id: number;
  title: string;
  author: string;
  created_at: string;
  rank: number;
  title_snippet: string;
  body_snippet: string;
}

export interface SearchOptions {
  query: string;
  limit?: number;
  offset?: number;
  columns?: ('title' | 'body' | 'author')[]; // restrict search to specific columns
}

export async function searchArticles(
  db: D1Database,
  opts: SearchOptions
): Promise<{ results: SearchResult[]; total: number }> {
  const { query, limit = 20, offset = 0, columns } = opts;

  // Build column filter if requested
  // FTS5 column filter syntax: {title body} : term
  const ftsQuery = columns && columns.length > 0
    ? `{${columns.join(' ')}} : ${escapeFtsQuery(query)}`
    : escapeFtsQuery(query);

  // BM25 rank is negative; ORDER BY rank ASC = best first
  // highlight() wraps matched tokens with HTML tags
  // snippet() extracts a short excerpt with matched tokens highlighted
  const [rows, countRow] = await Promise.all([
    db
      .prepare(`
        SELECT
          a.id,
          a.title,
          a.author,
          a.created_at,
          fts.rank,
          highlight(articles_fts, 0, '<mark>', '</mark>') AS title_snippet,
          snippet(articles_fts, 1, '<mark>', '</mark>', '…', 32) AS body_snippet
        FROM articles_fts fts
        JOIN articles a ON a.id = fts.rowid
        WHERE articles_fts MATCH ?
        ORDER BY fts.rank ASC
        LIMIT ? OFFSET ?
      `)
      .bind(ftsQuery, limit, offset)
      .all<SearchResult>(),

    db
      .prepare(`
        SELECT COUNT(*) AS cnt
        FROM articles_fts
        WHERE articles_fts MATCH ?
      `)
      .bind(ftsQuery)
      .first<{ cnt: number }>(),
  ]);

  return {
    results: rows.results,
    total: countRow?.cnt ?? 0,
  };
}

/** Escape special FTS5 characters in user input */
function escapeFtsQuery(raw: string): string {
  // Wrap each word in double quotes to treat as phrase components,
  // then allow prefix matching on the last word.
  const words = raw.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '""';
  const escaped = words.map((w) => `"${w.replace(/"/g, '\'"\'')}"`);
  // Append * to last token for prefix search
  escaped[escaped.length - 1] += '*';
  return escaped.join(' ');
}
```

### 4. Worker handler

```typescript
// src/handlers/search.ts
import { searchArticles } from '../services/search';

export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/search' && request.method === 'GET') {
      const q = url.searchParams.get('q')?.trim() ?? '';
      const page = Math.max(1, parseInt(url.searchParams.get('page') ?? '1', 10));
      const limit = Math.min(50, Math.max(1, parseInt(url.searchParams.get('limit') ?? '20', 10)));
      const offset = (page - 1) * limit;

      if (q.length < 2) {
        return Response.json({ error: 'Query must be at least 2 characters' }, { status: 400 });
      }

      try {
        const { results, total } = await searchArticles(env.DB, { query: q, limit, offset });
        return Response.json({
          query: q,
          page,
          limit,
          total,
          pages: Math.ceil(total / limit),
          results,
        });
      } catch (err) {
        console.error('FTS search error', err);
        return Response.json({ error: 'Search failed' }, { status: 500 });
      }
    }

    return new Response('Not found', { status: 404 });
  },
};
```

### 5. Phrase search and prefix search examples

```typescript
// Phrase search — tokens must appear adjacent in that order
const phraseResults = await db
  .prepare(`SELECT rowid, title FROM articles_fts WHERE articles_fts MATCH ? ORDER BY rank`)
  .bind('"cloudflare workers"')
  .all();

// Prefix search — matches 'work', 'worker', 'workers', etc.
const prefixResults = await db
  .prepare(`SELECT rowid, title FROM articles_fts WHERE articles_fts MATCH ? ORDER BY rank`)
  .bind('work*')
  .all();

// Column-scoped search — only match in title
const titleOnly = await db
  .prepare(`SELECT rowid, title FROM articles_fts WHERE articles_fts MATCH ? ORDER BY rank`)
  .bind('title : D1')
  .all();

// Boolean operators
const boolResults = await db
  .prepare(`SELECT rowid, title FROM articles_fts WHERE articles_fts MATCH ? ORDER BY rank`)
  .bind('D1 AND (search OR fts5) NOT deprecated')
  .all();
```

### 6. Rebuild FTS index (after bulk import)

```typescript
async function rebuildFtsIndex(db: D1Database): Promise<void> {
  // Rebuild from content table when triggers were bypassed (e.g. bulk INSERT via wrangler d1 execute)
  await db.prepare(`INSERT INTO articles_fts(articles_fts) VALUES ('rebuild')`).run();
}
```

## Implementation Details

- FTS5 shadow tables are prefixed with the virtual table name (e.g. `articles_fts_data`, `articles_fts_idx`). They are managed automatically; do not write to them directly.
- `content='articles'` tells FTS5 where to find the original text for `highlight()` and `snippet()`. The FTS table does NOT store a second copy of your text — it only stores the index. If the content table row is deleted without the trigger, `highlight()` returns empty strings.
- BM25 weights can be tuned per-column: `bm25(articles_fts, 10.0, 1.0, 0.5)` — higher weight = title matches rank higher than body matches.
- The `rank` column is a special FTS5 auxiliary that returns the BM25 score for the current row against the query.
- `snippet()` signature: `snippet(table, column_index, open_tag, close_tag, ellipsis, max_tokens)`.

## Anti-patterns

- **LIKE queries for search** — `WHERE body LIKE '%term%'` performs a full table scan and cannot rank by relevance. FTS5 is orders of magnitude faster on large tables.
- **Forgetting triggers** — Inserting into `articles` directly without the AFTER INSERT trigger leaves the FTS index stale. Always apply the three triggers (INSERT, UPDATE, DELETE).
- **Unescaped user input** — Passing raw user input to MATCH causes syntax errors or injection. Always sanitize with `escapeFtsQuery()` or equivalent.
- **Storing HTML in FTS columns** — HTML tags pollute the token index. Strip HTML before inserting into the content table.
- **Querying FTS without MATCH** — `SELECT * FROM articles_fts` without a WHERE clause returns all rows but with no rank; use it only for debugging.

## Gotchas

- D1 runs SQLite 3.x; FTS5 is available but FTS4 (`fts4` keyword) is also present. Use `fts5` — it has better performance and BM25 built in.
- `ORDER BY rank` in FTS5 triggers an implicit optimization that avoids a full sort; changing the ORDER BY column (e.g. adding a secondary sort) may force a full scan.
- The `highlight()` function returns the **original text** with match tokens wrapped. If the original row is deleted (bypassing the delete trigger), highlight() returns an empty string — not an error.
- D1 `batch()` executes statements in a single HTTP round-trip but each statement is still a separate SQLite transaction. Schema DDL and DML can coexist in a batch.
- FTS5 MATCH syntax is not the same as SQLite LIKE or GLOB. Test edge cases: queries with parentheses, hyphens, and single-character tokens.

## Verification

```bash
# Insert test data and verify search works
npx wrangler d1 execute example project-db --command "
  INSERT INTO articles (title, body, author) VALUES
    ('Getting started with D1', 'D1 is Cloudflare\'s SQLite database for Workers.', 'orchords'),
    ('FTS5 full-text search', 'Full-text search with BM25 ranking in SQLite.', 'orchords');
"

# Verify FTS index was populated via trigger
npx wrangler d1 execute example project-db --command "
  SELECT rowid, title FROM articles_fts WHERE articles_fts MATCH 'cloudflare*' ORDER BY rank;
"
# Expected: row for 'Getting started with D1'

# Verify BM25 ranking (more negative = better)
npx wrangler d1 execute example project-db --command "
  SELECT title, rank FROM articles_fts WHERE articles_fts MATCH 'search' ORDER BY rank;
"
```

## Related

- `documentation/categories/database/d1-schema-version-tracking.md` — migration runner for applying the FTS5 DDL
- `documentation/categories/database/d1-json-column-queries.md` — indexing JSON fields alongside FTS columns
- `documentation/categories/database/d1-row-level-security-pattern.md` — combining RLS filters with FTS MATCH

## Sources

- https://www.sqlite.org/fts5.html
- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/fts5.html#the_bm25_function
