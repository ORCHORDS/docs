# pagination-patterns

**Issue:** Offset vs cursor pagination, plus edge cases
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your API has `?page=1&size=20`. A user has 1M records. They
ask for page 50000. The query is `LIMIT 20 OFFSET 999980`.
The DB scans 1M rows to return 20. It takes 30 seconds. The
user is upset.

## Root cause
**Offset pagination is O(N).** Each request scans all the
skipped rows. For deep pagination, it's slow.

**Source:** Various pagination guides.

## The 3 main pagination patterns

### 1. Offset pagination (`?page=1&size=20`)
- **What:** Skip N rows, return M
- **Pros:** Simple; supports "jump to page 50"
- **Cons:** O(N) for deep pages; inconsistent under
  concurrent writes

```ts
const page = parseInt(searchParams.get('page') ?? '1');
const size = Math.min(parseInt(searchParams.get('size') ?? '20'), 100);
const offset = (page - 1) * size;

const rows = await env.DB!.prepare(
  `SELECT * FROM users WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?`
).bind(tenantId, size, offset).all<User>();
```

### 2. Cursor pagination (`?cursor=abc&size=20`)
- **What:** Return rows after a specific cursor (the last
  row's ID or timestamp)
- **Pros:** O(1) regardless of depth; consistent under
  concurrent writes
- **Cons:** No "jump to page 50"

```ts
const cursor = searchParams.get('cursor');  // Last row's ID
const size = Math.min(parseInt(searchParams.get('size') ?? '20'), 100);

let rows;
if (cursor) {
  rows = await env.DB!.prepare(
    `SELECT * FROM users WHERE tenant_id = ? AND id < ? ORDER BY id DESC LIMIT ?`
  ).bind(tenantId, cursor, size).all<User>();
} else {
  rows = await env.DB!.prepare(
    `SELECT * FROM users WHERE tenant_id = ? ORDER BY id DESC LIMIT ?`
  ).bind(tenantId, size).all<User>();
}

const nextCursor = rows.results.length === size ? rows.results[rows.results.length - 1].id : null;
return jsonOk({ data: rows.results, nextCursor });
```

✅ **O(1)** — fast for any depth
✅ **Consistent** — even if rows are added/removed
❌ **No random access** — can't jump to a specific page

### 3. Keyset pagination
- **What:** Similar to cursor but uses an indexed column
  (e.g. `created_at`)
- **Pros:** Works even if the primary key changes
- **Cons:** Requires a stable, indexed column

```ts
const after = searchParams.get('after');  // "2026-08-09T00:00:00Z"
const size = Math.min(parseInt(searchParams.get('size') ?? '20'), 100);

const rows = await env.DB!.prepare(
  `SELECT * FROM users WHERE tenant_id = ? AND created_at < ? ORDER BY created_at DESC LIMIT ?`
).bind(tenantId, after, size).all<User>();
```

## The "decision matrix"

| Use case | Use |
|---|---|
| Admin panel (need to jump to page 50) | Offset |
| Public API (mobile, web) | Cursor |
| Time-series data (logs, events) | Keyset |
| Search results (e.g. Algolia) | Offset (built-in) |
| Infinite scroll (web, mobile) | Cursor |

For most APIs, **cursor** is the right default.

## The "total count" anti-pattern

Many APIs return a `totalCount` field:
```json
{
  "data": [...],
  "totalCount": 1000000,
  "page": 1,
  "size": 20
}
```

For large tables, this is **expensive** (the DB scans the
whole table to count). For a cursor-paginated API, the
`totalCount` is misleading (it changes as data is added).

**Better:** Return `hasMore: true/false` or `nextCursor`:
```json
{
  "data": [...],
  "nextCursor": "u_999",
  "hasMore": true
}
```

The client uses `hasMore` to show "load more" or hide it.

## The "consistent ordering" requirement

For cursor pagination, the ORDER BY must be stable:
```ts
// ❌ Bad: non-deterministic order
ORDER BY display_name

// ✅ Good: stable order
ORDER BY display_name, id
```

A non-deterministic order can return the same row twice
(or miss a row) across pages.

## The "compound cursor" pattern

For ordering by multiple columns:
```ts
ORDER BY created_at DESC, id DESC
```

The cursor must encode both:
```ts
const cursor = Buffer.from(JSON.stringify({ createdAt: '2026-08-09T00:00:00Z', id: 'u_123' })).toString('base64');

const decoded = JSON.parse(Buffer.from(cursor, 'base64').toString());
// { createdAt: '2026-08-09T00:00:00Z', id: 'u_123' }
```

Encode the cursor as base64 to make it opaque to the client.

## The "pagination + filtering" pattern

Combine with filters:
```ts
const filters = ['tenant_id = ?'];
const params = [tenantId];

if (searchParams.get('status')) {
  filters.push('status = ?');
  params.push(searchParams.get('status'));
}
if (cursor) {
  filters.push('id < ?');
  params.push(cursor);
}

const query = `SELECT * FROM users WHERE ${filters.join(' AND ')} ORDER BY id DESC LIMIT ?`;
params.push(size);

const rows = await env.DB!.prepare(query).bind(...params).all<User>();
```

## The "pagination + sorting" pattern

For sortable columns, use a `sort` parameter:
```ts
const sort = searchParams.get('sort') ?? 'created_at';
const order = searchParams.get('order') === 'asc' ? 'ASC' : 'DESC';

const validSorts = ['created_at', 'display_name', 'email'];
if (!validSorts.includes(sort)) {
  return jsonError('Invalid sort column', 400);
}

const query = `SELECT * FROM users WHERE tenant_id = ? ORDER BY ${sort} ${order} LIMIT ?`;
```

⚠️ **SQL injection risk:** The `sort` column must be validated
against a whitelist. Never interpolate user input.

## The "pagination at scale" pattern

For very large datasets (1B+ rows), use:
- **Search engine:** Algolia, Elasticsearch
- **Data warehouse:** BigQuery, Snowflake
- **Caching layer:** Materialized view + cache

D1 (SQLite) is fine up to ~100M rows. Beyond that, the
query planner may struggle.

## Verification
- **Test:** `test/pagination.test.ts > cursor pagination is
  consistent across concurrent inserts` — passes
- **Test:** `test/pagination.test.ts > deep cursor
  pagination is fast` (< 100ms) — passes
- **Live:** Pagination latency is monitored

## Gotchas
- **The cursor must be opaque to the client.** Don't use
  the row's primary key; use a base64-encoded payload.
- **The "OFFSET 0" is fine.** "OFFSET 1000000" is slow.
  Cursor pagination avoids this.
- **The "total count" is expensive** for large tables. Use
  `hasMore` instead.
- **The "ORDER BY" must use an index.** Without an index, the
  query is a full table scan.
- **The "infinite scroll" UX** can have bugs. A user scrolls
  to page 100, refreshes, and loses their place. Cursor
  pagination + a "back" button helps.
- **The "stable order" is essential.** Without it, the user
  sees duplicates or skips rows.

## Related
- `api-design-anti-patterns.md`
- `cache-strategies.md` (paginated results can be cached)
- `api-versioning.md`
- Algolia: https://www.algolia.com/doc/api-reference/api-parameters/pagination/
- Stripe cursor pagination: https://stripe.com/docs/api/pagination
