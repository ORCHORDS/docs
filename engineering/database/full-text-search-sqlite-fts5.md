# SQLite FTS5 Full-Text Search

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

The search endpoint using `LIKE '%term%'` is slow (800 ms on a
200 k-row posts table), returns no relevance ranking, misses
plural or stemmed variants of the search term, and shows
`SCAN` in `EXPLAIN QUERY PLAN`. Users report that searching
"running" finds no results containing "runs" or "run".

## Context

SQLite's FTS5 (Full-Text Search version 5) is a virtual table
module that maintains an inverted index over one or more text
columns. Queries use the `MATCH` operator; the engine returns
only matching rows and exposes a `rank` column for BM25
relevance scoring.

Cloudflare D1 includes the FTS5 extension. Key differences
from PostgreSQL's `tsvector`:

- No stored generated columns; FTS sync must be done via
  application-layer dual writes (D1's HTTP API does not expose
  trigger DDL).
- Porter stemmer is built in but English-only.
- FTS5 virtual tables are separate from the main table; joins
  are always required.
- `highlight()` returns plain-text snippets with configurable
  markers, safe to display without additional escaping.

## Creating the FTS5 Virtual Table

```sql
-- Main posts table already exists:
-- CREATE TABLE posts (
--   id TEXT PRIMARY KEY,
--   body TEXT NOT NULL,
--   board_id TEXT NOT NULL,
--   author_id TEXT NOT NULL,
--   deleted_at INTEGER
-- );

-- FTS5 virtual table — content= links to the main table
CREATE VIRTUAL TABLE posts_fts
  USING fts5(
    body,
    content     = 'posts',
    content_rowid = 'rowid',
    tokenize    = 'unicode61 remove_diacritics 1'
  );

-- Populate from existing live rows on first deploy
INSERT INTO posts_fts (rowid, body)
  SELECT rowid, body FROM posts
  WHERE  deleted_at IS NULL;
```

`unicode61` handles non-ASCII text and strips diacritics.
For English stemming add `porter` before `unicode61`:
`tokenize = 'porter unicode61 remove_diacritics 1'`.
This makes search for "running" match "run", "runs", "runner".

## MATCH Queries and BM25 Relevance Ranking

```sql
-- Basic MATCH with relevance ordering
SELECT p.id, p.body, p.created_at
FROM   posts_fts f
JOIN   posts     p ON p.rowid = f.rowid
WHERE  f.body     MATCH ?1
  AND  p.deleted_at IS NULL
ORDER  BY rank          -- lower (more negative) = better
LIMIT  20;
```

`rank` is a built-in FTS5 auxiliary column. It is only
accessible inside a query that has a `MATCH` predicate.

FTS5 query syntax reference:

| Syntax              | Meaning                            |
|---------------------|------------------------------------|
| `word`              | Single token match                 |
| `"two words"`       | Exact phrase in order              |
| `word1 word2`       | Both tokens, any order             |
| `word1 OR word2`    | Either token                       |
| `word*`             | Prefix match (word, words, …)      |
| `NOT word`          | Exclude rows containing token      |
| `NEAR(a b, 5)`      | a and b within 5 tokens of each   |

Always sanitize user input before passing to `MATCH`; FTS5
throws on unbalanced quotes or bare hyphens. Strip special
characters and append `*` for a safe prefix search.

## highlight() and snippet() Functions

```sql
-- Wrap matched tokens in custom markers
SELECT
  p.id,
  highlight(posts_fts, 0, '<b>', '</b>') AS body_hl,
  rank
FROM   posts_fts f
JOIN   posts     p ON p.rowid = f.rowid
WHERE  f.body MATCH ?1
  AND  p.deleted_at IS NULL
ORDER  BY rank
LIMIT  10;
```

`highlight(table, column_index, before, after)` wraps every
matched token in the surrounding markers. Column index `0`
refers to the first column in the FTS5 definition (`body`).

For a short excerpt rather than the full body, use `snippet()`:

```sql
snippet(posts_fts, 0, '<b>', '</b>', '…', 32)
-- args: table, col_index, start_mark, end_mark,
--       ellipsis, max_tokens_returned
```

## Keeping the FTS Index in Sync

D1's HTTP API does not support SQL triggers. Use dual writes
inside `db.batch()`. On insert, pair the main `INSERT INTO
posts` with `INSERT INTO posts_fts (rowid, body) SELECT
rowid, body FROM posts WHERE id = ?1`. On soft delete add
`DELETE FROM posts_fts WHERE rowid = (SELECT rowid FROM posts
WHERE id = ?1)` to the same batch. On a post body edit,
delete the old FTS row and insert a new one — FTS5 `content=`
mode does not support `UPDATE`.

## Anti-patterns

- **Keeping `LIKE '%term%'` alongside FTS5** — `LIKE` still
  scans; route all search traffic through `MATCH`.
- **Not sanitizing `MATCH` input** — FTS5 throws on malformed
  syntax; wrap in `try/catch` and return an empty result set.
- **Syncing FTS5 outside a batch** — if the posts write
  succeeds but the FTS5 write fails, the index drifts
  silently; always use `db.batch()`.
- **Leaving soft-deleted rows in the FTS index** — search
  returns rowids that JOIN to deleted posts; results are
  silently missing, which misleads relevance scoring.
- **Porter stemmer for non-English content** — porter is
  English-only; use `unicode61` without `porter` for
  multilingual apps.

## Gotchas

- FTS5 `rowid` must match the posts table `rowid` exactly; if
  a row is deleted and re-inserted, the `rowid` changes and
  the FTS entry becomes an orphan.
- `content=` mode does not store the text itself. If a posts
  row is deleted without updating the FTS table, `MATCH` still
  returns the `rowid` and the subsequent `JOIN` returns no
  row — causing silent result gaps.
- `ORDER BY rank` is only valid when a `MATCH` predicate is
  present in the same query; it is an error otherwise.
- FTS5 `MATCH` is case-insensitive by default with `unicode61`.

## Verification

```sql
-- Confirm the FTS5 virtual table exists
SELECT name FROM sqlite_master
WHERE  type = 'table' AND name = 'posts_fts';

-- Run an integrity check (rebuilds internal structures)
INSERT INTO posts_fts (posts_fts) VALUES ('integrity-check');

-- Spot-check results for a known term
SELECT rowid, rank FROM posts_fts
WHERE  body MATCH 'test'
LIMIT  5;
```

## Related

- `database/full-text-search-tsvector.md`
- `database/d1-sqlite-query-optimization.md`
- `database/soft-delete-patterns.md`
- `database/sqlite-d1-patterns.md`

## Source URLs (verified 2026-08-17)

- https://www.sqlite.org/fts5.html
- https://www.sqlite.org/fts5.html#tokenizers
- https://www.sqlite.org/fts5.html#the_highlight_function
- https://developers.cloudflare.com/d1/platform/client-api/
