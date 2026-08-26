# D1: Cursor-based Pagination for Large Datasets

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
An API backed by D1 uses `LIMIT ? OFFSET ?` for pagination and experiences degrading response times as users navigate to later pages, or returns inconsistent results when rows are inserted between pages.

## Context
SQL `OFFSET`-based pagination performs a full index scan up to the offset position on every request — an O(n) operation that worsens with page depth. Cursor-based pagination anchors each page to a stable position in the dataset using an indexed column value from the last row of the previous page. D1's SQLite engine supports this pattern natively with a `WHERE id > ?` clause, returning consistent O(log n) queries regardless of page depth. This article covers keyset pagination for both monotonic integer IDs and composite keys (e.g. `(created_at, id)`).

## Schema Design for Cursor Pagination

Define a covering index that includes the sort column(s) plus the primary key. The primary key breaks ties when sort column values collide.

```sql
-- migration.sql
CREATE TABLE IF NOT EXISTS events (
  id          TEXT PRIMARY KEY,          -- ULID or UUID v7 (lexicographically sortable)
  tenant_id   TEXT NOT NULL,
  category    TEXT NOT NULL,
  created_at  INTEGER NOT NULL,          -- Unix ms
  payload     TEXT NOT NULL
);

-- Covering index for the cursor query
CREATE INDEX IF NOT EXISTS idx_events_tenant_cursor
  ON events (tenant_id, created_at DESC, id DESC);
```

## Forward Pagination with a Composite Cursor

Encode `(created_at, id)` as a single opaque cursor token so clients cannot tamper with individual components.

```typescript
// lib/cursor.ts
interface CursorPayload {
  createdAt: number;
  id: string;
}

export function encodeCursor(payload: CursorPayload): string {
  return btoa(JSON.stringify(payload));
}

export function decodeCursor(cursor: string): CursorPayload | null {
  try {
    return JSON.parse(atob(cursor)) as CursorPayload;
  } catch {
    return null;
  }
}
```

```typescript
// lib/paginate.ts
import { encodeCursor, decodeCursor } from "./cursor";

export interface Env {
  DB: D1Database;
}

export interface EventRow {
  id: string;
  tenant_id: string;
  category: string;
  created_at: number;
  payload: string;
}

export interface PageResult {
  items: EventRow[];
  nextCursor: string | null;
  hasMore: boolean;
}

export async function getEventsPage(
  db: D1Database,
  tenantId: string,
  limit: number,
  afterCursor?: string
): Promise<PageResult> {
  const safeLimit = Math.min(Math.max(1, limit), 200); // cap at 200
  // Fetch one extra row to detect hasMore
  const fetchLimit = safeLimit + 1;

  let stmt: D1PreparedStatement;

  if (afterCursor) {
    const pos = decodeCursor(afterCursor);
    if (!pos) throw new Error("Invalid cursor");

    // Rows strictly after the cursor position (descending by created_at)
    stmt = db
      .prepare(
        `SELECT id, tenant_id, category, created_at, payload
         FROM events
         WHERE tenant_id = ?
           AND (created_at < ? OR (created_at = ? AND id < ?))
         ORDER BY created_at DESC, id DESC
         LIMIT ?`
      )
      .bind(tenantId, pos.createdAt, pos.createdAt, pos.id, fetchLimit);
  } else {
    stmt = db
      .prepare(
        `SELECT id, tenant_id, category, created_at, payload
         FROM events
         WHERE tenant_id = ?
         ORDER BY created_at DESC, id DESC
         LIMIT ?`
      )
      .bind(tenantId, fetchLimit);
  }

  const { results } = await stmt.all<EventRow>();

  const hasMore = results.length > safeLimit;
  const items = hasMore ? results.slice(0, safeLimit) : results;

  const lastItem = items.at(-1);
  const nextCursor =
    hasMore && lastItem
      ? encodeCursor({ createdAt: lastItem.created_at, id: lastItem.id })
      : null;

  return { items, nextCursor, hasMore };
}
```

## Worker Endpoint: Exposing the Paginated API

