# D1 Batch Read Coalescing in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers handler fetches user rows in three separate places — auth middleware, a business-logic function, and a response formatter. Each issues its own `db.prepare().bind().first()` call. With 50 concurrent requests, the database sees 150 reads for 50 unique users. p99 latency climbs, and D1 billing reflects triple the reads you actually need.

## Context

D1 charges per query execution and has a per-Worker subrequest budget. Within a single isolate lifecycle every `db.prepare().bind().first()` is a separate network round-trip to D1's SQLite replica. Unlike a connection pool that can pipeline queries across requests, Workers isolates share no state between invocations by default. The solution is a **per-request read cache** that coalesces duplicate primary-key lookups into a single `db.batch()` call and then distributes results to all callers.

---

## Per-request Cache with Deferred Promise

Build a cache keyed by `table:pk`. First caller registers a pending Promise; subsequent callers within the same request share the same Promise. After all keys are registered, flush the batch.

```typescript
type PendingRead = {
  resolve: (value: Record<string, unknown> | null) => void;
  reject: (err: unknown) => void;
};

export class D1ReadCoalescer {
  private cache = new Map<string, Promise<Record<string, unknown> | null>>();
  private pending = new Map<string, PendingRead>();
  private flushed = false;

  constructor(private db: D1Database, private table: string, private pkCol: string) {}

  get(pk: string | number): Promise<Record<string, unknown> | null> {
    const key = String(pk);
    if (this.cache.has(key)) return this.cache.get(key)!;

    const promise = new Promise<Record<string, unknown> | null>((resolve, reject) => {
      this.pending.set(key, { resolve, reject });
    });
    this.cache.set(key, promise);
    return promise;
  }

  async flush(): Promise<void> {
    if (this.flushed || this.pending.size === 0) return;
    this.flushed = true;

    const keys = [...this.pending.keys()];
    const placeholders = keys.map(() => '?').join(',');
    const stmt = this.db.prepare(
      `SELECT * FROM ${this.table} WHERE ${this.pkCol} IN (${placeholders})`
    );
    const results = await stmt.bind(...keys).all<Record<string, unknown>>();

    const byKey = new Map(results.results.map(r => [String(r[this.pkCol]), r]));
    for (const [key, { resolve }] of this.pending) {
      resolve(byKey.get(key) ?? null);
    }
    this.pending.clear();
  }
}
```

## Wiring into the Request Lifecycle

Create a coalescer per request in the `fetch` handler and flush before any code awaits results.

```typescript
import { D1ReadCoalescer } from './coalescer';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const users = new D1ReadCoalescer(env.DB, 'users', 'id');

    // Register reads — no DB call yet
    const authPromise  = users.get(getAuthUserId(request));
    const ownerPromise = users.get(getResourceOwnerId(request));
    const viewerIds    = getViewerIds(request).map(id => users.get(id));

    // Single batch flush — one D1 round-trip for all keys
    await users.flush();

    // All promises now resolve from the in-memory cache
    const [authUser, ownerUser] = await Promise.all([authPromise, ownerPromise]);
    const viewers = await Promise.all(viewerIds);

    if (!authUser) return new Response('Unauthorized', { status: 401 });
    return renderResponse(authUser, ownerUser, viewers);
  },
};
```

## Handling Cache Invalidation Mid-request

If a write occurs mid-request, mark that key stale so a subsequent read re-fetches.

```typescript
export class D1ReadCoalescer {
  // ... existing fields

  invalidate(pk: string | number): void {
    this.cache.delete(String(pk));
  }

  async write(pk: string | number, data: Record<string, unknown>): Promise<void> {
    await this.db.prepare(`UPDATE ${this.table} SET data=? WHERE id=?`)
      .bind(JSON.stringify(data), pk)
      .run();
    this.invalidate(pk);
  }
}
```

## Multi-table Coalescer Registry

Scale to many tables by holding coalescers in a registry keyed by table name.

