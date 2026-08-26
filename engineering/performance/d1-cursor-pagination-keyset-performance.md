# D1 Cursor-Based (Keyset) Pagination Performance

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A D1-backed API returns a list of records with `?page=N&limit=50` semantics. Page 1 is fast
(~2 ms), but page 100 takes 180 ms and page 500 times out. EXPLAIN QUERY PLAN confirms a
full-table scan on every request because every deep OFFSET forces D1 (SQLite) to read and
discard all preceding rows before returning the requested slice.

---

## Context

SQLite's `LIMIT x OFFSET y` clause is O(offset) — the engine physically steps over `y` rows
even when an index is used for ordering. For a 500 k-row table, `OFFSET 49950` reads ~50 k
rows just to throw them away. D1 runs in Cloudflare's edge isolates with a strict 30-second
wall-clock limit and a 50 ms CPU budget per request for non-paid plans; deep OFFSET pages
exhaust that budget quickly.

Keyset (cursor) pagination avoids the scan entirely: instead of "skip N rows", the query says
"give me rows where the sort key is greater than the last key the caller already saw". An index
on the sort key makes this O(log n + page_size), independent of how many prior pages exist.

---

## Index Design for Keyset Pagination

Pick a stable, unique sort key. A monotonically increasing `id` (D1 auto-increment integer or
a ULID stored as TEXT) is the simplest choice. For multi-column sort orders, create a
composite index.

```sql
-- Simple case: sort by insertion order
CREATE INDEX IF NOT EXISTS idx_posts_id ON posts (id);

-- Multi-column: sort by published_at DESC, then id DESC as tiebreaker
CREATE INDEX IF NOT EXISTS idx_posts_published ON posts (published_at DESC, id DESC);
```

The tiebreaker column (`id`) is critical — without it the cursor is ambiguous when two rows
share the same `published_at` value and rows may be skipped or duplicated across pages.

---

## TypeScript / Workers Implementation

```typescript
export interface Env {
  DB: D1Database;
}

interface Post {
  id: number;
  published_at: string;
  title: string;
}

interface CursorPayload {
  lastId: number;
  lastPublishedAt: string;
}

function encodeCursor(payload: CursorPayload): string {
  return btoa(JSON.stringify(payload));
}

function decodeCursor(token: string): CursorPayload {
  return JSON.parse(atob(token)) as CursorPayload;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const limit = Math.min(Number(url.searchParams.get('limit') ?? '50'), 200);
    const cursorParam = url.searchParams.get('cursor');

    let stmt: D1PreparedStatement;

    if (cursorParam) {
      const { lastId, lastPublishedAt } = decodeCursor(cursorParam);
      // Use the composite keyset: rows that come AFTER the cursor position
      stmt = env.DB.prepare(`
        SELECT id, published_at, title
        FROM posts
        WHERE (published_at, id) < (?, ?)
        ORDER BY published_at DESC, id DESC
        LIMIT ?
      `).bind(lastPublishedAt, lastId, limit);
    } else {
      stmt = env.DB.prepare(`
        SELECT id, published_at, title
        FROM posts
        ORDER BY published_at DESC, id DESC
        LIMIT ?
      `).bind(limit);
    }

    const { results } = await stmt.all<Post>();

    let nextCursor: string | null = null;
    if (results.length === limit) {
      const last = results[results.length - 1];
      nextCursor = encodeCursor({ lastId: last.id, lastPublishedAt: last.published_at });
    }

    return Response.json({ results, nextCursor });
  },
};
```

The `WHERE (published_at, id) < (?, ?)` row-value comparison is a single SQLite expression
that is satisfied by the composite index without a full scan. SQLite 3.15+ (which D1 uses)
supports row-value comparisons natively.

---

## Cursor Opaqueness and Security

Never expose raw column values as the cursor — clients could manipulate them to access
arbitrary rows. Base64-encode a JSON payload (shown above) or, for sensitive data, HMAC-sign it:

```typescript
async function signCursor(payload: CursorPayload, secret: string): Promise<string> {
  const data = JSON.stringify(payload);
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(data));
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig)));
  return btoa(JSON.stringify({ data, sig: sigB64 }));
}
```

---

## Handling Bi-directional Pagination

Some UIs need both "next page" and "previous page". Store a `direction` flag in the cursor
and reverse the inequality and ORDER BY direction for backward traversal:

```typescript
// Forward:  WHERE (published_at, id) < (?, ?) ORDER BY published_at DESC, id DESC
// Backward: WHERE (published_at, id) > (?, ?) ORDER BY published_at ASC,  id ASC
//           then reverse results array in application code
```

Bi-directional keyset pagination with a stable cursor is non-trivial; prefer unidirectional
(next-only) pagination unless the product genuinely requires "previous page" navigation.

---

## Anti-patterns

**OFFSET on large tables.** `LIMIT 50 OFFSET 49950` reads 50 000 rows to return 50.
Even with an index on the ORDER BY column, SQLite must traverse 50 000 index entries.

**Non-unique sort key without tiebreaker.** If `published_at` is not unique and the cursor
only stores `lastPublishedAt`, rows with the same timestamp will be silently skipped or
duplicated. Always include a unique tiebreaker (`id`).

**Mutable sort key.** If the sort column (e.g. `score`) can change between page requests,
rows will shift positions and the keyset cursor becomes invalid. Use immutable columns
(`created_at`, `id`) as the primary sort dimension whenever possible.

**Page-count metadata with OFFSET.** Callers sometimes ask for `SELECT COUNT(*) FROM posts`
to pre-compute total page count. On large tables this is a full scan. Return `hasMore` (a
boolean) instead and let the UI implement infinite scroll or "load more" semantics.

---

## Gotchas

- **Row-value syntax availability.** SQLite < 3.15 does not support `(a, b) < (?, ?)`. D1's
  SQLite version is recent enough, but always verify with `SELECT sqlite_version()`.

- **Cursor invalidation on deletes.** If a row pointed to by the cursor is deleted, the next
  page query still works correctly (it finds rows strictly after/before the stored key values).
  Inserts at positions before the cursor are also safe. Only reordering/mutation of the sort
  key can cause drift.

- **Changing `limit` mid-session.** The cursor encodes no `limit` information. Callers may
  change page size between requests; this is safe with keyset pagination.

- **Total row count.** Keyset pagination makes it impossible to know the total count cheaply.
  If the UI requires it, maintain a separate counter or use a periodic `COUNT(*)` query cached
  in KV.

---

## Verification

```sql
-- Confirm the query uses the index, not a full scan:
EXPLAIN QUERY PLAN
  SELECT id, published_at, title
  FROM posts
  WHERE (published_at, id) < ('2026-01-01T00:00:00Z', 99999)
  ORDER BY published_at DESC, id DESC
  LIMIT 50;

-- Expected output should show:
-- SEARCH posts USING INDEX idx_posts_published (published_at<?)
-- (not SCAN posts)
```

Measure latency across pages using Workers `performance.now()` and emit a custom Analytics
Engine event; confirm page-1 and page-500 timings are within 5 ms of each other.

---

## Related

- `d1-query-performance-explain-index.md`
- `d1-prepared-statement-reuse.md`
- `d1-covering-index-multi-column.md`
- `d1-pragma-optimize-query-planner.md`
- `kv-read-performance.md` (for caching cursor page results)

---

## Sources

- SQLite Row Value documentation: https://www.sqlite.org/rowvalue.html
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
- "Pagination done the right way" — Markus Winand, use-the-index-luke.com
- Cloudflare D1 limits: https://developers.cloudflare.com/d1/platform/limits/
