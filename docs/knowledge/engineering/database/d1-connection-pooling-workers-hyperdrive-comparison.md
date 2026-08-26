# D1 Connection Pooling vs Hyperdrive for PostgreSQL at the Edge

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Workers applications that outgrow SQLite constraints (complex joins, advanced types, existing Postgres data) face a choice: stick with D1 and its built-in connection model, or migrate to PostgreSQL fronted by Hyperdrive. Teams frequently mischaracterize one as simply "faster" than the other without understanding that D1 and Hyperdrive solve different connection problems and carry fundamentally different latency profiles depending on read vs write ratio, geographic distribution, and query complexity.

## Context

D1 is a globally distributed SQLite service built on top of Cloudflare's Durable Objects infrastructure. Each D1 write is serialised through a single primary per database (located in the region chosen at creation time), while reads can be served from regional read replicas. Hyperdrive is a connection pool and query cache that sits between a Worker and an external PostgreSQL database, maintaining a small pool of persistent TCP connections so Workers do not pay the full TCP + TLS handshake cost on every invocation. Workers themselves are stateless and cannot hold open database connections between requests; both products exist specifically to bridge that gap, but they do so at different protocol layers.

## D1 Built-in Connection Handling

D1 abstracts connections entirely. The Worker SDK (`env.DB`) communicates with D1 over Cloudflare's internal network using an HTTP/2 multiplexed protocol. There are no explicit connection objects, no pool configuration, and no connection limits visible to application code. The trade-off is that every write traverses the globe to the primary region if the Worker is running far from it.

```typescript
// D1 — no connection setup, no teardown, no pool config required.
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === '/users') {
      // Reads are served from the nearest read replica automatically.
      const { results } = await env.DB.prepare(
        'SELECT id, name, email FROM users ORDER BY created_at DESC LIMIT 50',
      ).all();
      return Response.json(results);
    }

    if (pathname === '/users' && request.method === 'POST') {
      const { name, email } = await request.json<{ name: string; email: string }>();
      // Writes are routed to the primary; expect +50–150 ms if the Worker
      // is in a different continent from the D1 primary region.
      const info = await env.DB.prepare(
        'INSERT INTO users (id, name, email) VALUES (?, ?, ?)',
      )
        .bind(crypto.randomUUID(), name, email)
        .run();

      return Response.json({ success: info.success, meta: info.meta });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Hyperdrive Connection Pooling for PostgreSQL

Hyperdrive maintains a pool of persistent TCP connections to a remote Postgres instance (typically 5–20 connections, configurable). Workers connect via the `hyperdrive.connectionString` property, which is a local UNIX-socket-style URL that proxies to the real database. Connection setup overhead drops from ~100–300 ms (cold TCP + TLS to a remote host) to ~1–5 ms (local proxy socket).

```typescript
// src/index.ts — Hyperdrive + postgres driver pattern.
import { Client } from 'pg'; // npm i pg

export interface Env {
  HYPERDRIVE: Hyperdrive;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Each invocation gets a "connection" from the pool via the local proxy.
    // The underlying TCP socket to the remote Postgres is already open.
    const client = new Client({ connectionString: env.HYPERDRIVE.connectionString });
    await client.connect();

    try {
      const { pathname } = new URL(request.url);

      if (pathname === '/products') {
        // Hyperdrive caches SELECT results by default (max-age configurable).
        const { rows } = await client.query<{ id: string; name: string; price: number }>(
          'SELECT id, name, price FROM products WHERE active = true ORDER BY name LIMIT 100',
        );
        return Response.json(rows);
      }

      if (pathname === '/orders' && request.method === 'POST') {
        const { productId, quantity } = await request.json<{
          productId: string;
          quantity: number;
        }>();

        // Mutations bypass Hyperdrive's query cache automatically.
        await client.query('BEGIN');
        await client.query(
          'INSERT INTO orders (id, product_id, quantity) VALUES ($1, $2, $3)',
          [crypto.randomUUID(), productId, quantity],
        );
        await client.query(
          'UPDATE products SET stock = stock - $1 WHERE id = $2',
          [quantity, productId],
        );
        await client.query('COMMIT');

        return Response.json({ ok: true });
      }

      return new Response('Not found', { status: 404 });
    } catch (err) {
      await client.query('ROLLBACK').catch(() => {});
      throw err;
    } finally {
      // Release the connection back to the pool.
      await client.end();
    }
  },
};
```

## Latency Characteristics and When to Choose Each

Typical p50 latency by scenario (measured from a US-East Worker, database in us-east-1):

| Scenario | D1 Read (replica) | D1 Write (primary) | Hyperdrive Read (cached) | Hyperdrive Read (uncached) | Hyperdrive Write |
|---|---|---|---|---|---|
| Same-region | ~5 ms | ~10 ms | ~2 ms | ~8 ms | ~10 ms |
| Cross-region | ~8 ms | ~80–150 ms | ~2 ms | ~80–120 ms | ~80–120 ms |

```typescript
// Benchmark helper — measure actual round-trips in your own account.
async function benchmark(db: D1Database, label: string, iterations = 100): Promise<void> {
  const times: number[] = [];
  for (let i = 0; i < iterations; i++) {
    const t0 = performance.now();
    await db.prepare('SELECT 1').first();
    times.push(performance.now() - t0);
  }
  times.sort((a, b) => a - b);
  console.log(`[${label}] p50=${times[50].toFixed(1)}ms p95=${times[95].toFixed(1)}ms`);
}

