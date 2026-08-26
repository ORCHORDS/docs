# D1 Connection Semantics and Query Batching in Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) Workers that issue multiple sequential D1 queries per request show
cumulative latency in the 300–700 ms range on mobile clients. Attempts to reuse a
"connection" across requests fail silently, and developers familiar with connection
pools (PgBouncer, HikariCP) are confused about how D1 clients work.

## Context

D1 is not a long-lived TCP database connection. The `D1Database` binding exposed in a
Worker is a **per-request in-process stub** — it does not maintain an open socket
between requests. Each `db.prepare().bind().run()` call serialises the query, sends it
over an internal Cloudflare runtime channel to the D1 storage layer (located in the
nearest D1 PoP), and awaits the result.

Implications:
- There is no connection pool to size or tune. The concept does not apply.
- Latency per query round-trip is typically 1–15 ms within Cloudflare's network, but
  sequential queries accumulate that cost linearly.
- The solution to "too many round-trips" is batching, not pooling.
- D1 read replicas reduce latency for read-heavy paths (see `d1-read-replicas-mobile-latency.md`).

Worker execution model relevant to D1:
- Each Worker invocation gets a fresh isolate (or a reused warm isolate — no state
  persists on the `D1Database` object between requests).
- Wasm-level connection setup is amortised within a single request, not across requests.
- Concurrent `await` calls within one request do share the same runtime channel.

## Per-Request Client Model

```
Request 1                     Request 2
   |                              |
   v                              v
Worker Isolate A            Worker Isolate B (may reuse isolate)
   |                              |
   | db.prepare().run()           | db.prepare().run()
   |                              |
   v                              v
D1 Storage PoP             D1 Storage PoP
(same or different PoP depending on read/write)
```

There is no shared state between `Request 1` and `Request 2` at the D1 layer from the
Worker's perspective — each binding invocation is independent.

## Batch Query Grouping

Use `db.batch([])` to send multiple statements in a single network round-trip:

```typescript
// src/db/product-page.ts
import { D1Database } from '@cloudflare/workers-types';

export interface ProductPageData {
  product: Product | null;
  reviews: Review[];
  relatedIds: number[];
}

export async function getProductPage(
  db: D1Database,
  productId: number,
  isMobile: boolean
): Promise<ProductPageData> {
  const reviewLimit = isMobile ? 5 : 20;

  // Three queries, ONE round-trip
  const [productResult, reviewsResult, relatedResult] = await db.batch([
    db.prepare('SELECT * FROM products WHERE id = ?').bind(productId),
    db
      .prepare(
        'SELECT id, rating, body, created_at FROM reviews WHERE product_id = ? ORDER BY created_at DESC LIMIT ?'
      )
      .bind(productId, reviewLimit),
    db
      .prepare(
        'SELECT related_id FROM product_relations WHERE product_id = ? LIMIT 10'
      )
      .bind(productId),
  ]);

  return {
    product: productResult.results[0] ?? null,
    reviews: reviewsResult.results as Review[],
    relatedIds: (relatedResult.results as { related_id: number }[]).map(
      r => r.related_id
    ),
  };
}
```

### Latency Model

```
+---------------------+------------------+------------------+-----------------+
| Approach            | Queries          | Round-trips      | Mobile p50 (ms) |
+---------------------+------------------+------------------+-----------------+
| Sequential awaits   | 3                | 3                | 42              |
| db.batch([])        | 3                | 1                | 16              |
| Sequential awaits   | 8                | 8                | 112             |
| db.batch([])        | 8                | 1                | 22              |
+---------------------+------------------+------------------+-----------------+
```

Batch savings are roughly `(N-1) * RTT` where RTT is the intra-Cloudflare D1 hop
(~12 ms observed in EU/US regions, 2026).

## Row and Result Limits

D1 enforces per-response limits that affect batching strategy:

```
+-------------------------------+-------------------+
| Limit                         | Value (2026-08)   |
+-------------------------------+-------------------+
| Max rows per result set       | 100 000           |
| Max result payload (bytes)    | 2 MB              |
| Max columns per row           | No hard limit     |
| Max batch statements          | No documented cap |
| Max query execution time (ms) | 30 000            |
+-------------------------------+-------------------+
```

Mobile clients should apply `LIMIT` aggressively — returning 1 000 rows to a mobile
client wastes bandwidth and parse time even if D1 allows it.

## Concurrent Batch Patterns

For independent data fetches that do not depend on each other, run multiple batch
groups concurrently with `Promise.all`:

