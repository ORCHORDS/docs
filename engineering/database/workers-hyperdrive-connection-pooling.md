# Optimizing Hyperdrive Connection Pooling for PostgreSQL

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker that connects directly to a remote PostgreSQL database over TCP suffers from high cold-start latency because each Worker isolate opens a new TCP+TLS connection on every request. Under sustained load the database exhaust its `max_connections` limit. Hyperdrive solves both problems by maintaining a persistent connection pool between Cloudflare's network and the database, but misconfigured pool sizes or incompatible prepared-statement usage cause query errors and performance regressions.

## Context

Hyperdrive is a Cloudflare service that sits between Workers and external databases. It provides:
1. **Connection pooling** — one Hyperdrive instance maintains N long-lived connections to the database; Workers share them.
2. **Local caching** — read queries that opt-in are served from Cloudflare's edge cache, bypassing the database entirely.
3. **Reduced latency** — the TCP handshake to the database happens once; Workers communicate with Hyperdrive over Cloudflare's private backbone.

The postgres driver used inside the Worker must be compatible with Hyperdrive's connection string format. `postgres` (the `postgres.js` npm package) and `pg` both work; `pg` with prepared statements requires special configuration.

## Solution

```typescript
// wrangler.toml (Hyperdrive binding)
// [[hyperdrive]]
// binding = "HYPERDRIVE"
// id = "<your-hyperdrive-config-id>"

// src/db/client.ts
import postgres from 'postgres'; // postgres.js v3+
import type { Hyperdrive } from '@cloudflare/workers-types';

export interface Env {
  HYPERDRIVE: Hyperdrive;
  DB_MAX_CONNECTIONS?: string;
  ANALYTICS: AnalyticsEngineDataset; // for pool monitoring
}

// Worker module scope — one client per isolate.
let _sql: ReturnType<typeof postgres> | null = null;

export function getSql(env: Env) {
  if (_sql) return _sql;

  const maxConnections = parseInt(env.DB_MAX_CONNECTIONS ?? '5', 10);

  _sql = postgres(env.HYPERDRIVE.connectionString, {
    // Hyperdrive handles TLS externally; disable pg-level TLS.
    ssl: false,
    // Pool size: match Hyperdrive's per-Worker connection quota.
    // Cloudflare recommends ≤5 per Worker isolate for write-heavy,
    // ≤10 for read-heavy workloads.
    max: maxConnections,
    // Idle timeout shorter than Hyperdrive's 10-minute pool TTL.
    idle_timeout: 20,
    // Max connection lifetime — recycle before Hyperdrive force-closes.
    max_lifetime: 1800,
    // Disable prepared statements: Hyperdrive's connection pooling
    // routes queries to arbitrary backend connections; server-side
    // prepared statement handles are connection-local and will 404
    // on a different connection.
    prepare: false,
    // postgres.js transforms: convert snake_case columns to camelCase.
    transform: { column: { from: postgres.fromCamel, to: postgres.toCamel } },
    // Connection timeout — fail fast rather than queue indefinitely.
    connect_timeout: 5,
    // Reduce verbosity in production.
    debug: false,
    onnotice: () => {},
  });

  return _sql;
}

// ----- Read-heavy path: leverage Hyperdrive cache --------------------------

// Hyperdrive caches SELECT responses when `cacheControl` is enabled
// in the Hyperdrive config (set via dashboard or wrangler CLI).
// The cache key is the full query + parameters.

export interface Product {
  id: string;
  sku: string;
  name: string;
  priceMinor: number;
  stockQuantity: number;
  updatedAt: Date;
}

export async function getProductBySku(
  env: Env,
  sku: string
): Promise<Product | null> {
  const sql = getSql(env);
  // Hyperdrive caches this query for up to the configured cache TTL.
  const rows = await sql<Product[]>`
    SELECT id, sku, name, price_minor, stock_quantity, updated_at
    FROM products
    WHERE sku = ${sku}
      AND deleted_at IS NULL
    LIMIT 1
  `;
  return rows[0] ?? null;
}

// ----- Write path: bypass cache, use explicit transaction ------------------

export interface OrderRow {
  id: string;
  userId: string;
  totalMinor: number;
}

export async function createOrder(
  env: Env,
  userId: string,
  items: Array<{ productId: string; quantity: number; unitPriceMinor: number }>
): Promise<OrderRow> {
  const sql = getSql(env);

  // postgres.js transactions check out a single connection from the pool
  // for the duration of the transaction block — important when pooling
  // through Hyperdrive so all statements execute on the same backend conn.
  const order = await sql.begin(async (tx) => {
    const [newOrder] = await tx<OrderRow[]>`
      INSERT INTO orders (id, user_id, total_minor)
      VALUES (gen_random_uuid(), ${userId}, ${items.reduce(
        (sum, i) => sum + i.quantity * i.unitPriceMinor,
        0
      )})
      RETURNING id, user_id, total_minor
    `;

    for (const item of items) {
      await tx`
        INSERT INTO order_items (order_id, product_id, quantity, unit_price_minor)
        VALUES (${newOrder.id}, ${item.productId}, ${item.quantity}, ${item.unitPriceMinor})
      `;

      // Decrement stock — must happen in the same transaction.
      const result = await tx`
        UPDATE products
        SET stock_quantity = stock_quantity - ${item.quantity}
        WHERE id = ${item.productId}
          AND stock_quantity >= ${item.quantity}
        RETURNING stock_quantity
      `;

      if (result.length === 0) {
        throw new Error(`Insufficient stock for product ${item.productId}`);
      }
    }

    return newOrder;
  });

  return order;
}

// ----- Pool utilization monitoring via Analytics Engine --------------------

export async function emitPoolMetrics(env: Env, sql: ReturnType<typeof postgres>) {
  // postgres.js exposes pool stats via sql.reserve() count heuristics.
  // Query pg_stat_activity for Hyperdrive's connections to this db.
  const [stats] = await sql<[{ active: number; idle: number }]>`
    SELECT
      COUNT(*) FILTER (WHERE state = 'active') AS active,
      COUNT(*) FILTER (WHERE state = 'idle')   AS idle
    FROM pg_stat_activity
    WHERE application_name = 'hyperdrive'
  `;

  env.ANALYTICS.writeDataPoint({
    blobs: ['hyperdrive', 'pool'],
    doubles: [stats.active, stats.idle, stats.active + stats.idle],
    indexes: ['hyperdrive_pool'],
  });
}

// ----- Hyperdrive config creation via Cloudflare API (wrangler CLI) --------
// Run once:
//   wrangler hyperdrive create my-pool \
//     --connection-string="postgres://user:pass@db.host:5432/mydb" \
//     --caching-disabled=false \
//     --max-age=60 \
//     --stale-while-revalidate=15
//
// Tuning notes:
//   --max-age: cache TTL in seconds for read queries (default 60)
//   --stale-while-revalidate: serve stale data while refreshing (default 15)
//   For write-heavy workloads set --caching-disabled=true
```

