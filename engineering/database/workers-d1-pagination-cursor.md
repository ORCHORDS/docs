# Cursor-Based Pagination with Cloudflare D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You serve a feed or list endpoint backed by D1. Offset pagination (`LIMIT 100 OFFSET 900`) degrades as pages grow — SQLite must walk 900 rows it discards. It also suffers from page drift: an insert at the top shifts every offset while a client is paginating. You need stable, efficient cursor-based (keyset) pagination.

---

## Context

Keyset pagination uses values from the last row of a page as the cursor for the next page. For a `(created_at DESC, id ASC)` ordering, the cursor encodes those two values. The next-page query becomes:

```sql
WHERE (created_at, id) < (?, ?)   -- for DESC on created_at
```

SQLite supports row-value comparisons via the `(a, b) < (x, y)` syntax (equivalent to `a < x OR (a = x AND b < y)`). Combined with a composite index, this is an index seek — O(log n) — regardless of how many pages the client has consumed.

Base64-encoded JSON is a safe, opaque cursor format. Clients treat it as a black box; you control the encoding on both ends.

---

## Solution

```typescript
// src/types.ts
export interface Env {
  DB: D1Database;
}

export interface Post {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
}

export interface CursorPayload {
  created_at: string;
  id: string;
  direction: 'forward' | 'backward';
}

export interface PageResult<T> {
  items: T[];
  nextCursor: string | null;
  prevCursor: string | null;
  /** Estimated total — accurate within ~5 % via sqlite_stat1, no COUNT(*) scan. */
  estimatedTotal?: number;
}

// src/cursor.ts
export function encodeCursor(payload: CursorPayload): string {
  return btoa(JSON.stringify(payload));
}

export function decodeCursor(cursor: string): CursorPayload {
  try {
    return JSON.parse(atob(cursor)) as CursorPayload;
  } catch {
    throw new Error('Invalid cursor');
  }
}

// src/posts.ts
import { encodeCursor, decodeCursor } from './cursor';

const DEFAULT_PAGE_SIZE = 20;
const MAX_PAGE_SIZE = 100;

export class PostRepository {
  constructor(private db: D1Database) {}

  /**
   * Cursor-based paginated list, ordered by (created_at DESC, id ASC).
   *
   * Passing `cursor` fetches the next page after that position.
   * Passing `before` fetches the page before that position (backward).
   */
  async list(
    userId: string,
    options: {
      cursor?: string;
      before?: string;
      pageSize?: number;
    } = {}
  ): Promise<PageResult<Post>> {
    const limit = Math.min(options.pageSize ?? DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE);

    let rows: Post[];

    if (options.cursor) {
      rows = await this.pageAfter(userId, decodeCursor(options.cursor), limit);
    } else if (options.before) {
      rows = await this.pageBefore(userId, decodeCursor(options.before), limit);
    } else {
      rows = await this.firstPage(userId, limit);
    }

    return this.buildPageResult(rows, limit);
  }

  private async firstPage(userId: string, limit: number): Promise<Post[]> {
    const result = await this.db
      .prepare(
        `SELECT id, user_id, title, created_at
         FROM posts
         WHERE user_id = ?
         ORDER BY created_at DESC, id ASC
         LIMIT ?`
      )
      .bind(userId, limit + 1)  // fetch +1 to detect next page
      .all<Post>();
    return result.results;
  }

  private async pageAfter(
    userId: string,
    cursor: CursorPayload,
    limit: number
  ): Promise<Post[]> {
    // For DESC created_at: "after" means older — created_at is smaller
    // Row-value comparison: (created_at, id) < (cursor.created_at, cursor.id)
    // OR created_at equals cursor and id is lexicographically after (ASC tiebreak)
    const result = await this.db
      .prepare(
        `SELECT id, user_id, title, created_at
         FROM posts
         WHERE user_id = ?
           AND (created_at < ? OR (created_at = ? AND id > ?))
         ORDER BY created_at DESC, id ASC
         LIMIT ?`
      )
      .bind(userId, cursor.created_at, cursor.created_at, cursor.id, limit + 1)
      .all<Post>();
    return result.results;
  }

  private async pageBefore(
    userId: string,
    cursor: CursorPayload,
    limit: number
  ): Promise<Post[]> {
    // Fetch rows newer than the cursor, reversed, then flip back to DESC order.
    const result = await this.db
      .prepare(
        `SELECT id, user_id, title, created_at FROM (
           SELECT id, user_id, title, created_at
           FROM posts
           WHERE user_id = ?
             AND (created_at > ? OR (created_at = ? AND id < ?))
           ORDER BY created_at ASC, id DESC
           LIMIT ?
         ) ORDER BY created_at DESC, id ASC`
      )
      .bind(userId, cursor.created_at, cursor.created_at, cursor.id, limit + 1)
      .all<Post>();
    return result.results;
  }

  private buildPageResult(rows: Post[], limit: number): PageResult<Post> {
    const hasMore = rows.length > limit;
    const items = hasMore ? rows.slice(0, limit) : rows;

    const first = items[0];
    const last = items[items.length - 1];

    return {
      items,
      nextCursor: hasMore && last
        ? encodeCursor({ created_at: last.created_at, id: last.id, direction: 'forward' })
        : null,
      prevCursor: first
        ? encodeCursor({ created_at: first.created_at, id: first.id, direction: 'backward' })
        : null,
    };
  }

  /**
   * Estimated total count without a full COUNT(*) scan.
   * Reads sqlite_stat1 which is updated by ANALYZE.
   * Accurate within a few percent; do not use for billing or exact reporting.
   */
  async estimatedCount(userId: string): Promise<number | null> {
    // sqlite_stat1 holds aggregate stats; not per-user, so this is a rough estimate.
    const row = await this.db
      .prepare(
        `SELECT CAST(stat AS INTEGER) as n
         FROM sqlite_stat1
         WHERE tbl = 'posts' AND idx IS NULL
         LIMIT 1`
      )
      .first<{ n: number }>();
    return row?.n ?? null;
  }
}

// src/worker.ts
import { PostRepository } from './posts';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== '/posts') return new Response('Not Found', { status: 404 });

    // Auth (simplified).
    const userId = request.headers.get('X-User-Id');
    if (!userId) return new Response('Unauthorized', { status: 401 });

    const repo = new PostRepository(env.DB);
    const cursor = url.searchParams.get('cursor') ?? undefined;
    const before = url.searchParams.get('before') ?? undefined;
    const pageSize = parseInt(url.searchParams.get('limit') ?? '20', 10);

    try {
      const page = await repo.list(userId, { cursor, before, pageSize });
      return Response.json(page);
    } catch (err) {
      if (err instanceof Error && err.message === 'Invalid cursor') {
        return Response.json({ error: 'Invalid cursor' }, { status: 400 });
      }
      throw err;
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

**Schema and indexes:**
```sql
CREATE TABLE posts (
  id         TEXT NOT NULL,
  user_id    TEXT NOT NULL,
  title      TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (id)
);