```typescript
// worker.ts
export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/events") {
      return new Response("Not found", { status: 404 });
    }

    const tenantId = request.headers.get("X-Tenant-ID");
    if (!tenantId) return new Response("Missing X-Tenant-ID", { status: 400 });

    const cursor = url.searchParams.get("cursor") ?? undefined;
    const limit = parseInt(url.searchParams.get("limit") ?? "50", 10);

    try {
      const page = await getEventsPage(env.DB, tenantId, limit, cursor);
      return Response.json({
        data: page.items,
        pagination: {
          nextCursor: page.nextCursor,
          hasMore: page.hasMore,
          limit,
        },
      });
    } catch (err) {
      if (err instanceof Error && err.message === "Invalid cursor") {
        return new Response("Invalid cursor", { status: 400 });
      }
      throw err;
    }
  },
};

// Re-export for co-location in a single-file deployment
async function getEventsPage(
  db: D1Database,
  tenantId: string,
  limit: number,
  afterCursor?: string
): Promise<{ items: EventRow[]; nextCursor: string | null; hasMore: boolean }> {
  const safeLimit = Math.min(Math.max(1, limit), 200);
  const fetchLimit = safeLimit + 1;

  interface EventRow { id: string; tenant_id: string; category: string; created_at: number; payload: string; }

  let stmt: D1PreparedStatement;
  if (afterCursor) {
    const pos = decodeCursor(afterCursor);
    if (!pos) throw new Error("Invalid cursor");
    stmt = db
      .prepare(`SELECT id, tenant_id, category, created_at, payload FROM events WHERE tenant_id = ? AND (created_at < ? OR (created_at = ? AND id < ?)) ORDER BY created_at DESC, id DESC LIMIT ?`)
      .bind(tenantId, pos.createdAt, pos.createdAt, pos.id, fetchLimit);
  } else {
    stmt = db
      .prepare(`SELECT id, tenant_id, category, created_at, payload FROM events WHERE tenant_id = ? ORDER BY created_at DESC, id DESC LIMIT ?`)
      .bind(tenantId, fetchLimit);
  }

  const { results } = await stmt.all<EventRow>();
  const hasMore = results.length > safeLimit;
  const items = hasMore ? results.slice(0, safeLimit) : results;
  const last = items.at(-1);
  const nextCursor = hasMore && last ? encodeCursor({ createdAt: last.created_at, id: last.id }) : null;
  return { items, nextCursor, hasMore };
}

function encodeCursor(p: { createdAt: number; id: string }): string { return btoa(JSON.stringify(p)); }
function decodeCursor(s: string): { createdAt: number; id: string } | null { try { return JSON.parse(atob(s)); } catch { return null; } }
```

## Bi-directional Pagination with a Previous Cursor

For UI list views that support "previous page", store the first item's cursor in the response and reverse the sort on `prevCursor` requests.

```typescript
export interface BiDiPageResult extends PageResult {
  prevCursor: string | null;
}

export async function getEventsPageBiDi(
  db: D1Database,
  tenantId: string,
  limit: number,
  afterCursor?: string,
  beforeCursor?: string
): Promise<BiDiPageResult> {
  // "before" means newer items (ascending traversal, then reverse)
  if (beforeCursor) {
    const pos = decodeCursor(beforeCursor);
    if (!pos) throw new Error("Invalid cursor");

    const { results } = await db
      .prepare(
        `SELECT id, tenant_id, category, created_at, payload
         FROM events
         WHERE tenant_id = ?
           AND (created_at > ? OR (created_at = ? AND id > ?))
         ORDER BY created_at ASC, id ASC
         LIMIT ?`
      )
      .bind(tenantId, pos.createdAt, pos.createdAt, pos.id, limit + 1)
      .all<EventRow>();

    const hasMore = results.length > limit;
    const items = (hasMore ? results.slice(0, limit) : results).reverse();
    const first = items.at(0);
    const last = items.at(-1);

    return {
      items,
      nextCursor: last ? encodeCursor({ createdAt: last.created_at, id: last.id }) : null,
      prevCursor: first ? encodeCursor({ createdAt: first.created_at, id: first.id }) : null,
      hasMore,
    };
  }

  // Default: forward pagination
  const forward = await getEventsPage(db, tenantId, limit, afterCursor);
  const first = forward.items.at(0);
  return {
    ...forward,
    prevCursor: first ? encodeCursor({ createdAt: first.created_at, id: first.id }) : null,
  };
}
```

## Anti-patterns
- Using `OFFSET` for any page beyond the first — query time grows linearly with offset on large tables
- Exposing raw `(created_at, id)` values as cursor parameters — clients can manipulate the sort key; always base64-encode or sign the cursor
- Sorting by `created_at` alone without a tiebreaker — rows inserted at the same millisecond will produce non-deterministic page boundaries
- Not capping `limit` on the server side — a client requesting `limit=100000` can exhaust D1's row budget in a single call

## Gotchas
- D1 global read replicas may return slightly stale data; a newly inserted row may not appear until replication propagates — design cursors to be stable across replicas, not real-time
- `btoa()` / `atob()` are available in the Workers runtime but produce URL-unsafe characters (`+`, `/`, `=`); URL-encode the cursor or use `base64url` encoding before passing in query strings
- The composite `(tenant_id, created_at DESC, id DESC)` index is only used when the `ORDER BY` clause matches the index direction exactly
- D1 `stmt.all()` returns up to 10 000 rows per call; for batches beyond that, use `stmt.raw()` with streaming or break into multiple smaller queries

## Verification
1. Insert 1 000 rows for `tenant_id = "t1"` with distinct `created_at` values
2. Fetch page 1 (`limit=10`, no cursor) and confirm 10 rows returned with `hasMore: true`
3. Use `nextCursor` from page 1 to fetch page 2 and confirm no row overlap with page 1
4. Insert a new row between fetching page 1 and page 2 and confirm it does not appear in the middle of the sequence
5. Navigate to the last page and confirm `hasMore: false` and `nextCursor: null`

## Related
- `d1-best-practices.md`
- `d1-global-read-replicas.md`
- `d1-sessions-api.md`
- `d1-typescript-patterns.md`
- `workers-fetch-api-patterns.md`

## Sources
- https://developers.cloudflare.com/d1/worker-api/d1-database/
- https://developers.cloudflare.com/d1/best-practices/
- https://use-the-index-luke.com/no-offset
