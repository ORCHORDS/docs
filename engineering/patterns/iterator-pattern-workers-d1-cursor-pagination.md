# Iterator Pattern: Workers D1 Cursor Pagination

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A social feed, moderation queue, or admin export endpoint needs to page through millions of D1 rows without holding a database cursor open between HTTP requests or issuing `OFFSET`-based queries that slow down quadratically as the offset grows. Callers — mobile clients, CLI scripts, background Workers — want a consistent `for-await` or `while` loop abstraction that hides pagination bookkeeping and handles end-of-stream detection cleanly.

## Context

Cloudflare D1 is a request-scoped database; there are no server-side cursors that persist between Worker invocations. Keyset (cursor) pagination is the only viable approach: each page carries a stable cursor value derived from the last row's indexed column(s), and the next query uses `WHERE sort_key < ?` (or `>` for ascending) with `LIMIT`. Wrapping this in an iterator object gives callers a standard `AsyncIterable<Page<T>>` surface without exposing the SQL cursor mechanics.

## Defining the Iterator Interface

The generic `PageIterator<T>` follows the `AsyncIterable` protocol so callers can use `for await`.

```typescript
// src/pagination/types.ts

export interface Page<T> {
  items: T[];
  nextCursor: string | null;
  hasMore: boolean;
}

export interface PageIterator<T> extends AsyncIterable<Page<T>> {
  [Symbol.asyncIterator](): AsyncIterator<Page<T>>;
  /** Convenience: collect all pages into a flat array (use with care on large sets) */
  toArray(): Promise<T[]>;
}
```

## Building the D1 Page Iterator

`createD1Iterator` closes over the D1 binding, the parameterised query, and pagination config. It returns a stateful iterator that tracks the current cursor.

```typescript
// src/pagination/d1-iterator.ts
import type { D1Database } from '@cloudflare/workers-types';
import type { Page, PageIterator } from './types';

interface D1IteratorOptions<T> {
  db: D1Database;
  /** SELECT query with TWO trailing bind slots: cursor placeholder and LIMIT */
  query: string;
  /** Static bind params that appear before the cursor param in the query */
  staticParams: unknown[];
  pageSize?: number;
  /** Extract the cursor value from the last row of a page */
  cursorOf: (row: T) => string;
  /** Initial cursor; null means start from the beginning */
  initialCursor?: string | null;
}

export function createD1Iterator<T>(
  opts: D1IteratorOptions<T>
): PageIterator<T> {
  const pageSize = opts.pageSize ?? 20;
  let cursor: string | null = opts.initialCursor ?? null;
  let done = false;

  async function fetchPage(): Promise<Page<T>> {
    // Query selects pageSize+1 rows to detect hasMore without a COUNT(*)
    const result = await opts.db
      .prepare(opts.query)
      .bind(...opts.staticParams, cursor, pageSize + 1)
      .all<T>();

    const rows = result.results;
    const hasMore = rows.length > pageSize;
    const items = hasMore ? rows.slice(0, pageSize) : rows;
    const nextCursor = hasMore ? opts.cursorOf(items[items.length - 1]) : null;

    cursor = nextCursor;
    if (!hasMore) done = true;

    return { items, nextCursor, hasMore };
  }

  return {
    [Symbol.asyncIterator]() {
      let first = true;
      return {
        async next(): Promise<IteratorResult<Page<T>>> {
          // Always yield the first page even if cursor is null (fresh start)
          if (!first && done) return { done: true, value: undefined as never };
          first = false;
          const page = await fetchPage();
          return { done: false, value: page };
        },
        async return() {
          done = true;
          return { done: true, value: undefined as never };
        },
      };
    },

    async toArray(): Promise<T[]> {
      const all: T[] = [];
      for await (const page of this) {
        all.push(...page.items);
      }
      return all;
    },
  };
}
```

## Feed Iterator — Concrete Usage

Wraps the feed query. Cursor is `created_at` ISO string — stable because posts are immutable once created and the column is indexed.

```typescript
// src/pagination/feed-iterator.ts
import type { D1Database } from '@cloudflare/workers-types';
import { createD1Iterator } from './d1-iterator';

export interface FeedRow {
  post_id: string;
  author_handle: string;
  body: string;
  created_at: string;
}

export function createFeedIterator(
  db: D1Database,
  viewerId: string,
  initialCursor?: string | null
) {
  return createD1Iterator<FeedRow>({
    db,
    // cursor slot: ? IS NULL OR created_at < ?   (same param bound twice)
    query: `
      SELECT p.id AS post_id, u.handle AS author_handle, p.body, p.created_at
      FROM posts p
      JOIN users u ON u.id = p.author_id
      WHERE p.author_id IN (
        SELECT followee_id FROM follows WHERE follower_id = ?
      )
      AND (? IS NULL OR p.created_at < ?)
      ORDER BY p.created_at DESC
      LIMIT ?
    `,
    // viewer id appears once; cursor appears twice (null check + comparison)
    staticParams: [viewerId],
    // Override fetchPage to bind cursor twice — compose a specialised query instead
    cursorOf: (row) => row.created_at,
    initialCursor,
    pageSize: 20,
  });
}
```

> Note: The query above binds cursor twice. The generic `createD1Iterator` binds `staticParams` then `cursor` once. For queries needing the cursor duplicated, override the binding in a specialised wrapper as shown below.

