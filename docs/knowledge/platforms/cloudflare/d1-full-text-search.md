# d1-full-text-search

**Issue:** Implementing full-text search in Cloudflare D1 using SQLite FTS5
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
D1 supports SQLite's FTS5 (Full-Text Search) extension. FTS5 creates a virtual table that can efficiently search text columns using `MATCH` queries, supporting phrase matching, prefix search, and ranking.

## Pattern / Solution

```sql
-- migrations/0002_add_fts.sql

-- 1. Create the FTS5 virtual table (content table pattern)
CREATE VIRTUAL TABLE posts_fts USING fts5(
  title,
  body,
  content='posts',       -- keep FTS in sync with the posts table
  content_rowid='id'
);

-- 2. Populate FTS from existing data
INSERT INTO posts_fts(rowid, title, body) SELECT id, title, body FROM posts;

-- 3. Keep FTS in sync via triggers
CREATE TRIGGER posts_ai AFTER INSERT ON posts BEGIN
  INSERT INTO posts_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;

CREATE TRIGGER posts_ad AFTER DELETE ON posts BEGIN
  INSERT INTO posts_fts(posts_fts, rowid, title, body) VALUES ('delete', old.id, old.title, old.body);
END;

CREATE TRIGGER posts_au AFTER UPDATE ON posts BEGIN
  INSERT INTO posts_fts(posts_fts, rowid, title, body) VALUES ('delete', old.id, old.title, old.body);
  INSERT INTO posts_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
```

```typescript
// Search query
export async function searchPosts(env: Env, query: string, limit = 20) {
  const { results } = await env.DB.prepare(`
    SELECT
      p.id,
      p.title,
      p.created,
      highlight(posts_fts, 1, '<mark>', '</mark>') AS body_snippet,
      rank
    FROM posts_fts
    JOIN posts p ON posts_fts.rowid = p.id
    WHERE posts_fts MATCH ?
    ORDER BY rank
    LIMIT ?
  `).bind(query, limit).all<{
    id: number;
    title: string;
    created: number;
    body_snippet: string;
    rank: number;
  }>();

  return results;
}

// Prefix search — append * to the last term
const results = await searchPosts(env, 'cloud* deploy');

// Phrase search
const exact = await searchPosts(env, '"cloudflare workers"');

// Column-scoped search
const titleOnly = await searchPosts(env, 'title: workers');
```

## Gotchas
- FTS5 `rank` is negative — lower (more negative) means more relevant; use `ORDER BY rank` (ASC) not `ORDER BY rank DESC`.
- The content table pattern (`content='posts'`) means FTS does not store the text itself — you must keep triggers in sync or the FTS index goes stale.
- `highlight()` and `snippet()` auxiliary functions work only in FTS5 SELECT context.
- FTS5 does not support `LIKE` queries — use `MATCH` syntax exclusively.
- Special characters in the query (`"`, `*`, `AND`, `OR`, `NOT`) are FTS5 operators — escape user input with `fts5_tokenize` or sanitise before binding.
- D1 does not support the `porter` tokeniser; use the default `unicode61` or `ascii`.

## Related
- `d1-best-practices.md`
- `d1-pragma-tuning.md`
- `vectorize-best-practices.md`
