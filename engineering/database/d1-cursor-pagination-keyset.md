# Keyset (Cursor) Pagination with Cloudflare D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your API returns paginated lists of records that grow beyond tens of thousands of rows. `OFFSET`-based pagination becomes slow because D1 must scan and discard all preceding rows on every page request. Cursor-based (keyset) pagination solves this by jumping directly to the right position using indexed column values.

---

## Context

D1 is built on SQLite, which executes `OFFSET N` by reading and discarding the first N rows — an O(N) operation that degrades linearly as users page deeper. Keyset pagination replaces the offset with a `WHERE` clause that filters rows using the last-seen values of the sort columns, making every page fetch O(log N) when the columns are indexed. The cursor is encoded as base64 JSON and passed back in the API response, keeping the URL clean and the client stateless. Zod validates the decoded cursor before it touches SQL to prevent injection or corrupt-state errors.

---

## Schema — Table & Index Setup

```sql
CREATE TABLE IF NOT EXISTS posts (
  id          TEXT        PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  title       TEXT        NOT NULL,
  body        TEXT        NOT NULL,
  author_id   TEXT        NOT NULL REFERENCES users(id),
  created_at  DATETIME    NOT NULL DEFAULT (datetime('now')),
  updated_at  DATETIME    NOT NULL DEFAULT (datetime('now'))
);

-- Composite index that matches the ORDER BY clause exactly.
-- D1/SQLite will use this for both the sort and the keyset WHERE filter.
CREATE INDEX IF NOT EXISTS idx_posts_created_at_id
  ON posts (created_at DESC, id DESC);
```

---

## Implementation

```typescript
// src/lib/pagination.ts
import { z } from 'zod';

/** Shape stored inside the opaque cursor string. */
const CursorSchema = z.object({
  created_at: z.string().datetime(),
  id: z.string().min(1),
});
export type Cursor = z.infer<typeof CursorSchema>;

/** Encode a cursor to a URL-safe base64 string. */
export function encodeCursor(cursor: Cursor): string {
  return btoa(JSON.stringify(cursor))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

/** Decode and validate a cursor. Throws ZodError on invalid input. */
export function decodeCursor(raw: string): Cursor {
  const json = atob(raw.replace(/-/g, '+').replace(/_/g, '/'));
  return CursorSchema.parse(JSON.parse(json));
}
```

```typescript
// src/routes/posts.ts
import { Hono } from 'hono';
import { z } from 'zod';
import { encodeCursor, decodeCursor } from '../lib/pagination';

type Env = { Bindings: { DB: D1Database } };

const app = new Hono<Env>();

const QuerySchema = z.object({
  limit: z.coerce.number().int().min(1).max(100).default(20),
  cursor: z.string().optional(),
});

app.get('/posts', async (c) => {
  const { limit, cursor } = QuerySchema.parse(
    Object.fromEntries(new URL(c.req.url).searchParams)
  );

  let stmt: D1PreparedStatement;

  if (cursor) {
    // Decode and validate the cursor before touching SQL.
    const { created_at, id } = decodeCursor(cursor);

    // Row-value comparison: the composite (created_at, id) tuple must be
    // strictly less than the last-seen tuple when ordering DESC.
    stmt = c.env.DB.prepare(`
      SELECT id, title, author_id, created_at
      FROM   posts
      WHERE  (created_at, id) < (?, ?)
      ORDER  BY created_at DESC, id DESC
      LIMIT  ?
    `).bind(created_at, id, limit + 1);  // fetch one extra to detect next page
  } else {
    stmt = c.env.DB.prepare(`
      SELECT id, title, author_id, created_at
      FROM   posts
      ORDER  BY created_at DESC, id DESC
      LIMIT  ?
    `).bind(limit + 1);
  }

  const { results } = await stmt.all<{
    id: string;
    title: string;
    author_id: string;
    created_at: string;
  }>();

  const hasNextPage = results.length > limit;
  const items = hasNextPage ? results.slice(0, limit) : results;

  const nextCursor =
    hasNextPage
      ? encodeCursor({
          created_at: items[items.length - 1].created_at,
          id: items[items.length - 1].id,
        })
      : null;

  return c.json({
    items,
    pagination: {
      next_cursor: nextCursor,
      has_next_page: hasNextPage,
      limit,
    },
  });
});

export default app;
```

