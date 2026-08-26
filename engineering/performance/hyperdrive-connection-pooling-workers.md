# Hyperdrive: Accelerating Database Queries from Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A Cloudflare Worker connecting directly to a PostgreSQL or MySQL database over the public internet incurs 100–300 ms of TLS handshake + connection overhead on every invocation due to Workers' stateless architecture. Hyperdrive eliminates this by maintaining persistent, pooled connections at Cloudflare PoPs.

## Context
Workers are stateless and ephemeral — they cannot hold open a database connection across invocations. Without Hyperdrive, each Worker invocation opens a fresh TCP + TLS connection to the origin database, adding significant latency. Hyperdrive is a connection pooler run at Cloudflare's network edge that maintains warm connections to the origin. Workers connect to Hyperdrive over a local (same-datacenter) socket in sub-millisecond time. Hyperdrive also caches read queries in memory at the PoP, avoiding round-trips for repeated SELECT statements.

## Configuring Hyperdrive

Create a Hyperdrive config via Wrangler and bind it to your Worker:

```toml
# wrangler.toml
name = "api-worker"
compatibility_date = "2025-01-01"

[[hyperdrive]]
binding = "HYPERDRIVE"
id = "<your-hyperdrive-config-id>"
```

```bash
# Create the config pointing at your Postgres instance
wrangler hyperdrive create my-db \
  --connection-string "postgresql://user:pass@db.example.com:5432/mydb"
```

## Querying via Hyperdrive

Use the Hyperdrive binding's `connectionString` with any Postgres client. The `postgres` npm package works well in Workers:

```typescript
import postgres from "postgres";

interface Env {
  HYPERDRIVE: Hyperdrive;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // connectionString points to Hyperdrive's local proxy, not the origin
    const sql = postgres(env.HYPERDRIVE.connectionString, {
      max: 1, // Workers are single-threaded — one connection per invocation
    });

    try {
      const url = new URL(request.url);
      const id = url.searchParams.get("id");

      if (!id || !/^\d+$/.test(id)) {
        return new Response("Bad Request", { status: 400 });
      }

      const rows = await sql`SELECT id, name, price FROM products WHERE id = ${parseInt(id, 10)}`;

      return Response.json(rows[0] ?? null);
    } finally {
      // Always end the connection — Hyperdrive returns it to the pool
      await sql.end();
    }
  },
};
```

## Read Query Caching

Hyperdrive caches SELECT results at the PoP. Configure cache TTL per binding in `wrangler.toml`:

```toml
[[hyperdrive]]
binding = "HYPERDRIVE"
id = "<your-hyperdrive-config-id>"

[hyperdrive.caching]
disabled = false
max_age = 60        # seconds to cache identical SELECT queries
stale_while_revalidate = 15
```

For queries where stale data is unacceptable (e.g., inventory counts), disable caching at the query level by wrapping them in a transaction — Hyperdrive never caches queries inside transactions:

```typescript
async function getInventoryLive(sql: postgres.Sql, productId: number): Promise<number> {
  // Transaction prevents Hyperdrive from caching this query
  const [result] = await sql.begin(async (tx) => {
    return tx`SELECT stock FROM inventory WHERE product_id = ${productId} FOR UPDATE`;
  });
  return result?.stock ?? 0;
}
```

## Batching Writes for Throughput

Batch INSERT/UPDATE statements to minimize round-trips through Hyperdrive:

```typescript
interface OrderItem {
  productId: number;
  quantity: number;
  unitPrice: number;
}

async function insertOrderItems(
  sql: postgres.Sql,
  orderId: number,
  items: OrderItem[],
): Promise<void> {
  if (items.length === 0) return;

  // postgres.js handles batch INSERT natively — single round-trip
  await sql`
    INSERT INTO order_items (order_id, product_id, quantity, unit_price)
    VALUES ${sql(items.map((i) => [orderId, i.productId, i.quantity, i.unitPrice]))}
  `;
}
```

## Connection Lifecycle and ctx.waitUntil

Always end the postgres.js client inside `ctx.waitUntil` when the response doesn't depend on it, to avoid delaying the response:

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const sql = postgres(env.HYPERDRIVE.connectionString, { max: 1 });

    const rows = await sql`SELECT id, slug, title FROM posts ORDER BY created_at DESC LIMIT 10`;

    // Return response immediately; clean up connection asynchronously
    const response = Response.json(rows);
    ctx.waitUntil(sql.end());
    return response;
  },
};
```

## Anti-patterns
- Setting `max > 1` connections per Worker invocation — Workers are single-threaded and extra connections waste Hyperdrive pool slots
- Wrapping all queries in transactions to bypass caching — transactions have higher latency; only use them when consistency requires it
- Using Hyperdrive with SQLite/D1 — Hyperdrive is for Postgres/MySQL; D1 has its own optimization path
- Not calling `sql.end()` — leaked connections exhaust the Hyperdrive pool and cause connection refused errors under load

## Gotchas
- Hyperdrive connection strings change format when rotated via `wrangler hyperdrive update` — redeploy the Worker after credential rotation
- The `FOR UPDATE` lock hint inside a transaction disables Hyperdrive query caching, which is intentional and correct
- `max_age` caching applies per-PoP; a cache invalidation on one PoP does not propagate to others immediately
- Hyperdrive does not support prepared statements with named parameters in all client libraries — test your client's wire protocol

## Verification
1. Add `server-timing: db;dur=<ms>` to responses and compare with/without Hyperdrive
2. Use `wrangler hyperdrive get <id>` to confirm the config is active and the origin is reachable
3. Enable Cloudflare Analytics for the Worker and graph P95 request duration before/after — expect 40–80% reduction on query-heavy endpoints
4. Test cache hits by sending identical SELECT parameters twice in quick succession and checking that `db` timing drops to < 5 ms on the second request

## Related
- [d1-query-optimization.md](d1-query-optimization.md)
- [d1-batch-query-performance-optimization.md](d1-batch-query-performance-optimization.md)
- [workers-cold-start-optimization.md](workers-cold-start-optimization.md)
- [database-connection-pool-sizing.md](database-connection-pool-sizing.md)

## Sources
- Cloudflare Docs: Hyperdrive — https://developers.cloudflare.com/hyperdrive/
- Cloudflare Blog: Hyperdrive: making your regional database feel distributed
- postgres.js GitHub: https://github.com/porsager/postgres