```typescript
// src/pagination/feed-iterator.ts (specialised, cursor used twice)
import type { D1Database } from '@cloudflare/workers-types';
import type { Page, PageIterator } from './types';
import type { FeedRow } from './feed-iterator';

export function createFeedIteratorV2(
  db: D1Database,
  viewerId: string,
  initialCursor?: string | null
): PageIterator<FeedRow> {
  let cursor: string | null = initialCursor ?? null;
  let done = false;
  const pageSize = 20;

  async function fetchPage(): Promise<Page<FeedRow>> {
    const rows = (await db.prepare(`
      SELECT p.id AS post_id, u.handle AS author_handle, p.body, p.created_at
      FROM posts p
      JOIN users u ON u.id = p.author_id
      WHERE p.author_id IN (SELECT followee_id FROM follows WHERE follower_id = ?)
        AND (? IS NULL OR p.created_at < ?)
      ORDER BY p.created_at DESC
      LIMIT ?
    `).bind(viewerId, cursor, cursor, pageSize + 1).all<FeedRow>()).results;

    const hasMore = rows.length > pageSize;
    const items = hasMore ? rows.slice(0, pageSize) : rows;
    const nextCursor = items.at(-1)?.created_at ?? null;
    cursor = hasMore ? nextCursor : null;
    if (!hasMore) done = true;
    return { items, nextCursor: hasMore ? nextCursor : null, hasMore };
  }

  return {
    [Symbol.asyncIterator]() {
      let first = true;
      return {
        async next() {
          if (!first && done) return { done: true, value: undefined as never };
          first = false;
          return { done: false, value: await fetchPage() };
        },
        async return() { done = true; return { done: true, value: undefined as never }; },
      };
    },
    async toArray() {
      const all: FeedRow[] = [];
      for await (const page of this) all.push(...page.items);
      return all;
    },
  };
}
```

## HTTP Handler — Exposing Pages over REST

```typescript
// src/handlers/feed.ts
import type { Env } from '../env';
import { createFeedIteratorV2 } from '../pagination/feed-iterator';

export async function handleFeed(req: Request, env: Env): Promise<Response> {
  const url = new URL(req.url);
  const cursor = url.searchParams.get('cursor') ?? null;
  const userId = req.headers.get('x-user-id')!;

  const iter = createFeedIteratorV2(env.DB, userId, cursor);
  const iterResult = iter[Symbol.asyncIterator]();
  const { value: page } = await iterResult.next();
  await iterResult.return?.(); // close iterator after one page

  return Response.json({
    posts: page.items,
    nextCursor: page.nextCursor,
    hasMore: page.hasMore,
  });
}
```

## Background Export — Consuming All Pages

A Cron Worker or Queue consumer can exhaust all pages without modifying the iterator API.

```typescript
// src/consumers/export-consumer.ts
import type { Env } from '../env';
import { createFeedIteratorV2 } from '../pagination/feed-iterator';

export async function exportUserFeed(userId: string, env: Env): Promise<void> {
  const iter = createFeedIteratorV2(env.DB, userId);
  let pageNum = 0;

  for await (const page of iter) {
    pageNum++;
    await env.EXPORT_BUCKET.put(
      `exports/${userId}/page-${String(pageNum).padStart(4, '0')}.json`,
      JSON.stringify(page.items)
    );
    if (!page.hasMore) break;
  }
}
```

## Anti-patterns

- Using `OFFSET n` pagination — O(n) query cost; breaks when rows are inserted/deleted mid-iteration
- Using auto-increment integer IDs as cursors without a tie-breaker column — ties at the same millisecond cause rows to be skipped
- Holding the iterator open across HTTP requests as a class instance — Workers are stateless; reconstruct the iterator from the cursor token on each request
- Returning `COUNT(*)` on every page to calculate total pages — expensive on D1; use `hasMore` derived from `LIMIT+1` instead
- Exposing the raw SQL cursor value in the API — encode it (`btoa`) so it's opaque and you can change the column without breaking clients

## Gotchas

- D1 `? IS NULL OR col < ?` requires the same parameter bound twice; `.bind(cursor, cursor)` is correct
- `ORDER BY created_at DESC` combined with `WHERE created_at < ?` is only stable if `created_at` is unique per row; add a secondary sort by `id` for ties: `ORDER BY created_at DESC, id DESC` with `WHERE (created_at, id) < (?, ?)`
- The `+1` trick to detect `hasMore` means callers should never trust `items.length === pageSize` as a `hasMore` signal
- In tests, mock `db.prepare(...).bind(...).all()` to return arrays of length `pageSize + 1` to verify the `hasMore` detection
- `for await` catches iterator `return()` on `break` — ensure your iterator's `return` method marks `done = true` to prevent phantom fetches

## Verification

```bash
# Page 1 — no cursor
curl 'https://example.com/feed' -H 'x-user-id: u1' | jq '{count: (.posts | length), nextCursor}'

# Page 2 — use cursor from page 1
CURSOR=$(curl -s 'https://example.com/feed' -H 'x-user-id: u1' | jq -r .nextCursor)
curl "https://example.com/feed?cursor=${CURSOR}" -H 'x-user-id: u1' | jq .posts[0].created_at
# Should be strictly less than the first item on page 1

# Confirm last page has hasMore: false
# (iterate until nextCursor is null in a loop test)
```

## Related

- `documentation/categories/patterns/pagination-cursor-pattern.md`
- `documentation/categories/patterns/pagination-patterns.md`
- `documentation/categories/patterns/cqrs-pattern-workers-d1-kv-read-write-split.md`
- `documentation/categories/patterns/materialized-view-d1-workers.md`
- `documentation/categories/patterns/feature-cookbook-pagination.md`

## Sources

- https://developers.cloudflare.com/d1/worker-api/d1-database/#prepare
- https://developers.cloudflare.com/d1/best-practices/
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Iteration_protocols#the_async_iterator_and_async_iterable_protocols
- https://refactoring.guru/design-patterns/iterator
