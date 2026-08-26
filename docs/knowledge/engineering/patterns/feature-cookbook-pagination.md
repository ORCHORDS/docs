# feature-cookbook-pagination

**Issue:** Pagination — offset, cursor, keyset
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have 1M users. You return all of them. The
response is 50MB. The browser hangs. The team
complains. You wish you'd paginated.

## Root cause
**Without pagination, large responses are
unmanageable.** Use pagination.

**Source:** Stripe API design.

## Pagination strategies

### Offset pagination
- **How:** `LIMIT 20 OFFSET 0`
- **Pros:** Simple, can jump to any page
- **Cons:** Slow on large tables, inconsistent if data
  changes

```ts
const offset = parseInt(new URL(request.url).searchParams.get('offset') ?? '0');
const limit = parseInt(new URL(request.url).searchParams.get('limit') ?? '20');

const users = await env.DB!.prepare(
  `SELECT * FROM users LIMIT ? OFFSET ?`
).bind(limit, offset).all();

return Response.json({ data: users.results, offset, limit });
```

### Cursor pagination
- **How:** `WHERE id > ?` with the last seen ID
- **Pros:** Stable, fast
- **Cons:** No jump to page

```ts
const cursor = new URL(request.url).searchParams.get('cursor');
const limit = 20;

const users = cursor
  ? await env.DB!.prepare(`SELECT * FROM users WHERE id > ? LIMIT ?`).bind(cursor, limit).all()
  : await env.DB!.prepare(`SELECT * FROM users LIMIT ?`).bind(limit).all();

const nextCursor = users.results.length === limit ? users.results[users.results.length - 1].id : null;

return Response.json({ data: users.results, nextCursor });
```

### Keyset pagination
- **How:** `WHERE (createdAt, id) > (?, ?)`
- **Pros:** Stable, handles inserts
- **Cons:** Slightly more complex

```ts
const cursor = new URL(request.url).searchParams.get('cursor');
const limit = 20;

const { createdAt, id } = decodeCursor(cursor);

const users = await env.DB!.prepare(
  `SELECT * FROM users WHERE (createdAt, id) > (?, ?) ORDER BY createdAt, id LIMIT ?`
).bind(createdAt, id, limit).all();
```

For most apps, **cursor pagination** is the right
balance.

## The "cursor encoding" pattern

For cursors, base64-encode:
```ts
function encodeCursor(data: any): string {
  return Buffer.from(JSON.stringify(data)).toString('base64url');
}

function decodeCursor(cursor: string): any {
  return JSON.parse(Buffer.from(cursor, 'base64url').toString('utf-8'));
}

const cursor = encodeCursor({ id: 'u_123', createdAt: '2026-08-09T00:00:00Z' });
const decoded = decodeCursor(cursor);
```

The cursor is opaque.

## The "page size" pattern

For page size:
- **Default:** 20
- **Max:** 100
- **Min:** 1

```ts
const limit = Math.max(1, Math.min(100, parseInt(new URL(request.url).searchParams.get('limit') ?? '20')));
```

The limit is bounded.

## The "has more" pattern

For "has more":
```ts
const users = await env.DB!.prepare(
  `SELECT * FROM users LIMIT ?`
).bind(limit + 1).all();

const hasMore = users.results.length > limit;
const data = hasMore ? users.results.slice(0, limit) : users.results;
const nextCursor = hasMore ? data[data.length - 1].id : null;

return Response.json({ data, nextCursor, hasMore });
```

The has-more is computed.

## The "reverse pagination" pattern

For reverse (newest first):
```ts
const cursor = new URL(request.url).searchParams.get('cursor');
const limit = 20;

const users = cursor
  ? await env.DB!.prepare(`SELECT * FROM users WHERE id < ? ORDER BY id DESC LIMIT ?`).bind(cursor, limit).all()
  : await env.DB!.prepare(`SELECT * FROM users ORDER BY id DESC LIMIT ?`).bind(limit).all();
```

Reverse pagination is supported.

## The "total count" pattern

For total count:
```ts
const data = await env.DB!.prepare(`SELECT * FROM users LIMIT ? OFFSET ?`).bind(limit, offset).all();
const total = await env.DB!.prepare(`SELECT COUNT(*) as count FROM users`).first();

return Response.json({
  data: data.results,
  pagination: {
    total: total.count,
    limit,
    offset,
  },
});
```

The total is included.

**Caveat:** `COUNT(*)` is slow on large tables; consider
approximations.

## The "no pagination" anti-pattern

For no pagination:
```ts
// ❌ Bad: returns all
const users = await env.DB!.prepare(`SELECT * FROM users`).all();
return Response.json(users.results);
```

A 1M-row response is 50MB+.

## The "pagination" headers

For pagination, link headers:
```ts
const link = [
  `<${url}?cursor=${prevCursor}>; rel="prev"`,
  `<${url}?cursor=${nextCursor}>; rel="next"`,
].join(', ');

response.headers.set('Link', link);
```

The link headers are standard.

**Source:** RFC 5988 — Web Linking:
https://datatracker.ietf.org/doc/html/rfc5988

## The "pagination" anti-patterns

### 1. No pagination
- **Issue:** Huge response
- **Fix:** Use pagination

### 2. Offset on large tables
- **Issue:** Slow query
- **Fix:** Cursor pagination

### 3. Inconsistent cursor
- **Issue:** Cursor changes between requests
- **Fix:** Use a stable cursor

### 4. No max limit
- **Issue:** Client requests 1M rows
- **Fix:** Set a max

### 5. Cursor leaks data
- **Issue:** Cursor contains sensitive info
- **Fix:** Encode + sign

## Verification
- **Test:** Pagination works
- **Test:** Cursor is stable
- **Test:** Total count is correct
- **Live:** Pagination is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no pagination" anti-pattern.** Always
  paginate.
- **The "offset on large tables" anti-pattern.** Use
  cursor.
- **The "cursor leaks data" anti-pattern.** Encode +
  sign.

## Related
- `pagination-patterns.md`
- `api-design-best-practices.md`
- `feature-cookbook-api-design.md`
- `feature-cookbook-data-import.md`
- Stripe API: https://stripe.com/docs/api
- RFC 5988: https://datatracker.ietf.org/doc/html/rfc5988