## Implementation Details

**`prepare: false`** is the most critical setting. Hyperdrive's connection pooling can route the second query in a client session to a different backend connection than the first, where a server-side prepared statement handle does not exist. Setting `prepare: false` forces the driver to use extended query protocol without persistent server-side handles.

**Pool size per isolate** — Cloudflare can spawn many isolate instances per Worker. Each isolate opens up to `max` connections to Hyperdrive. The total concurrent database connections is `isolate_count × max`. A common production setting is `max: 5` (write-heavy) to `max: 10` (read-heavy). Hyperdrive itself limits the number of backend connections it opens.

**`idle_timeout` and `max_lifetime`** — set below Hyperdrive's internal idle-connection timeout (~10 min) to avoid the driver receiving a surprise connection closure from Hyperdrive. `max_lifetime: 1800` (30 min) recycles connections before Hyperdrive forcibly drops them.

**`sql.begin()` for transactions** — postgres.js' `begin` checks out one connection from the pool for the entire callback. Without this, sequential `await sql` calls in a transaction may use different connections (different Hyperdrive backends), and `ROLLBACK` on a different connection is a no-op.

**Analytics Engine** — D1 has no native connection-pool telemetry. Querying `pg_stat_activity` from a cron Worker and writing to Analytics Engine gives a time-series view of pool utilization without an external metrics system.

## Anti-patterns

- **Using `prepare: true` (default)** — causes `ERROR: prepared statement "s1" does not exist` under pooling.
- **Opening a new `postgres()` client per request** — bypasses module-scope caching, opens a fresh connection on every request, and saturates Hyperdrive's backend pool.
- **Performing reads inside transactions** — locks rows unnecessarily; keep reads outside `sql.begin()` and only wrap mutating statements.
- **Setting `max` to 1** — serialises all database access per isolate; fine for low-traffic but degrades under concurrency.
- **Disabling caching globally** — wastes Hyperdrive's main benefit for read-dominated workloads.

## Gotchas

- Hyperdrive's `connectionString` is a runtime secret resolved at request time. Do not read it at module scope outside of a function — it will be undefined.
- Hyperdrive caches only `SELECT` statements. `INSERT`, `UPDATE`, `DELETE`, and DDL bypass the cache.
- The cache TTL is set per Hyperdrive config, not per query. All cacheable queries share the same TTL; for mixed TTL needs, create multiple Hyperdrive configs.
- `ssl: false` on the `postgres()` client is correct for Hyperdrive — Hyperdrive terminates TLS on your behalf. Enabling it causes a double-TLS handshake failure.
- `pg_stat_activity` query requires the database user to have `pg_monitor` role or be a superuser.

## Verification

```typescript
// src/routes/health.ts
export async function handleHealth(env: Env): Promise<Response> {
  const sql = getSql(env);
  try {
    const [row] = await sql<[{ now: Date }]>`SELECT NOW() AS now`;
    return Response.json({ status: 'ok', dbTime: row.now });
  } catch (err) {
    return Response.json(
      { status: 'error', message: String(err) },
      { status: 503 }
    );
  }
}

// Confirm pool size via pg_stat_activity:
// SELECT COUNT(*), state FROM pg_stat_activity
// WHERE application_name = 'hyperdrive'
// GROUP BY state;
```

## Related

- [workers-d1-schema-versioning](workers-d1-schema-versioning.md)
- [workers-d1-soft-delete-pattern](workers-d1-soft-delete-pattern.md)

## Sources

- https://developers.cloudflare.com/hyperdrive/
- https://developers.cloudflare.com/hyperdrive/configuration/connection-pooling/
- https://github.com/porsager/postgres
- https://developers.cloudflare.com/analytics/analytics-engine/