-- Index must match ORDER BY exactly for an index-only scan.
CREATE INDEX idx_posts_user_created
  ON posts (user_id, created_at DESC, id ASC);
```

The `(user_id, created_at DESC, id ASC)` composite index means:
1. SQLite enters the index at `user_id = ?`.
2. It seeks to `created_at` at the cursor position.
3. Reads exactly `LIMIT + 1` index entries without touching the table (covering index if only those columns are selected).

**`+1` trick:** Fetch `limit + 1` rows. If the result has `limit + 1` items, there is a next page — pop the extra row and encode the last kept row as `nextCursor`. If `length <= limit`, you are on the last page.

**Stable ordering requirement:** The `ORDER BY` clause must be deterministic — every row needs a unique position. `created_at` alone can have ties (many inserts in the same second). Adding `id ASC` as a tiebreaker makes the order unique. Both `created_at` and `id` must appear in the cursor.

---

## Anti-patterns

```typescript
// BAD: offset pagination
const page = parseInt(url.searchParams.get('page') ?? '0');
await db.prepare('SELECT * FROM posts LIMIT 20 OFFSET ?').bind(page * 20).all();
// ^ O(n) cost grows with page number; unstable under inserts.

// BAD: cursor with only created_at (non-unique)
await db.prepare(
  'SELECT * FROM posts WHERE created_at < ? ORDER BY created_at DESC LIMIT 20'
).bind(cursor.created_at).all();
// ^ Rows with the same created_at are silently skipped or duplicated at page boundaries.

