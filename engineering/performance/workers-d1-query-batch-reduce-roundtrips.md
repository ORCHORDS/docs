# Reducing D1 Round-trips with the Batch API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A product-detail page fetches data from three tables — `products`, `reviews`, and `inventory` — with three sequential `await env.DB.prepare(...).first()` calls. Each call is a separate HTTP round-trip from the Worker to the D1 service. On a US-East Worker serving a European D1 database the round-trip overhead alone is 60-100 ms per query, turning a single page load into 180-300 ms of pure network wait.

Goal: collapse N sequential D1 statements into a single `db.batch([...])` call so all statements travel in one request and return in one response.

---

## Context

- **D1 `db.batch()`** sends an array of prepared statements to the D1 service in a single HTTP request. The service executes them sequentially (in order), then returns an array of result sets.
- Each element in the returned array corresponds to the same-index statement.
- Statements in a batch share a single implicit transaction for reads; for writes they are each auto-committed unless you wrap them in explicit `BEGIN`/`COMMIT` statements.
- Batch does not support dynamic inter-statement dependencies (i.e., you cannot use the result of statement 1 as a parameter to statement 2 within the same batch).

---

## Before: N+1 Sequential Queries

```typescript
// src/handlers/product-detail-before.ts — SLOW
import type { Env } from '../types';

interface Product  { id: number; title: string; price: number; category: string }
interface Review   { id: number; product_id: number; rating: number; body: string }
interface Inventory { product_id: number; qty: number; warehouse: string }

export async function handleProductDetailSlow(
  productId: number,
  env: Env,
): Promise<Response> {
  const start = Date.now();

  // Round-trip 1
  const product = await env.DB
    .prepare('SELECT id, title, price, category FROM products WHERE id = ?1')
    .bind(productId)
    .first<Product>();

  if (!product) return new Response('Not Found', { status: 404 });

  // Round-trip 2 (depends on product.id — but product.id === productId, so we already have it)
  const reviews = await env.DB
    .prepare('SELECT id, product_id, rating, body FROM reviews WHERE product_id = ?1 ORDER BY id DESC LIMIT 10')
    .bind(productId)
    .all<Review>();

  // Round-trip 3
  const inventory = await env.DB
    .prepare('SELECT product_id, qty, warehouse FROM inventory WHERE product_id = ?1')
    .bind(productId)
    .first<Inventory>();

  const elapsed = Date.now() - start;
  console.log(`[slow] product-detail latency: ${elapsed} ms`);

  return Response.json(
    { product, reviews: reviews.results, inventory },
    { headers: { 'X-D1-Latency-Ms': String(elapsed) } },
  );
}
```

Typical elapsed on cross-region D1: **180-280 ms**.

---

## After: Single Batch Call

```typescript
// src/handlers/product-detail-after.ts — FAST
import type { Env } from '../types';

interface Product   { id: number; title: string; price: number; category: string }
interface Review    { id: number; product_id: number; rating: number; body: string }
interface Inventory { product_id: number; qty: number; warehouse: string }

export async function handleProductDetailFast(
  productId: number,
  env: Env,
): Promise<Response> {
  const start = Date.now();

  // Prepare all three statements
  const stmtProduct = env.DB
    .prepare('SELECT id, title, price, category FROM products WHERE id = ?1')
    .bind(productId);

  const stmtReviews = env.DB
    .prepare(
      'SELECT id, product_id, rating, body FROM reviews WHERE product_id = ?1 ORDER BY id DESC LIMIT 10',
    )
    .bind(productId);

  const stmtInventory = env.DB
    .prepare('SELECT product_id, qty, warehouse FROM inventory WHERE product_id = ?1')
    .bind(productId);

  // Single HTTP round-trip to D1
  const [productResult, reviewsResult, inventoryResult] = await env.DB.batch<
    Product | Review | Inventory
  >([stmtProduct, stmtReviews, stmtInventory]);

  const product = (productResult.results as Product[])[0] ?? null;
  if (!product) return new Response('Not Found', { status: 404 });

  const reviews = reviewsResult.results as Review[];
  const inventory = (inventoryResult.results as Inventory[])[0] ?? null;

  const elapsed = Date.now() - start;
  console.log(`[fast] product-detail latency: ${elapsed} ms`);

  return Response.json(
    { product, reviews, inventory },
    { headers: { 'X-D1-Latency-Ms': String(elapsed) } },
  );
}
```

Typical elapsed on cross-region D1: **65-90 ms** (one round-trip instead of three).

---

## Typed Batch Helper

For codebases with many batch patterns, a typed helper reduces boilerplate and makes the return types explicit:

