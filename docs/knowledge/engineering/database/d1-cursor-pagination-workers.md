# Cursor-Based Pagination in D1 (Cloudflare Workers)

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A list endpoint returns thousands of rows. OFFSET-based pagination (`LIMIT 20 OFFSET 10000`) becomes progressively slower because SQLite must read and discard the first 10 000 rows to compute the offset. You need a pagination strategy that stays O(log n) as the table grows.

## Context

Keyset (cursor) pagination works by remembering the last row seen and asking for rows that come after it, using an indexed inequality in the WHERE clause instead of OFFSET. D1's edge-local SQLite makes this especially worthwhile: a full-scan OFFSET query on a large table will hit D1's CPU time limits before a keyset query would. The approach requires a stable sort order and a unique tiebreaker column (usually `id`).

---

## The Problem with OFFSET

```sql
-- This looks harmless for page 1...
SELECT * FROM items ORDER BY created_at DESC LIMIT 20 OFFSET 0;

-- ...but page 501 silently reads 10 020 rows and discards 10 000:
SELECT * FROM items ORDER BY created_at DESC LIMIT 20 OFFSET 10000;
-- SQLite has no way to skip rows without reading them first.
```

## Keyset Pagination Implementation

```typescript
// src/db/pagination.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface PageCursor {
  created_at: string;
  id: string;
}

export interface PageResult<T> {
  items: T[];
  nextCursor: string | null; // base64-encoded JSON cursor, or null on last page
}

/**
 * Encode a cursor as an opaque base64 string safe for use in URLs and headers.
 * Clients treat this as an opaque token — never parse it on the client.
 */
function encodeCursor(cursor: PageCursor): string {
  return btoa(JSON.stringify(cursor));
}

function decodeCursor(token: string): PageCursor {
  try {
    return JSON.parse(atob(token)) as PageCursor;
  } catch {
    throw new Error('Invalid pagination cursor');
  }
}

export interface Item {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
}

/**
 * List items for a user, newest first, using keyset pagination.
 *
 * @param db      - D1 database binding
 * @param userId  - filter to this user's items
 * @param limit   - page size (max enforced by caller)
 * @param cursor  - opaque cursor from a previous response, or null for first page
 */
export async function listItemsPaged(
  db: D1Database,
  userId: string,
  limit: number,
  cursor: string | null,
): Promise<PageResult<Item>> {
  const pageSize = Math.min(limit, 100); // hard cap

  let rows: Item[];

  if (cursor === null) {
    // First page — no lower bound
    const { results } = await db
      .prepare(
        `SELECT id, user_id, title, created_at
         FROM items
         WHERE user_id = ? AND deleted_at IS NULL
         ORDER BY created_at DESC, id DESC
         LIMIT ?`,
      )
      .bind(userId, pageSize + 1) // fetch one extra to detect next page
      .all<Item>();
    rows = results;
  } else {
    const { created_at, id } = decodeCursor(cursor);

    // Subsequent pages — keyset filter replaces OFFSET
    // The composite condition (created_at, id) < (?, ?) respects
    // the sort order: rows with an earlier timestamp come after,
    // and for equal timestamps the lower id comes after.
    const { results } = await db
      .prepare(
        `SELECT id, user_id, title, created_at
         FROM items
         WHERE user_id = ?
           AND deleted_at IS NULL
           AND (created_at < ? OR (created_at = ? AND id < ?))
         ORDER BY created_at DESC, id DESC
         LIMIT ?`,
      )
      .bind(userId, created_at, created_at, id, pageSize + 1)
      .all<Item>();
    rows = results;
  }

  // If we got pageSize + 1 rows, there is a next page.
  const hasMore = rows.length > pageSize;
  if (hasMore) rows.pop(); // remove the sentinel row

  const nextCursor =
    hasMore && rows.length > 0
      ? encodeCursor({
          created_at: rows[rows.length - 1].created_at,
          id: rows[rows.length - 1].id,
        })
      : null;

  return { items: rows, nextCursor };
}
```

