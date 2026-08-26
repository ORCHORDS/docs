# Vitest Workers D1 FTS5 Full-Text Search Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker uses D1's SQLite FTS5 (full-text search) virtual tables to power search endpoints. You need Vitest tests that validate MATCH query correctness, rank ordering, snippet extraction, edge-case tokenisation, and the absence of SQL injection through search inputs — all against a real FTS5 engine, not a mock.

## Context

D1 is SQLite under the hood, and SQLite's FTS5 extension is available in D1. `@cloudflare/vitest-pool-workers` runs tests inside a real Miniflare Workers isolate that uses a local SQLite file, so FTS5 virtual tables, `MATCH` queries, `bm25()` ranking, and `snippet()` function calls all work in tests identically to production D1 behaviour.

---

## 1. Schema Setup via Migration

```sql
-- migrations/0001_create_posts.sql
CREATE TABLE IF NOT EXISTS posts (
  id      INTEGER PRIMARY KEY,
  title   TEXT NOT NULL,
  body    TEXT NOT NULL,
  author  TEXT NOT NULL
);

-- FTS5 virtual table — content= links it to the posts table
CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
  title,
  body,
  content = 'posts',
  content_rowid = 'id'
);

-- Keep FTS index in sync via triggers
CREATE TRIGGER IF NOT EXISTS posts_ai AFTER INSERT ON posts BEGIN
  INSERT INTO posts_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;

CREATE TRIGGER IF NOT EXISTS posts_ad AFTER DELETE ON posts BEGIN
  INSERT INTO posts_fts(posts_fts, rowid, title, body)
    VALUES ('delete', old.id, old.title, old.body);
END;

CREATE TRIGGER IF NOT EXISTS posts_au AFTER UPDATE ON posts BEGIN
  INSERT INTO posts_fts(posts_fts, rowid, title, body)
    VALUES ('delete', old.id, old.title, old.body);
  INSERT INTO posts_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;
```

---

## 2. Worker Search Handler

```typescript
// src/search.ts
export interface SearchResult {
  id: number;
  title: string;
  snippet: string;
  rank: number;
}

export async function searchPosts(
  db: D1Database,
  query: string,
  limit = 10
): Promise<SearchResult[]> {
  if (!query.trim()) return [];

  // FTS5 MATCH with BM25 ranking and snippet extraction
  const rows = await db
    .prepare(
      `SELECT
         p.id,
         p.title,
         snippet(posts_fts, 1, '<b>', '</b>', '…', 10) AS snippet,
         bm25(posts_fts)                                AS rank
       FROM posts_fts
       JOIN posts p ON p.id = posts_fts.rowid
       WHERE posts_fts MATCH ?
       ORDER BY rank
       LIMIT ?`
    )
    .bind(query, limit)
    .all<SearchResult>();

  return rows.results;
}
```

---

## 3. Test Fixture: Seeded FTS5 Database

```typescript
// src/search.test.ts
import { describe, it, expect, beforeAll } from "vitest";
import { env } from "cloudflare:test";
import { searchPosts } from "./search";

const SEED_POSTS = [
  { id: 1, title: "Getting started with Cloudflare Workers", body: "Learn how to deploy serverless functions on Cloudflare's edge network." },
  { id: 2, title: "D1 SQLite on the edge",                  body: "D1 brings SQLite to Cloudflare Workers with global replication." },
  { id: 3, title: "KV store patterns for Workers",          body: "Key-value storage for low-latency reads on the edge." },
  { id: 4, title: "R2 object storage with Workers",         body: "Store and retrieve files cheaply using Cloudflare R2." },
  { id: 5, title: "Durable Objects coordination",           body: "Strong consistency for Workers via Durable Objects actors." },
];

beforeAll(async () => {
  // Apply migrations
  await env.DB.exec(`
    CREATE TABLE IF NOT EXISTS posts (
      id INTEGER PRIMARY KEY, title TEXT NOT NULL,
      body TEXT NOT NULL, author TEXT NOT NULL DEFAULT 'test'
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
      title, body, content='posts', content_rowid='id'
    );
    CREATE TRIGGER IF NOT EXISTS posts_ai AFTER INSERT ON posts BEGIN
      INSERT INTO posts_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
    END;
  `);

  // Seed via batch to also fire the INSERT trigger
  await env.DB.batch(
    SEED_POSTS.map((p) =>
      env.DB.prepare("INSERT OR IGNORE INTO posts (id, title, body) VALUES (?, ?, ?)")
        .bind(p.id, p.title, p.body)
    )
  );
});
```

---

## 4. MATCH Query Correctness Tests

```typescript
describe("FTS5 MATCH query correctness", () => {
  it("finds post by keyword in title", async () => {
    const results = await searchPosts(env.DB, "D1");
    expect(results.length).toBeGreaterThanOrEqual(1);
    expect(results[0].title).toContain("D1");
  });

  it("finds post by keyword in body", async () => {
    const results = await searchPosts(env.DB, "replication");
    expect(results.some((r) => r.id === 2)).toBe(true);
  });

  it("returns empty array for zero-hit query", async () => {
    const results = await searchPosts(env.DB, "nonexistentxyz");
    expect(results).toHaveLength(0);
  });

  it("returns empty array for empty query string", async () => {
    const results = await searchPosts(env.DB, "");
    expect(results).toHaveLength(0);
  });

  it("matches prefix with * operator", async () => {
    // FTS5 prefix queries use the * suffix
    const results = await searchPosts(env.DB, "server*");
    expect(results.some((r) => r.body.includes("serverless"))).toBe(true);
  });

  it("phrase query matches consecutive words", async () => {
    const results = await searchPosts(env.DB, '"global replication"');
    expect(results.length).toBeGreaterThanOrEqual(1);
    expect(results[0].id).toBe(2);
  });
});
```

