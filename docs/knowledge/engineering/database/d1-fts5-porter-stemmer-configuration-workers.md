# D1 FTS5 Porter Stemmer Configuration — Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A D1 FTS5 full-text search index returns no results for "running" when documents contain "run", and vice versa. The default `unicode61` tokenizer is not stemming English words — it treats each inflected form as a distinct token. Switching to the built-in `porter` tokenizer collapses morphological variants so that "run", "runs", "running", and "ran" all map to the same stem.

---

## Context

SQLite's FTS5 ships with three built-in tokenizers:

| Tokenizer | Stemming | Use-case |
|---|---|---|
| `unicode61` | None | Multilingual, case-fold only (default) |
| `ascii` | None | ASCII text, faster than unicode61 |
| `porter` | Porter English stemmer | English-language content search |
| `trigram` | None | Substring/LIKE search, typo-tolerant |

The **Porter stemmer** (Martin Porter, 1980) applies a sequence of suffix-stripping rules specific to English. It reduces words to their approximate root form (the "stem"): "generalises" → "general", "fishing" → "fish". It is built into SQLite's FTS5 module and therefore available in D1 with no additional extensions needed.

The porter tokenizer **wraps** another tokenizer — typically `unicode61` — for Unicode normalisation and case folding before stemming:

```sql
-- Full declaration with underlying tokenizer
tokenize = "porter unicode61"
```

---

## Creating an FTS5 Table with Porter Stemmer

```typescript
// src/lib/fts-schema.ts
import type { D1Database } from "@cloudflare/workers-types";

/**
 * Create an FTS5 virtual table with Porter stemming over an `articles` table.
 *
 * `content` mode keeps FTS5 as an index referencing the real table;
 * the porter tokenizer stems English tokens before indexing.
 */
export async function createFtsIndex(db: D1Database): Promise<void> {
  // Source table
  await db
    .prepare(
      `CREATE TABLE IF NOT EXISTS articles (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        title   TEXT NOT NULL,
        body    TEXT NOT NULL,
        tags    TEXT,
        lang    TEXT NOT NULL DEFAULT 'en'
      )`
    )
    .run();

  // FTS5 content table — indexes title and body with Porter stemming
  await db
    .prepare(
      `CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts
       USING fts5(
         title,
         body,
         content    = articles,
         content_rowid = id,
         tokenize   = 'porter unicode61'
       )`
    )
    .run();

  // Populate the FTS index from existing rows
  await db
    .prepare(
      `INSERT INTO articles_fts(articles_fts)
       VALUES ('rebuild')`
    )
    .run();
}
```

---

## Keeping the FTS Index in Sync

Because `content=articles` makes FTS5 a dependent index, you must update it manually on INSERT, UPDATE, and DELETE. Use triggers in the migration:

```typescript
// src/lib/fts-triggers.ts
import type { D1Database } from "@cloudflare/workers-types";

export async function createFtsTriggers(db: D1Database): Promise<void> {
  await db.batch([
    // INSERT trigger
    db.prepare(`
      CREATE TRIGGER IF NOT EXISTS articles_fts_insert
      AFTER INSERT ON articles BEGIN
        INSERT INTO articles_fts(rowid, title, body)
        VALUES (new.id, new.title, new.body);
      END
    `),
    // DELETE trigger
    db.prepare(`
      CREATE TRIGGER IF NOT EXISTS articles_fts_delete
      AFTER DELETE ON articles BEGIN
        INSERT INTO articles_fts(articles_fts, rowid, title, body)
        VALUES ('delete', old.id, old.title, old.body);
      END
    `),
    // UPDATE trigger
    db.prepare(`
      CREATE TRIGGER IF NOT EXISTS articles_fts_update
      AFTER UPDATE ON articles BEGIN
        INSERT INTO articles_fts(articles_fts, rowid, title, body)
        VALUES ('delete', old.id, old.title, old.body);
        INSERT INTO articles_fts(rowid, title, body)
        VALUES (new.id, new.title, new.body);
      END
    `),
  ]);
}
```

---

## Full-text Search Query with Stemming

