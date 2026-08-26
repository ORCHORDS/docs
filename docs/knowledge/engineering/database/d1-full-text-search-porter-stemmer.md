# FTS5 with Porter Stemmer in D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need full-text search over a `documents` table in D1 with stemming so that "running" matches "run" and "runner". D1 supports SQLite FTS5 including the Porter stemmer tokenizer, enabling ranked search without an external search service.

## Context

- Runtime: Cloudflare Workers (ESM, TypeScript)
- Database: Cloudflare D1 (SQLite FTS5 enabled)
- Tokenizer: `porter ascii` (stems English terms, strips non-ASCII noise)
- Ranking: `bm25()` auxiliary function built into FTS5

---

## Section 1: Create the FTS5 Virtual Table

```sql
-- migrations/0003_fts.sql

-- Source content table
CREATE TABLE IF NOT EXISTS documents (
  id          TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  title       TEXT NOT NULL,
  body        TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- FTS5 virtual table using Porter stemmer
-- 'content' mode mirrors an existing table so FTS5 does not duplicate storage.
-- 'content_rowid' maps to the rowid of the content table.
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
  USING fts5(
    title,
    body,
    content     = 'documents',
    content_rowid = 'rowid',
    tokenize    = 'porter ascii'
  );

-- Populate FTS index from existing rows
INSERT INTO documents_fts (documents_fts) VALUES ('rebuild');
```

> **Note**: The `porter ascii` tokenizer applies Porter stemming to ASCII tokens. For multilingual content replace `ascii` with `unicode61`.

---

## Section 2: Keep the FTS Index in Sync

Because D1 does not reliably fire `AFTER INSERT` triggers visible to the application, maintain the FTS index explicitly inside the write wrappers.

```typescript
// src/db/documents-write.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface NewDocument {
  id: string;
  tenantId: string;
  title: string;
  body: string;
}

export async function insertDocument(
  db: D1Database,
  doc: NewDocument,
): Promise<void> {
  // 1. Insert the canonical row
  const insertRow = db
    .prepare(
      `INSERT INTO documents (id, tenant_id, title, body)
       VALUES (?, ?, ?, ?)`,
    )
    .bind(doc.id, doc.tenantId, doc.title, doc.body);

  // 2. Insert into FTS index (content= tables require explicit sync)
  // We first need the rowid; batch gives us the RETURNING equivalent via last_row_id.
  const [result] = await db.batch([insertRow]);
  const rowid = result.meta.last_row_id;

  await db
    .prepare(
      `INSERT INTO documents_fts (rowid, title, body)
       VALUES (?, ?, ?)`,
    )
    .bind(rowid, doc.title, doc.body)
    .run();
}

export async function updateDocument(
  db: D1Database,
  id: string,
  tenantId: string,
  title: string,
  body: string,
): Promise<void> {
  // Fetch rowid for the FTS delete+insert dance
  const row = await db
    .prepare(`SELECT rowid FROM documents WHERE id = ? AND tenant_id = ?`)
    .bind(id, tenantId)
    .first<{ rowid: number }>();

  if (!row) throw new Error(`Document ${id} not found`);

  const updateRow = db
    .prepare(
      `UPDATE documents SET title = ?, body = ? WHERE id = ? AND tenant_id = ?`,
    )
    .bind(title, body, id, tenantId);

  // FTS5 content= tables: delete old index entry, insert new one
  const ftsDelete = db
    .prepare(`INSERT INTO documents_fts (documents_fts, rowid, title, body) VALUES ('delete', ?, ?, ?)`)
    .bind(row.rowid, title, body); // title/body values here are the OLD values for the delete

  const ftsInsert = db
    .prepare(`INSERT INTO documents_fts (rowid, title, body) VALUES (?, ?, ?)`)
    .bind(row.rowid, title, body);

  await db.batch([updateRow, ftsDelete, ftsInsert]);
}

export async function deleteDocument(
  db: D1Database,
  id: string,
  tenantId: string,
): Promise<void> {
  const row = await db
    .prepare(`SELECT rowid, title, body FROM documents WHERE id = ? AND tenant_id = ?`)
    .bind(id, tenantId)
    .first<{ rowid: number; title: string; body: string }>();

  if (!row) return;

  const deleteRow = db
    .prepare(`DELETE FROM documents WHERE id = ? AND tenant_id = ?`)
    .bind(id, tenantId);

  const ftsDelete = db
    .prepare(
      `INSERT INTO documents_fts (documents_fts, rowid, title, body)
       VALUES ('delete', ?, ?, ?)`,
    )
    .bind(row.rowid, row.title, row.body);

  await db.batch([deleteRow, ftsDelete]);
}
```

---

## Section 3: Workers Search Endpoint with BM25 Ranking

`bm25()` is an FTS5 auxiliary function that returns a negative score (more negative = more relevant). Negate it for `ORDER BY relevance DESC`.