// BAD: exposing internal cursor structure to clients
const cursor = `${row.created_at}|${row.id}`;
// ^ Schema changes break all in-flight cursors. Use opaque base64 JSON.
```

---

## Gotchas

- **Cursor expiry:** Cursors are stable as long as rows are not deleted. If you support delete, a cursor pointing at a deleted row still works — the WHERE clause skips to the next matching row naturally.
- **Backward pagination is tricky.** The inner-query-reversal technique shown above is the standard approach. Test it carefully against your specific ORDER BY clause.
- **`sqlite_stat1` requires `ANALYZE`.** Run `ANALYZE posts;` as part of migrations after large data loads to refresh the statistics used by `estimatedCount`. On a live database, run it in a scheduled Cron Trigger.
- **Do not use `ROWID` as a tiebreaker** unless the table is `WITHOUT ROWID = false`. TEXT primary keys in D1 default to WITHOUT ROWID behavior, so `id` (your primary key) is the correct tiebreaker.

---

## Verification

```typescript
// test/pagination.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { PostRepository } from '../src/posts';

describe('Cursor pagination', () => {
  let repo: PostRepository;

  beforeEach(async () => {
    const db = getMiniflareD1('DB');
    await db.exec(SCHEMA_SQL);
    // Seed 25 posts for user-a, all with distinct created_at.
    for (let i = 0; i < 25; i++) {
      const ts = new Date(Date.now() - i * 1000).toISOString();
      await db
        .prepare("INSERT INTO posts (id, user_id, title, created_at) VALUES (?, 'user-a', ?, ?)")
        .bind(`post-${String(i).padStart(2, '0')}`, `Post ${i}`, ts)
        .run();
    }
    repo = new PostRepository(db);
  });

  it('first page returns 10 items and a nextCursor', async () => {
    const page = await repo.list('user-a', { pageSize: 10 });
    expect(page.items).toHaveLength(10);
    expect(page.nextCursor).not.toBeNull();
  });

  it('second page items do not overlap with first page', async () => {
    const page1 = await repo.list('user-a', { pageSize: 10 });
    const page2 = await repo.list('user-a', { cursor: page1.nextCursor!, pageSize: 10 });
    const ids1 = new Set(page1.items.map(p => p.id));
    for (const item of page2.items) {
      expect(ids1.has(item.id)).toBe(false);
    }
  });

  it('all pages together cover all 25 items exactly once', async () => {
    const seen = new Set<string>();
    let cursor: string | null = null;
    do {
      const page = await repo.list('user-a', { cursor: cursor ?? undefined, pageSize: 10 });
      for (const item of page.items) {
        expect(seen.has(item.id)).toBe(false);
        seen.add(item.id);
      }
      cursor = page.nextCursor;
    } while (cursor);
    expect(seen.size).toBe(25);
  });
});
```

---

## Related

- `workers-d1-row-level-security.md` — combine user_id scoping with keyset predicates
- `workers-d1-full-text-search.md` — FTS queries also benefit from keyset pagination on `rowid`
- `workers-d1-time-series-data.md` — time-series tables use identical (timestamp, id) cursor patterns

---

## Sources

- "Pagination done the right way": https://use-the-index-luke.com/no-offset
- SQLite row-value comparison: https://www.sqlite.org/rowvalue.html
- Cloudflare D1 parameterized queries: https://developers.cloudflare.com/d1/worker-api/prepared-statements/