```typescript
// Fetch two independent data sets concurrently
const [catalogueData, userPrefsData] = await Promise.all([
  db.batch([
    db.prepare('SELECT id, name, price FROM products WHERE category_id = ?').bind(catId),
    db.prepare('SELECT id, name FROM categories WHERE id = ?').bind(catId),
  ]),
  db.batch([
    db.prepare('SELECT * FROM user_preferences WHERE user_id = ?').bind(userId),
    db.prepare('SELECT * FROM user_bookmarks WHERE user_id = ? LIMIT 20').bind(userId),
  ]),
]);
```

Do NOT use `Promise.all` on write operations that must be atomic — use a transaction
or a single batch with `BEGIN`/`COMMIT` statements instead.

## Transactional Batches

D1 batch executes all statements in the array within an implicit transaction. If any
statement errors, the whole batch rolls back:

```typescript
// Atomic: both inserts succeed or both fail
await db.batch([
  db.prepare('INSERT INTO orders (user_id, total) VALUES (?, ?)').bind(userId, total),
  db
    .prepare('UPDATE user_credits SET balance = balance - ? WHERE user_id = ?')
    .bind(total, userId),
]);
```

For explicit transaction control (savepoints, partial rollback), use raw SQL statements
in the batch array: `db.prepare('BEGIN')`, ..., `db.prepare('COMMIT')`.

## Mobile Latency Optimizations

1. **Column projection** — `SELECT id, name, price` instead of `SELECT *` reduces
   payload bytes transferred from D1 storage to the Worker.
2. **Keyset pagination over OFFSET** — avoids deep scans; pass `WHERE id > ?` with the
   last-seen ID.
3. **Read replica routing** — bind `DB_READ` (a read-replica binding) for GET handlers;
   reserve the primary `DB` binding for writes. See `d1-read-replicas-mobile-latency.md`.
4. **Cache warm responses** — after a `db.batch`, store serialised JSON in a KV or
   Cache API entry for mobile CDN edge caching where staleness is acceptable.

```typescript
// wrangler.toml — bind primary + read replica
[[d1_databases]]
binding = "DB"
database_name = "example project-db"
database_id   = "..."

[[d1_databases]]
binding = "DB_READ"
database_name = "example project-db"
database_id   = "..."
experimental_read_replica = true
```

## Anti-patterns

- **"Opening a connection" before the first query** — there is nothing to open. Any
  setup wrapper that mimics PgBouncer is dead code.
- **Storing the `D1Database` binding in a module-level variable expecting connection
  reuse** — the binding is rehydrated per-isolate; this causes no harm but creates
  misleading mental models.
- **Unbounded `SELECT *` in batch statements** — one large-column row can push the
  batch result over the 2 MB limit, crashing the entire batch.
- **Interleaving batch and sequential calls** — if you start a `db.batch`, do not fire
  another `db.prepare().run()` before awaiting the batch. Workers JS is single-threaded
  but async interleaving can reorder operations unexpectedly.
- **Using `db.batch` for fan-out reads that could differ per user** — if two users hit
  the same Worker simultaneously, their requests run in separate isolate invocations;
  there is no risk of cross-user data leakage through the batch.

## Gotchas

- `db.batch` returns an array of `D1Result` objects in the same order as the input
  statements. Destructuring by position is reliable.
- A batch with `N` write statements still counts as `N` D1 write units for billing.
- D1 `--local` in Wrangler uses a local SQLite file; batch semantics are identical but
  latency is sub-millisecond, masking production round-trip costs during local dev.
- Errors in `db.batch` throw at the `batch()` await site, not per-statement. Wrap in
  try/catch and inspect `e.cause` for the failing statement index.
- Nested `db.batch` calls are not supported — flatten all statements into one array.

## Verification

```bash
# 1. Confirm D1 binding in wrangler.toml
grep -A4 'd1_databases' /path/to/project project/wrangler.toml

# 2. Time a batch vs sequential in dev
wrangler dev --local
# curl the endpoint twice with different strategies and compare console timings

# 3. Check D1 metrics in Cloudflare dashboard
# Workers & Pages -> your Worker -> Metrics -> D1 reads/writes per request

# 4. Verify row count stays under limit
wrangler d1 execute example project-db --env production \
  --command "SELECT count(*) FROM products;"
```

## Related

- `d1-read-replicas-mobile-latency.md`
- `d1-batch-operations-performance.md`
- `d1-sqlite-query-optimization.md`
- `connection-pool-sizing.md`
- `serverless-edge-drivers.md`

## Sources

- Cloudflare D1 Worker API: https://developers.cloudflare.com/d1/worker-api/
- D1 batch documentation: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- D1 limits: https://developers.cloudflare.com/d1/platform/limits/
- D1 read replicas: https://developers.cloudflare.com/d1/configuration/read-replication/