```typescript
// src/repositories/article-search.ts
import type { D1Database } from "@cloudflare/workers-types";

export interface ArticleSearchResult {
  id: number;
  title: string;
  snippet: string;
  rank: number;
}

/**
 * Search articles using FTS5 with Porter stemming.
 *
 * The query is wrapped in double-quotes to treat multi-word phrases as
 * proximity queries; alternatively pass bare tokens for OR-style matching.
 */
export async function searchArticles(
  db: D1Database,
  query: string,
  limit = 20,
  offset = 0
): Promise<ArticleSearchResult[]> {
  // Sanitise user input: remove FTS5 operator characters to prevent injection
  const sanitised = query.replace(/[*"^()]/g, "").trim();
  if (!sanitised) return [];

  const results = await db
    .prepare(
      `SELECT
         a.id,
         a.title,
         snippet(articles_fts, 1, '<b>', '</b>', '…', 32) AS snippet,
         articles_fts.rank
       FROM articles_fts
       JOIN articles a ON a.id = articles_fts.rowid
       WHERE articles_fts MATCH ?1
       ORDER BY rank
       LIMIT ?2 OFFSET ?3`
    )
    .bind(sanitised, limit, offset)
    .all<ArticleSearchResult>();

  return results.results;
}
```

---

## Phrase Search and Boolean Operators

```typescript
// src/repositories/article-advanced-search.ts
import type { D1Database } from "@cloudflare/workers-types";

type FtsQueryMode = "phrase" | "and" | "or" | "prefix";

function buildFtsQuery(terms: string[], mode: FtsQueryMode): string {
  const escaped = terms.map((t) => t.replace(/[*"^()]/g, "").trim()).filter(Boolean);

  switch (mode) {
    case "phrase":
      return `"${escaped.join(" ")}"`;
    case "and":
      return escaped.join(" AND ");
    case "or":
      return escaped.join(" OR ");
    case "prefix":
      return escaped.map((t) => `${t}*`).join(" ");
    default:
      return escaped.join(" ");
  }
}

export async function advancedSearch(
  db: D1Database,
  terms: string[],
  mode: FtsQueryMode,
  column: "title" | "body" | "all" = "all"
): Promise<{ id: number; title: string }[]> {
  const ftsQuery = buildFtsQuery(terms, mode);
  const columnFilter = column === "all" ? ftsQuery : `{${column}} : ${ftsQuery}`;

  const results = await db
    .prepare(
      `SELECT a.id, a.title
       FROM articles_fts
       JOIN articles a ON a.id = articles_fts.rowid
       WHERE articles_fts MATCH ?1
       ORDER BY rank
       LIMIT 50`
    )
    .bind(columnFilter)
    .all<{ id: number; title: string }>();

  return results.results;
}
```

---

## Inspecting What the Porter Stemmer Produces

Use the `fts5vocab` virtual table to inspect tokens as D1 indexed them — useful to debug why a search term does or doesn't match:

```typescript
// src/lib/fts-debug.ts
import type { D1Database } from "@cloudflare/workers-types";

interface FtsVocabRow {
  term: string;
  doc: number;
  cnt: number;
}

/**
 * Inspect tokens in the FTS5 index.
 * Helps verify porter stemmer output: "running" appears as "run".
 */
export async function inspectFtsVocab(
  db: D1Database,
  prefix = ""
): Promise<FtsVocabRow[]> {
  // fts5vocab is created per-FTS-table with the _v suffix by convention
  await db
    .prepare(
      `CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts_v
       USING fts5vocab('articles_fts', 'row')`
    )
    .run();

  const filter = prefix ? `WHERE term LIKE ?1` : "";
  const params = prefix ? [`${prefix}%`] : [];

  const result = await db
    .prepare(
      `SELECT term, doc, cnt
       FROM articles_fts_v
       ${filter}
       ORDER BY term
       LIMIT 100`
    )
    .bind(...params)
    .all<FtsVocabRow>();

  return result.results;
}
```

Example result — note "running" and "runs" both appear as term `run`:

```
term      doc  cnt
────────────────────
run         3    7
search      1    2
walk        2    4
```

---

## Rebuilding the FTS Index

After bulk data imports or if the index becomes stale, trigger a rebuild:

```typescript
// src/lib/fts-rebuild.ts
import type { D1Database } from "@cloudflare/workers-types";

export async function rebuildFtsIndex(db: D1Database): Promise<void> {
  // 'rebuild' re-indexes all rows from the content table
  await db
    .prepare(`INSERT INTO articles_fts(articles_fts) VALUES ('rebuild')`)
    .run();

  // 'optimize' merges all FTS5 segment B-trees into one — run after bulk rebuild
  await db
    .prepare(`INSERT INTO articles_fts(articles_fts) VALUES ('optimize')`)
    .run();
}
```

---

## Wrangler Migration File

