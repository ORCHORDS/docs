# Full-Text Search with D1 FTS5

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Workers application stores articles, product listings, or documentation in D1 and needs users to search across titles and body text with relevance ranking, phrase matching, and autocomplete-style prefix queries. `LIKE '%keyword%'` scans entire tables and ignores word boundaries; it does not scale beyond a few thousand rows.

## Context

SQLite ships with FTS5 (Full-Text Search version 5) built in. D1 exposes this extension. FTS5 maintains an inverted index over tokenised text columns and supports BM25 ranking, snippet extraction, phrase search with double-quotes, and prefix search with the `*` operator. The index must be kept in sync with the source table; D1 does not support arbitrary triggers natively but you can maintain sync through application-level batch writes or with SQLite `AFTER INSERT / UPDATE / DELETE` triggers declared in DDL.

## Solution

```typescript
// src/db/fts.ts
import type { D1Database } from '@cloudflare/workers-types';

// ----- Schema setup (run once via migration) --------------------------------

export const FTS_SETUP_SQL = `
  -- Source content table
  CREATE TABLE IF NOT EXISTS articles (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    author_id   TEXT NOT NULL,
    published   INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL DEFAULT (unixepoch())
  );

  -- FTS5 virtual table — content= links it to the source table.
  -- tokenize='porter ascii' applies Porter stemming for English.
  CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    title,
    body,
    content='articles',
    content_rowid='rowid',
    tokenize='porter ascii'
  );

  -- Triggers to keep the FTS index in sync with the content table.
  CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
    INSERT INTO articles_fts(rowid, title, body)
    VALUES (new.rowid, new.title, new.body);
  END;

  CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, body)
    VALUES ('delete', old.rowid, old.title, old.body);
    INSERT INTO articles_fts(rowid, title, body)
    VALUES (new.rowid, new.title, new.body);
  END;

  CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, body)
    VALUES ('delete', old.rowid, old.title, old.body);
  END;
`;

// ----- Types ----------------------------------------------------------------

export interface Article {
  id: string;
  title: string;
  body: string;
  author_id: string;
  published: number;
  created_at: number;
}

export interface SearchResult {
  id: string;
  title: string;
  snippet: string;
  rank: number;
}

export interface SearchOptions {
  query: string;
  /** BM25 column weights: [title_weight, body_weight] */
  weights?: [number, number];
  limit?: number;
  offset?: number;
  /** Restrict to phrase match — wraps query in double quotes */
  phraseMatch?: boolean;
  /** Enable prefix search — appends * to each token */
  prefixSearch?: boolean;
}

// ----- Helper: build FTS query string --------------------------------------

function buildFtsQuery(options: SearchOptions): string {
  const { query, phraseMatch, prefixSearch } = options;
  const trimmed = query.trim();

  if (phraseMatch) {
    // Escape any internal double-quotes.
    return `"${trimmed.replace(/"/g, '""')}"`;
  }

  if (prefixSearch) {
    // Append * to each token for prefix matching.
    return trimmed
      .split(/\s+/)
      .filter(Boolean)
      .map((t) => `${t}*`)
      .join(' ');
  }

  return trimmed;
}

// ----- Core search function ------------------------------------------------

export async function searchArticles(
  db: D1Database,
  options: SearchOptions
): Promise<{ results: SearchResult[]; total: number }> {
  const { weights = [10, 1], limit = 20, offset = 0 } = options;
  const ftsQuery = buildFtsQuery(options);

  // Count query for pagination metadata.
  const countRow = await db
    .prepare(
      `SELECT COUNT(*) AS n
       FROM articles_fts
       WHERE articles_fts MATCH ?
         AND published = 1`
    )
    .bind(ftsQuery)
    .first<{ n: number }>();

  const total = countRow?.n ?? 0;
  if (total === 0) return { results: [], total: 0 };

  // BM25 ranks lower scores as more relevant (negative values).
  // bm25(fts_table, col0_weight, col1_weight)
  const rows = await db
    .prepare(
      `SELECT
         a.id,
         a.title,
         snippet(articles_fts, 1, '<b>', '</b>', '…', 24) AS snippet,
         bm25(articles_fts, ?, ?) AS rank
       FROM articles_fts
       JOIN articles AS a ON a.rowid = articles_fts.rowid
       WHERE articles_fts MATCH ?
         AND a.published = 1
       ORDER BY rank
       LIMIT ? OFFSET ?`
    )
    .bind(weights[0], weights[1], ftsQuery, limit, offset)
    .all<SearchResult>();

  return { results: rows.results, total };
}

// ----- Rebuild index (for backfill after schema changes) -------------------

export async function rebuildFtsIndex(db: D1Database): Promise<void> {
  // Delete all FTS rows and re-insert from the source table.
  await db.exec(
    `INSERT INTO articles_fts(articles_fts) VALUES('rebuild');`
  );
  console.log('[fts] index rebuilt from content table.');
}