// D1 read replica routing — opt in with the `experimental` flag in wrangler.toml:
// [d1_databases]
// [[d1_databases]]
// binding = "DB"
// database_name = "my-db"
// database_id = "..."
// experimental = { read_replication = { mode = "auto" } }
```

Decision matrix:

- **Choose D1** when: the application is new (no existing Postgres), data model fits SQLite, writes are infrequent or latency-tolerant, or cost is a primary concern. D1's free tier is generous and there is zero infrastructure to operate.
- **Choose Hyperdrive + Postgres** when: the team already runs Postgres (Neon, Supabase, RDS), requires advanced types (arrays, JSONB operators, PostGIS), needs stored procedures, or has write-heavy workloads that must execute close to the database.
- **Avoid mixing both** for the same logical dataset — use D1 as a caching layer in front of Postgres only if you are prepared to manage cache invalidation explicitly.

## Anti-patterns

- Calling `client.connect()` without a corresponding `client.end()` in a `finally` block — Hyperdrive's pool has a finite size and leaking connections causes subsequent requests to queue or time out.
- Relying on D1 read replicas for strongly consistent reads immediately after a write — replication lag exists and can be 50–200 ms; always read from the primary for data written in the same request if consistency is required (use `{ experimental: { readReplication: false } }` per-query).
- Configuring Hyperdrive's `max-age` cache to a large value for mutable data — Hyperdrive caches at the SQL text level, not the result level; two textually identical queries share one cache entry regardless of side-effects that have occurred between them.
- Treating Hyperdrive as a pgBouncer replacement in transaction-pooling mode — Hyperdrive uses session pooling semantics; prepared statements and `SET` commands persist for the lifetime of the session, which may span multiple Worker invocations.

## Gotchas

- Workers have a maximum of 6 concurrent outbound TCP connections per isolate when using `cloudflare:sockets` directly; Hyperdrive bypasses this limit because its proxy is internal to Cloudflare's network.
- D1's `batch()` API sends multiple statements in a single HTTP round-trip and is the closest equivalent to a pipelined connection — use it when issuing multiple independent writes to reduce per-statement latency overhead.
- Hyperdrive does not support PostgreSQL `LISTEN`/`NOTIFY` — the connection is returned to the pool before any async notification can arrive. Use Cloudflare Queues or Pub/Sub for event delivery instead.

## Verification

```bash
# Check D1 read replica status for a database.
wrangler d1 info <DATABASE_NAME>

# List configured Hyperdrive configs in your account.
wrangler hyperdrive list

# Create a Hyperdrive config pointing to a Postgres connection string.
wrangler hyperdrive create my-pg-pool \
  --connection-string "postgresql://user:pass@host:5432/dbname"

# Test Hyperdrive connection latency from a local Worker.
wrangler dev --remote
# Then curl the benchmark endpoint and inspect Worker logs.

# Inspect D1 query metrics in the dashboard or via the API.
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/d1/database/$DB_ID" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.version, .result.file_size'
```

## Related

- `database/d1-connection-pooling-workers.md`
- `database/d1-read-replicas-mobile-latency.md`
- `database/connection-pool-tuning-pgbouncer-hikaricp.md`
- `database/serverless-edge-drivers.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/hyperdrive/
- https://developers.cloudflare.com/hyperdrive/configuration/connection-pooling/
- https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/
- https://developers.cloudflare.com/d1/platform/client-api/