```typescript
// src/lib/d1-batch.ts
import type { D1Database, D1PreparedStatement, D1Result } from '@cloudflare/workers-types';

/**
 * Strongly-typed wrapper around D1Database.batch().
 *
 * Usage:
 *   const [users, posts] = await batchTyped(env.DB, [
 *     { stmt: env.DB.prepare('SELECT * FROM users WHERE id = ?').bind(1), type: {} as User },
 *     { stmt: env.DB.prepare('SELECT * FROM posts WHERE user_id = ?').bind(1), type: {} as Post },
 *   ]);
 */
export async function batchTyped<T extends readonly { stmt: D1PreparedStatement; type: unknown }[]>(
  db: D1Database,
  queries: T,
): Promise<{ [K in keyof T]: D1Result<T[K]['type']> }> {
  const stmts = queries.map((q) => q.stmt);
  const results = await db.batch(stmts);
  return results as { [K in keyof T]: D1Result<T[K]['type']> };
}

// Example call
// const [productRes, reviewRes] = await batchTyped(env.DB, [
//   { stmt: env.DB.prepare('SELECT * FROM products WHERE id = ?').bind(42), type: {} as Product },
//   { stmt: env.DB.prepare('SELECT * FROM reviews WHERE product_id = ?').bind(42), type: {} as Review },
// ]);
```

---

## Benchmark Harness

```typescript
// scripts/benchmark-d1.ts  — run with: npx tsx scripts/benchmark-d1.ts
// Requires env vars: WORKER_URL

const WORKER_URL = process.env.WORKER_URL ?? 'https://my-worker.example.workers.dev';
const PRODUCT_ID = 1;
const ITERATIONS = 20;

async function measure(path: string): Promise<number[]> {
  const times: number[] = [];
  for (let i = 0; i < ITERATIONS; i++) {
    const t0 = performance.now();
    await fetch(`${WORKER_URL}${path}?id=${PRODUCT_ID}`);
    times.push(performance.now() - t0);
  }
  return times;
}

function stats(times: number[]) {
  const sorted = [...times].sort((a, b) => a - b);
  return {
    p50: sorted[Math.floor(sorted.length * 0.5)].toFixed(1),
    p90: sorted[Math.floor(sorted.length * 0.9)].toFixed(1),
    p99: sorted[Math.floor(sorted.length * 0.99)].toFixed(1),
  };
}

(async () => {
  console.log('Warming up...');
  await measure('/product-slow');
  await measure('/product-fast');

  console.log('Measuring slow (sequential) handler...');
  const slowTimes = await measure('/product-slow');

  console.log('Measuring fast (batch) handler...');
  const fastTimes = await measure('/product-fast');

  console.log('Sequential:', stats(slowTimes), 'ms');
  console.log('Batch:     ', stats(fastTimes), 'ms');
})();
```

---

## Anti-patterns

- **Using batch for inter-dependent queries**: if statement 2 needs the result of statement 1 (e.g., INSERT then SELECT last_insert_rowid()), batch cannot help — use `db.prepare('INSERT...').run()` then `db.prepare('SELECT last_insert_rowid()').first()`.
- **Batching writes without understanding transaction semantics**: batch does not wrap all statements in a single transaction by default. A failure in statement 3 does not roll back statements 1 and 2. Use explicit `BEGIN`/`COMMIT`/`ROLLBACK` pseudo-statements if you need atomicity.
- **Very large batches (50+ statements)**: D1 has payload size and statement count limits. Break batches of 50+ statements into chunks of 25.
- **`Promise.all` of separate `db.prepare().all()` calls**: this parallelises the HTTP calls from the Worker side but still opens multiple connections to D1. `db.batch()` is one connection.

---

## Gotchas

- `db.batch()` returns `D1Result[]` (always an array), even when individual statements use `.first()` semantics. You must index into `results[0]` to get the single row.
- TypeScript types: `D1Database.batch<T>()` takes a generic `T` that applies to all results in the batch. Use the typed helper above for mixed-type batches.
- Statement order in the returned array is guaranteed to match statement order in the input array.
- If any statement in the batch has a SQL error, the entire batch call rejects (the Promise rejects). Validate queries separately in development.

---

## Verification

```bash
# Deploy and test
npx wrangler deploy

# Compare X-D1-Latency-Ms headers
curl -sI "https://my-worker.workers.dev/product-slow?id=1" | grep X-D1
curl -sI "https://my-worker.workers.dev/product-fast?id=1" | grep X-D1

# Wrangler tail to see console.log latency output
npx wrangler tail --format pretty | grep latency
```

---

## Related

- `workers-speculative-prefetch-kv.md` — uses D1 batch inside the cron prefetch loop
- `workers-tcp-connection-reuse-upstream.md` — connection-level optimisations complementing batch
- [D1 Batch API docs](https://developers.cloudflare.com/d1/worker-api/prepared-statements/#batch-statements)

---

## Sources

- D1 Worker API — https://developers.cloudflare.com/d1/worker-api/
- D1 Batch Statements — https://developers.cloudflare.com/d1/worker-api/prepared-statements/#batch-statements
- D1 Limits — https://developers.cloudflare.com/d1/platform/limits/