// ----- Worker handler -------------------------------------------------------

// src/index.ts
import { searchArticles, FTS_SETUP_SQL } from './db/fts';

export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/search') {
      const q = url.searchParams.get('q') ?? '';
      if (!q) return new Response('Missing q', { status: 400 });

      const page = parseInt(url.searchParams.get('page') ?? '1', 10);
      const limit = 20;
      const offset = (page - 1) * limit;
      const phraseMatch = url.searchParams.get('phrase') === 'true';
      const prefixSearch = url.searchParams.get('prefix') === 'true';

      const { results, total } = await searchArticles(env.DB, {
        query: q,
        limit,
        offset,
        phraseMatch,
        prefixSearch,
      });

      return Response.json({
        results,
        pagination: {
          total,
          page,
          limit,
          pages: Math.ceil(total / limit),
        },
      });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Implementation Details

**Content-linked FTS5 table** — `content='articles'` tells FTS5 not to store a redundant copy of the text; it reads from the `articles` table when needed for snippet generation. This halves storage but requires the `content_rowid` mapping and the three sync triggers.

**BM25 column weighting** — `bm25(articles_fts, 10, 1)` weights title matches ten times higher than body matches. BM25 returns negative values; `ORDER BY rank` puts the most relevant row first (most-negative rank = highest relevance).

**`snippet()` function** — extracts a fragment of the matched column (column index 1 = body) surrounding the matching tokens, wraps them in `<b>` tags, and truncates to 24 tokens. The fifth argument is the ellipsis string.

**Porter stemmer** — `tokenize='porter ascii'` maps inflected forms to their stem (`running` → `run`) so a search for `run` matches `running`, `runs`, `ran`. Use `unicode61` for multilingual content.

**`rebuild` command** — `INSERT INTO articles_fts(articles_fts) VALUES('rebuild')` rebuilds the entire index from the content table. Use this after importing bulk data that bypassed triggers, or after the `content=` table is restored from backup.

**Pagination** — FTS5 does not expose an efficient `COUNT(*)` path; the count query does a separate match scan. For very large result sets, consider caching the count or using cursor-based pagination.

## Anti-patterns

- **Using `LIKE` alongside FTS for the same search** — redundant and slower; pick one strategy.
- **Querying `articles_fts` without `JOIN`ing the source table** — with `content=`, columns in FTS rows are empty unless you explicitly `JOIN`.
- **Storing HTML in the indexed columns** — FTS tokenises angle brackets as word boundaries, bloating the index with tag names. Strip HTML before inserting.
- **Neglecting to escape user input** — an unescaped `*` or `"` in the query string will cause an FTS5 syntax error. Sanitise or escape before passing to `MATCH`.
- **Rebuilding on every deploy** — `rebuild` is expensive (full table scan); run it only after bulk imports.

## Gotchas

- FTS5 `MATCH` is case-insensitive by default with the `ascii` tokeniser. The `porter` tokeniser is also case-insensitive.
- `bm25()` requires the FTS virtual table name as the first argument, not the shadow tables. Do not pass the joined `articles` alias.
- D1's `db.exec()` does not return rows; use `db.prepare().all()` for queries that return data.
- Prefix search (`word*`) is fast because FTS5 uses a prefix-optimised B-tree. Suffix search (`*word`) is not supported; use `LIKE` for suffix needs.
- The `snippet()` function slows down at very high `max_tokens` values (>64). Keep it at 24–32 for search results.

## Verification

```typescript
// Quick smoke test via wrangler dev
async function smokeTest(baseUrl: string) {
  // Phrase search
  const phrase = await fetch(`${baseUrl}/search?q=cloudflare+workers&phrase=true`);
  const phraseData = await phrase.json();
  console.assert(Array.isArray(phraseData.results), 'phrase search returns array');

  // Prefix search (autocomplete)
  const prefix = await fetch(`${baseUrl}/search?q=cloud&prefix=true`);
  const prefixData = await prefix.json();
  console.assert(prefixData.pagination.total >= 0, 'prefix search has total');

  // Standard ranked search
  const ranked = await fetch(`${baseUrl}/search?q=workers+d1`);
  const rankedData = await ranked.json();
  if (rankedData.results.length > 1) {
    console.assert(
      rankedData.results[0].rank <= rankedData.results[1].rank,
      'results sorted by BM25 rank'
    );
  }
}
```

## Related

- [workers-d1-schema-versioning](workers-d1-schema-versioning.md)
- [workers-d1-soft-delete-pattern](workers-d1-soft-delete-pattern.md)

## Sources

- https://www.sqlite.org/fts5.html
- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/fts5.html#the_bm25_function