---

## Testing / Verification

```typescript
// src/routes/posts.test.ts
import { describe, it, expect, beforeAll } from 'vitest';
import { unstable_dev } from 'wrangler';
import type { UnstableDevWorker } from 'wrangler';

describe('Keyset pagination', () => {
  let worker: UnstableDevWorker;

  beforeAll(async () => {
    worker = await unstable_dev('src/index.ts', { experimental: { disableExperimentalWarning: true } });
  });

  afterAll(async () => { await worker.stop(); });

  it('returns first page without cursor', async () => {
    const res = await worker.fetch('/posts?limit=5');
    const body = await res.json<any>();
    expect(res.status).toBe(200);
    expect(body.items).toHaveLength(5);
    expect(body.pagination.next_cursor).toBeTruthy();
  });

  it('second page does not overlap first page', async () => {
    const first = await (await worker.fetch('/posts?limit=5')).json<any>();
    const secondRes = await worker.fetch(`/posts?limit=5&cursor=${first.pagination.next_cursor}`);
    const second = await secondRes.json<any>();
    const firstIds = new Set(first.items.map((r: any) => r.id));
    for (const item of second.items) {
      expect(firstIds.has(item.id)).toBe(false);
    }
  });

  it('rejects a tampered cursor with 400', async () => {
    const res = await worker.fetch('/posts?cursor=notbase64!!!');
    expect(res.status).toBe(400);
  });
});
```

---

## Anti-patterns

- **Using OFFSET for pagination** — O(N) scan cost; at 100 k rows page 500 is visibly slow and ties up D1 CPU time.
- **Sorting only by `id`** — natural UUIDs are not time-ordered; without `created_at` as the leading sort key, pages appear in random order.
- **Passing raw cursor values into SQL via string interpolation** — always bind via `?` parameters; decodeCursor + Zod ensures type safety before binding.
- **Omitting the +1 fetch trick** — without fetching `limit + 1` rows you cannot detect whether a next page exists without an extra `COUNT` query.

---

## Gotchas

- Row-value syntax `WHERE (a, b) < (?, ?)` is supported in SQLite 3.15+ (D1 is ≥ 3.39), but double-check D1 changelog if behaviour seems off.
- If two rows share the same `created_at` down to the second, the secondary sort on `id` (UUID) is the tiebreaker — the composite index must include both columns.
- URL-safe base64 replaces `+` with `-` and `/` with `_`; forgetting this causes `atob` to throw on the server side.
- Cursors encode a point-in-time snapshot position, not an offset. Newly inserted rows that sort before the cursor will not appear on earlier pages, which is generally the desired behaviour for feeds.

---

## Verification

```bash
# Confirm the composite index is being used (look for "SEARCH posts USING INDEX idx_posts_created_at_id")
wrangler d1 execute orchords-db --command "
  EXPLAIN QUERY PLAN
  SELECT id, title, created_at
  FROM   posts
  WHERE  (created_at, id) < ('2026-08-01T00:00:00Z', 'abc123')
  ORDER  BY created_at DESC, id DESC
  LIMIT  20;
"

# Seed test data and time first vs. deep page
wrangler d1 execute orchords-db --command "SELECT COUNT(*) FROM posts;"
```

---

## Related

- `d1-soft-delete-restore-pattern.md`
- `d1-json-column-queries.md`

---

## Sources

- Cloudflare D1 Docs — https://developers.cloudflare.com/d1/
- SQLite Row Value Expressions — https://www.sqlite.org/rowvalue.html
- Zod Schema Validation — https://zod.dev