## HTTP Handler

```typescript
// src/handlers/items.ts
import { listItemsPaged } from '../db/pagination';

export async function handleListItems(
  request: Request,
  env: Env,
): Promise<Response> {
  const url = new URL(request.url);
  const userId = url.searchParams.get('user_id') ?? '';
  const cursorParam = url.searchParams.get('cursor') ?? null;
  const limit = parseInt(url.searchParams.get('limit') ?? '20', 10);

  const page = await listItemsPaged(env.DB, userId, limit, cursorParam);

  return Response.json({
    data: page.items,
    pagination: {
      next_cursor: page.nextCursor,
      has_more: page.nextCursor !== null,
    },
  });
}
```

Client usage:

```
GET /items?user_id=abc&limit=20
→ { data: [...20 items], pagination: { next_cursor: "eyJjcmVhdGVkX2F0...", has_more: true } }

GET /items?user_id=abc&limit=20&cursor=eyJjcmVhdGVkX2F0...
→ { data: [...20 more items], pagination: { next_cursor: null, has_more: false } }
```

## Required Index

```sql
-- The composite index must match the ORDER BY exactly.
-- Without this, SQLite sorts in memory for every page request.
CREATE INDEX idx_items_user_cursor
  ON items (user_id, created_at DESC, id DESC)
  WHERE deleted_at IS NULL;
```

## Anti-patterns

- **Mixing OFFSET and cursor pagination in the same endpoint.** They have incompatible consistency guarantees. Pick one and enforce it at the API boundary.
- **Encoding the cursor as a plain readable string.** Clients will parse and manipulate it. Use base64 to signal opacity, and validate the shape server-side before binding to SQL.
- **Using a single-column cursor on a non-unique column.** If two rows share the same `created_at`, a cursor on that timestamp alone will skip or duplicate rows. Always include `id` as a tiebreaker.
- **Allowing arbitrary `limit` values.** Cap the page size server-side (e.g. 100) to prevent a client from requesting a full-table dump in one call.

## Gotchas

- The `pageSize + 1` trick is the simplest way to detect a next page without an extra `COUNT(*)` query. Pop the sentinel before returning.
- `btoa` / `atob` are available as globals in the Workers runtime. No import needed.
- Keyset pagination does not support random page jumps ("go to page 42"). If your UI needs page numbers, keyset pagination is not the right tool — accept the OFFSET cost or pre-materialise page boundaries.
- If rows are inserted between page fetches, the cursor remains consistent — new rows appear on subsequent calls without pushing existing rows to a different page, which is the main advantage over OFFSET.

## Verification

```sql
-- Simulate page 1 (no cursor)
SELECT id, created_at FROM items
WHERE user_id = 'test-user' AND deleted_at IS NULL
ORDER BY created_at DESC, id DESC
LIMIT 21;

-- Simulate page 2 using the last row from page 1
SELECT id, created_at FROM items
WHERE user_id = 'test-user'
  AND deleted_at IS NULL
  AND (created_at < '2026-08-01T12:00:00' OR (created_at = '2026-08-01T12:00:00' AND id < 'last-id-from-page-1'))
ORDER BY created_at DESC, id DESC
LIMIT 21;

-- Confirm index is used
EXPLAIN QUERY PLAN
SELECT id FROM items
WHERE user_id = 'x' AND deleted_at IS NULL
ORDER BY created_at DESC, id DESC LIMIT 21;
```

## Related

- `d1-soft-delete-pattern-workers.md` — the `deleted_at IS NULL` filter used in these queries
- `d1-json-column-query-workers.md` — filtering on JSON fields in paginated results
- `d1-hyperdrive-connection-comparison-workers.md` — when to move off D1 as row counts grow

## Sources

- https://developers.cloudflare.com/d1/
- https://use-the-index-luke.com/no-offset
- https://www.sqlite.org/optoverview.html
