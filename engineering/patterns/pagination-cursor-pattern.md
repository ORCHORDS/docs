# pagination-cursor-pattern

**Issue:** Offset pagination breaks under concurrent inserts — use cursor-based pagination
**Date:** 2026-08-11
**Status:** documented

## Problem with offset pagination

```sql
SELECT * FROM controls LIMIT 50 OFFSET 100
```

If rows are inserted while a client pages through the list, rows shift. The client
sees duplicates or skips rows. Offset pagination is broken for any live dataset.

## Cursor-based pagination

A cursor encodes the position of the last seen row. The next page query asks for
rows strictly after that position.

### Cursor encoding

Use a tuple of (created_at, id) — stable sort order + tie-breaker:

```typescript
function encodeCursor(row: { created_at: number; id: string }): string {
  return btoa(JSON.stringify({ ts: row.created_at, id: row.id }));
}

function decodeCursor(cursor: string): { ts: number; id: string } {
  try {
    return JSON.parse(atob(cursor));
  } catch {
    throw new Error('invalid_cursor');
  }
}
```

### Query

```typescript
const url = new URL(request.url);
const cursorRaw = url.searchParams.get('cursor');
const limit = Math.min(Number(url.searchParams.get('limit') ?? 50), 200);

let sql = `SELECT * FROM controls WHERE tenant_id = ?`;
const params: (string | number)[] = [ctx.tenant.id];

if (cursorRaw) {
  let cur: { ts: number; id: string };
  try {
    cur = decodeCursor(cursorRaw);
  } catch {
    return jsonError(400, 'invalid_cursor', 'Invalid pagination cursor', ctx.request_id);
  }
  // Composite cursor: (created_at DESC, id DESC)
  // "before" means created_at < cursor.ts OR (created_at = cursor.ts AND id < cursor.id)
  sql += ` AND (created_at < ? OR (created_at = ? AND id < ?))`;
  params.push(cur.ts, cur.ts, cur.id);
}

sql += ` ORDER BY created_at DESC, id DESC LIMIT ?`;
params.push(limit + 1);  // fetch one extra to detect next page

const { results } = await env.DB!.prepare(sql).bind(...params).all<Control>();

const hasMore = results.length > limit;
const items = hasMore ? results.slice(0, limit) : results;
const nextCursor = hasMore ? encodeCursor(items[items.length - 1]) : null;

return jsonOk({
  controls: items,
  count: items.length,
  cursor: nextCursor,
}, ctx.request_id);
```

### Response shape

```json
{
  "controls": [...],
  "count": 50,
  "cursor": "eyJ0cyI6MTY5..."
}
```

Client passes `?cursor=eyJ0cyI6MTY5...` for the next page. `cursor: null` means last page.

## Ascending sort variant

For feeds sorted oldest-first (e.g. audit log replay):

```typescript
sql += ` AND (created_at > ? OR (created_at = ? AND id > ?))`;
// ...
sql += ` ORDER BY created_at ASC, id ASC LIMIT ?`;
```

## Filter + cursor

When the client filters by status, include it in both pages:

```typescript
if (status) {
  sql += ` AND status = ?`;
  params.push(status);
}
// Cursor clause comes AFTER filter clauses
if (cursorRaw) {
  sql += ` AND (created_at < ? OR (created_at = ? AND id < ?))`;
  ...
}
```

**Important**: The cursor encodes position only, NOT the filter. The filter must be
re-applied from the query string on every page request.

## Gotchas

- **`limit + 1` fetch**: Fetching one extra is how you know if there's a next page without a COUNT(*) query. Always slice before returning.
- **Cursor leaks last ID**: The cursor contains the last row's `id` and `created_at`. These are opaque to the client but visible if decoded. Don't include sensitive fields in the cursor.
- **Composite tie-breaker is mandatory**: `ORDER BY created_at DESC LIMIT 50` — if two rows have the same `created_at`, the sort is nondeterministic. Always add `id` as a tie-breaker.
- **Index must match sort order**: A query with `ORDER BY created_at DESC, id DESC` needs an index on `(tenant_id, created_at DESC, id DESC)`. Without it, D1 does a full-table scan.
- **Don't use offset for admin UIs**: Even in admin panels, cursor pagination is better. Offset works for small fixed-size datasets only.

## Index for cursor pagination

```sql
CREATE INDEX controls_cursor_idx ON controls(tenant_id, created_at DESC, id DESC)
  WHERE deleted_at IS NULL;
```

## Related

- `d1-typescript-patterns.md`
- `multi-tenant-data-isolation.md`
- `typescript-route-handler.md`
- `error-codes-and-responses.md`
- `api-design-best-practices.md`