---

## 5. Ranking and Snippet Tests

```typescript
describe("FTS5 BM25 ranking and snippets", () => {
  it("more-specific match ranks higher", async () => {
    // Both posts mention 'storage', but the R2 post is more focused
    const results = await searchPosts(env.DB, "object storage");
    expect(results[0].id).toBe(4); // R2 post should rank first
  });

  it("snippet contains highlighted term wrapped in <b> tags", async () => {
    const results = await searchPosts(env.DB, "Workers");
    expect(results.length).toBeGreaterThan(0);
    // snippet() wraps matched tokens
    expect(results.some((r) => r.snippet.includes("<b>"))).toBe(true);
  });

  it("rank field is negative (BM25 returns negative scores)", async () => {
    const results = await searchPosts(env.DB, "Workers");
    // bm25() returns negative values; lower (more negative) = better match
    for (const r of results) {
      expect(r.rank).toBeLessThan(0);
    }
  });

  it("respects LIMIT parameter", async () => {
    const results = await searchPosts(env.DB, "Workers", 2);
    expect(results.length).toBeLessThanOrEqual(2);
  });
});
```

---

## 6. Edge Case and Injection Safety Tests

```typescript
describe("FTS5 edge cases and safety", () => {
  it("handles query with FTS5 special characters gracefully", async () => {
    // FTS5 operators: * " ( ) ^ - OR AND NOT
    // Passing raw operator strings should not throw or corrupt DB
    await expect(searchPosts(env.DB, "OR")).resolves.toBeDefined();
  });

  it("handles unicode query terms", async () => {
    const results = await searchPosts(env.DB, "функция");
    // No matches expected, but must not throw
    expect(Array.isArray(results)).toBe(true);
  });

  it("very long query string does not crash", async () => {
    const longQuery = "word ".repeat(200).trim();
    await expect(searchPosts(env.DB, longQuery)).resolves.toBeDefined();
  });

  it("SQL injection attempt via query string is safe", async () => {
    // Parameterised binding prevents injection; FTS5 MATCH treats value as a query, not SQL
    const results = await searchPosts(env.DB, "'; DROP TABLE posts; --");
    expect(Array.isArray(results)).toBe(true);
    // Verify posts table still intact
    const check = await env.DB.prepare("SELECT COUNT(*) AS n FROM posts").first<{ n: number }>();
    expect(check?.n).toBe(SEED_POSTS.length);
  });
});
```

---

## Anti-patterns

- **Creating the FTS5 table without `content=` and `content_rowid=`** — a contentless FTS5 table cannot use `snippet()` or `highlight()` and duplicates all post data; always use the external content table pattern with triggers.
- **Calling `INSERT INTO posts_fts … VALUES (…)` directly in tests** — bypassing triggers means the FTS index diverges from the base table; always insert into `posts` and let triggers keep FTS in sync.
- **Using `LIKE '%keyword%'` as a fallback in tests** — LIKE does a full-table scan and does not test FTS5 behaviour; keep test queries through the same `searchPosts` function used in production.
- **Not testing the `rank` field sign** — `bm25()` returns negative values; asserting `rank < 0` catches code that accidentally sorts `ASC` instead of the default `ORDER BY rank` (ascending = most negative first).
- **Sharing a single DB connection across parallel test workers** — each Vitest worker should have an isolated D1; use `wrangler: { configPath }` isolation or separate test suites.

## Gotchas

- FTS5 MATCH syntax is not SQL; unbalanced quotes (`"`) in the query string throw a "fts5: syntax error" SQLite error — validate and sanitise user queries before passing them to MATCH.
- `bm25()` is only valid inside an FTS5 query context; calling it in a non-FTS query throws at the SQLite level.
- Content tables with FTS5 triggers must use `INSERT OR IGNORE` or `INSERT OR REPLACE` carefully — a conflicting rowid insert can cause the FTS index to diverge.
- D1's local Miniflare uses a real SQLite file; running `vitest --watch` without resetting state between watch cycles can accumulate duplicate rows and skew ranking tests. Use `beforeAll` with `DELETE FROM posts; DELETE FROM posts_fts;` at the start.
- The `snippet()` function's fourth argument (the omission indicator, `'…'`) counts as one Unicode codepoint for column width calculations; use ASCII ellipsis to keep test assertions simple.

## Verification

```bash
# Run FTS5 tests in the Workers pool
npx vitest run src/search.test.ts

# Inspect local D1 for FTS index state
sqlite3 .wrangler/state/v3/d1/DB/db.sqlite \
  "SELECT * FROM posts_fts WHERE posts_fts MATCH 'Workers' ORDER BY rank LIMIT 5;"

# Confirm FTS virtual table exists
sqlite3 .wrangler/state/v3/d1/DB/db.sqlite \
  ".tables" | grep fts
```

## Related

- `d1-testing-local.md`
- `miniflare-d1-integration-testing.md`
- `vitest-workers-d1-schema-migration-testing.md`
- `vitest-d1-prepared-statement-caching-testing.md`
- `vitest-cloudflare-pool-workers.md`

## Sources

- https://www.sqlite.org/fts5.html
- https://developers.cloudflare.com/d1/platform/sql-api/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- https://developers.cloudflare.com/d1/best-practices/