```typescript
export class RequestDB {
  private coalescers = new Map<string, D1ReadCoalescer>();

  constructor(private db: D1Database) {}

  table(name: string, pk = 'id'): D1ReadCoalescer {
    if (!this.coalescers.has(name)) {
      this.coalescers.set(name, new D1ReadCoalescer(this.db, name, pk));
    }
    return this.coalescers.get(name)!;
  }

  async flushAll(): Promise<void> {
    await Promise.all([...this.coalescers.values()].map(c => c.flush()));
  }
}

// In fetch handler:
const db = new RequestDB(env.DB);
const userP   = db.table('users').get(userId);
const postP   = db.table('posts', 'post_id').get(postId);
await db.flushAll(); // one D1 batch() per table, all in parallel
```

## Measuring Impact

Log before/after counts to confirm coalescing is working.

```typescript
export class D1ReadCoalescer {
  private hitCount = 0;
  private missCount = 0;

  get(pk: string | number): Promise<Record<string, unknown> | null> {
    const key = String(pk);
    if (this.cache.has(key)) {
      this.hitCount++;
      return this.cache.get(key)!;
    }
    this.missCount++;
    // ... existing logic
  }

  stats() {
    return {
      hits: this.hitCount,
      misses: this.missCount,
      ratio: this.hitCount / (this.hitCount + this.missCount || 1),
    };
  }
}
```

---

## Anti-patterns

- **Flushing inside `get()`**: Causes a partial batch per call. Always register all keys first, then call `flush()` once.
- **Sharing the coalescer across requests via module scope**: D1 rows may be stale. The coalescer must be instantiated fresh per request.
- **Awaiting `get()` before `flush()`**: Deadlocks — the Promise never resolves because `flush()` was never called. Register first, flush second, await third.
- **Using a coalescer with writes that depend on reads**: If a write changes rows other keys depend on, invalidate those keys explicitly before awaiting their Promises.
- **Ignoring `db.batch()` limits**: D1 batch accepts up to 100 statements per call. If your coalescer might see >100 unique PKs, chunk the flush into batches of 100.

---

## Gotchas

- `db.batch()` returns results in statement order, not PK order. Always re-index by primary key after the batch, never assume positional alignment.
- D1 `IN (?)` binding must list individual `?` placeholders; you cannot bind a single array parameter. Generate the placeholder string dynamically.
- The coalescer only helps with **read deduplication** within one request. Cross-request deduplication requires KV or Cache API.
- If a row does not exist, `byKey.get(key)` returns `undefined`, not `null`. Normalize to `null` for consistent downstream handling.

---

## Verification

```typescript
// Add to test suite
const coalescer = new D1ReadCoalescer(mockDB, 'users', 'id');
const p1 = coalescer.get('42');
const p2 = coalescer.get('42'); // same key
const p3 = coalescer.get('99');
await coalescer.flush();

// Confirm only one DB batch was issued, containing ['42', '99']
expect(mockDB.batchCallCount).toBe(1);
expect(mockDB.lastBatchKeys).toEqual(['42', '99']);
// Both p1 and p2 resolve to the same object
expect(await p1).toBe(await p2);
```

Run `wrangler dev --local` with `console.log(coalescer.stats())` at the end of the handler; confirm `misses === unique PKs` and `hits === duplicates`.

---

## Related

- `d1-batch-query-performance-optimization.md` — batching write queries
- `d1-prepared-statement-reuse.md` — reusing prepared statements across calls
- `durable-objects-storage-read-coalescing.md` — same pattern for DO storage
- `workers-request-coalescing-deduplication.md` — coalescing at the HTTP level

---

## Sources

- Cloudflare D1 docs — `db.batch()`: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- SQLite IN clause binding: https://www.sqlite.org/lang_expr.html#the_in_and_not_in_operators
- Cloudflare D1 limits (max 100 statements per batch): https://developers.cloudflare.com/d1/platform/limits/