```sql
-- migrations/0005_fts5_porter.sql

CREATE TABLE IF NOT EXISTS articles (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  title   TEXT NOT NULL,
  body    TEXT NOT NULL,
  tags    TEXT,
  lang    TEXT NOT NULL DEFAULT 'en'
);

CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts
USING fts5(
  title,
  body,
  content       = articles,
  content_rowid = id,
  tokenize      = 'porter unicode61'
);

-- Sync triggers
CREATE TRIGGER IF NOT EXISTS articles_fts_insert
AFTER INSERT ON articles BEGIN
  INSERT INTO articles_fts(rowid, title, body)
  VALUES (new.id, new.title, new.body);
END;

CREATE TRIGGER IF NOT EXISTS articles_fts_delete
AFTER DELETE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, title, body)
  VALUES ('delete', old.id, old.title, old.body);
END;

CREATE TRIGGER IF NOT EXISTS articles_fts_update
AFTER UPDATE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, title, body)
  VALUES ('delete', old.id, old.title, old.body);
  INSERT INTO articles_fts(rowid, title, body)
  VALUES (new.id, new.title, new.body);
END;
```

---

## Anti-patterns

- **Using `porter` without `unicode61`**: `tokenize = 'porter'` alone defaults to ASCII processing. Non-ASCII characters (accented letters, em dashes) are not normalised. Always specify `porter unicode61`.
- **Mixing languages in a single Porter FTS table**: Porter stemming is English-specific. French "marcher" does not stem correctly. Use separate FTS tables per language, or the `unicode61` tokenizer for multilingual content.
- **Passing raw user input as FTS `MATCH` operands**: FTS5 query syntax includes operators (`*`, `"`, `^`). Always sanitise or escape user input before binding. Use parameterised `?` bindings — FTS5 supports them.
- **Not rebuilding after `content` table bulk inserts**: If you bypass triggers and INSERT directly into `articles` in bulk, the FTS index will be stale until you call `INSERT INTO articles_fts(articles_fts) VALUES ('rebuild')`.
- **Expecting exact-match ranking with Porter**: The stemmer changes tokens, which affects BM25 scoring. A search for "run" now matches "running" — but the relevance score also accounts for the stem frequency. Do not compare scores across different tokenizer configurations.

---

## Gotchas

- **`content` FTS tables do not store text**: When using `content=articles`, FTS5 stores only the index, not the actual text. If the source row is deleted without the trigger, `snippet()` and `highlight()` return empty strings for that row.
- **`optimize` is expensive**: `INSERT INTO articles_fts(articles_fts) VALUES ('optimize')` can take seconds on large tables. Run it only in Cron Triggers, not request handlers.
- **`rank` column default is BM25**: FTS5 `rank` is BM25 by default, negative values mean better match. `ORDER BY rank` (ascending) gives best results first.
- **D1 does not support custom FTS5 tokenizer extensions**: You cannot load external SQLite extensions in D1, so custom stemmers (Snowball, etc.) are not available. Porter is the only stemmer built-in to SQLite.
- **`fts5vocab` is a separate virtual table**: You must `CREATE VIRTUAL TABLE` for it — it doesn't exist automatically. Create it in dev/debug only; don't include it in production migrations.

---

## Verification

```typescript
// Verify porter stemming collapses inflections
async function verifyPorterStemming(db: D1Database): Promise<void> {
  // Insert test documents
  await db.batch([
    db.prepare(`INSERT INTO articles (title, body) VALUES ('Running Tests', 'We run tests daily and the runner is fast')`),
    db.prepare(`INSERT INTO articles (title, body) VALUES ('Run Configuration', 'Configure the run parameters')`),
  ]);

  // All three queries should return both rows
  for (const term of ["run", "runs", "running", "runner"]) {
    const results = await db
      .prepare(`SELECT id FROM articles_fts WHERE articles_fts MATCH ?1`)
      .bind(term)
      .all();
    console.log(`Term "${term}": ${results.results.length} results`);
    // Expect: 2 results for each term
  }
}
```

Expected output:
```
Term "run": 2 results
Term "runs": 2 results
Term "running": 2 results
Term "runner": 2 results
```

---

## Related

- `d1-full-text-search-fts5.md` — FTS5 baseline setup in D1
- `d1-fts5-bm25-custom-ranking-workers.md` — Custom BM25 rank weighting
- `d1-fts5-trigram-tokenizer.md` — Trigram tokenizer for substring search
- `full-text-search-sqlite-fts5.md` — SQLite FTS5 general reference
- `d1-json-columns-partial-indexes.md` — Combining FTS with partial indexes

---

## Sources

- SQLite FTS5 tokenizers: https://www.sqlite.org/fts5.html#tokenizers
- Porter stemming algorithm: https://tartarus.org/martin/PorterStemmer/
- SQLite FTS5 `fts5vocab`: https://www.sqlite.org/fts5.html#the_fts5vocab_virtual_table
- Cloudflare D1 full-text search guide: https://developers.cloudflare.com/d1/tutorials/query-d1-database-with-ai/