```typescript
// src/routes/search.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface SearchResult {
  id: string;
  title: string;
  snippet: string;
  relevance: number;
}

export async function searchDocuments(
  db: D1Database,
  tenantId: string,
  query: string,
  limit = 20,
  offset = 0,
): Promise<SearchResult[]> {
  if (!query.trim()) return [];

  // Sanitise query: strip FTS5 special characters to prevent injection
  const safeQuery = query
    .replace(/["*^()]/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((term) => `"${term}"`)  // phrase-quote each token
    .join(' OR ');

  if (!safeQuery) return [];

  const { results } = await db
    .prepare(
      `SELECT
         d.id,
         d.title,
         snippet(documents_fts, 1, '<b>', '</b>', '…', 16) AS snippet,
         -bm25(documents_fts) AS relevance
       FROM documents_fts
       JOIN documents d ON documents_fts.rowid = d.rowid
       WHERE documents_fts MATCH ?
         AND d.tenant_id = ?
       ORDER BY relevance DESC
       LIMIT ? OFFSET ?`,
    )
    .bind(safeQuery, tenantId, limit, offset)
    .all<SearchResult>();

  return results;
}

// Cloudflare Workers fetch handler
export default {
  async fetch(request: Request, env: { DB: D1Database }): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== '/search') {
      return new Response('Not Found', { status: 404 });
    }

    const q = url.searchParams.get('q') ?? '';
    const tenantId = request.headers.get('X-Tenant-Id') ?? '';
    const limit = Math.min(Number(url.searchParams.get('limit') ?? '20'), 100);
    const offset = Number(url.searchParams.get('offset') ?? '0');

    if (!tenantId) return new Response('Missing X-Tenant-Id', { status: 400 });

    try {
      const results = await searchDocuments(env.DB, tenantId, q, limit, offset);
      return Response.json({ results, query: q, limit, offset });
    } catch (err) {
      console.error('Search error:', err);
      return new Response('Internal Server Error', { status: 500 });
    }
  },
};
```

---

## Section 4: Rebuilding the FTS Index

If the FTS index drifts out of sync (e.g., after a bulk import), rebuild it with a single command.

```bash
# Rebuild the FTS5 index from the content table
wrangler d1 execute YOUR_DB_NAME \
  --command "INSERT INTO documents_fts(documents_fts) VALUES('rebuild');" \
  --remote

# Optimize the FTS index (merges segments, reduces query latency)
wrangler d1 execute YOUR_DB_NAME \
  --command "INSERT INTO documents_fts(documents_fts) VALUES('optimize');" \
  --remote
```

---

## Anti-patterns

- Using `LIKE '%term%'` instead of FTS5 — full table scans, no stemming, no ranking.
- Forgetting to sync the FTS index on UPDATE/DELETE — stale results that never clear.
- Using `MATCH ?` with raw user input without sanitising FTS5 operators — query syntax errors bubble to the user.
- Storing large binary blobs in `body` — FTS5 tokenises everything; keep body as plain text.
- Using `unicode61` tokenizer when only ASCII content is expected — Porter stemming only works through the `ascii` sub-tokenizer.

## Gotchas

- `bm25()` returns a negative value; negate it (`-bm25(...)`) for descending relevance sort.
- `content=` tables do not store their own copy of the data; deleting from the content table without updating the FTS index leaves ghost entries.
- `snippet()` column index is zero-based and refers to the FTS table column order, not the JOIN.
- FTS5 is available in D1 but not guaranteed in older local SQLite builds used by Wrangler; always test with `--remote`.
- Rebuilding a large FTS index can time out in a single Worker request; run it via `wrangler d1 execute` from CI.

## Verification

```bash
# Insert a test document and verify it is findable
wrangler d1 execute YOUR_DB_NAME \
  --command "INSERT INTO documents (id, tenant_id, title, body) \
             VALUES ('test-1', 'org_test', 'Running Tests', 'This document is about running automated tests.');" \
  --remote

wrangler d1 execute YOUR_DB_NAME \
  --command "INSERT INTO documents_fts (documents_fts) VALUES ('rebuild');" \
  --remote

# Search for stemmed form 'run' -- should match 'running'
wrangler d1 execute YOUR_DB_NAME \
  --command "SELECT d.id, d.title, -bm25(documents_fts) AS relevance \
             FROM documents_fts \
             JOIN documents d ON documents_fts.rowid = d.rowid \
             WHERE documents_fts MATCH 'run' \
             ORDER BY relevance DESC;" \
  --remote
```

## Related

- `documentation/docs/policies/database/d1-multi-tenant-row-isolation-pattern.md`
- `documentation/docs/policies/database/d1-trigger-audit-log-application-layer.md`

## Sources

- https://developers.cloudflare.com/d1/reference/full-text-search/
- https://www.sqlite.org/fts5.html
- https://www.sqlite.org/fts5.html#the_bm25_function
- https://www.sqlite.org/fts5.html#porter_tokenizer
