# hyperdrive-best-practices

**Issue:** Hyperdrive — accelerate Postgres/MySQL from Workers
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a Postgres DB in us-east-1. Your Workers run
globally. Every query takes 100ms. The round trip is
the bottleneck. You wish the connection were faster.

## Root cause
**TCP + TLS handshake is slow over long distances.**
Use Hyperdrive.

**Source:** Hyperdrive docs:
https://developers.cloudflare.com/hyperdrive/

## The "Hyperdrive" concept

Hyperdrive is a connection pooler:
- **Pooled connections:** Reuse across requests
- **Edge cache:** For read-heavy queries
- **Faster:** Up to 25x for distant DBs
- **Compatible:** Postgres, MySQL

The connection is at the edge.

## The "binding" pattern

For the binding:
```toml
[[hyperdrive]]
binding = "HYPERDRIVE"
id = "your-hyperdrive-id"
```

The binding is in `wrangler.toml`.

## The "Postgres" pattern

For Postgres:
```ts
import { Client } from 'pg';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const client = new Client({ connectionString: env.HYPERDRIVE.connectionString });
    await client.connect();

    const result = await client.query('SELECT * FROM users WHERE id = $1', ['u_1']);
    await client.end();

    return Response.json(result.rows);
  },
};
```

The query is via Hyperdrive.

## The "MySQL" pattern

For MySQL:
```ts
import { createConnection } from 'mysql2/promise';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const conn = await createConnection({
      host: env.HYPERDRIVE.host,
      user: env.DB_USER,
      password: env.DB_PASSWORD,
      database: env.DB_NAME,
      port: env.HYPERDRIVE.port,
    });

    const [rows] = await conn.execute('SELECT * FROM users WHERE id = ?', ['u_1']);
    await conn.end();

    return Response.json(rows);
  },
};
```

The MySQL query is via Hyperdrive.

## The "Drizzle" pattern

For Drizzle:
```ts
import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';

const client = postgres(env.HYPERDRIVE.connectionString);
const db = drizzle(client);

const users = await db.select().from(usersTable).where(eq(usersTable.id, 'u_1'));
```

Drizzle works with Hyperdrive.

## The "edge cache" pattern

For caching:
- **Hyperdrive caches** query results at the edge
- **TTL:** Configurable per query
- **Cache key:** Query + params

```ts
const result = await client.query({
  text: 'SELECT * FROM users WHERE id = $1',
  values: ['u_1'],
  // Hyperdrive cache hint
  cache: { ttl: 300 },
});
```

The query is cached.

## The "prepared statement" pattern

For prepared statements:
```ts
const stmt = await client.prepare('SELECT * FROM users WHERE id = $1');
const result = await stmt.execute({ id: 'u_1' });
await stmt.close();
```

The statement is prepared (faster).

## The "transaction" pattern

For transactions:
```ts
await client.query('BEGIN');
try {
  await client.query('UPDATE users SET status = $1 WHERE id = $2', ['active', 'u_1']);
  await client.query('UPDATE accounts SET balance = balance - 100 WHERE user_id = $1', ['u_1']);
  await client.query('COMMIT');
} catch (err) {
  await client.query('ROLLBACK');
  throw err;
}
```

The transaction is atomic.

## The "Hyperdrive limits" pattern

For limits:
- **Connections:** Pooled (configurable)
- **Latency:** Up to 25x faster
- **DBs:** Postgres, MySQL, others
- **Region:** Origin DB stays put

The limits are checked.

## The "Hyperdrive vs direct" choice

| Use case | Use |
|---|---|
| **Workers + remote DB** | Hyperdrive |
| **Workers + D1** | Direct (D1 is at the edge) |
| **Workers + same-region DB** | Either |
| **Long-distance DB** | Hyperdrive |

For most remote-DB use cases, **Hyperdrive** is the
right answer.

## The "Hyperdrive observability" pattern

For observability:
- **Query count:** Per minute
- **Query latency:** p50, p95, p99
- **Cache hit rate:** Per query
- **Connection count:** Per pool

The metrics are in the CF dashboard.

## The "Hyperdrive anti-pattern" anti-patterns

### 1. New connection per query
- **Issue:** Slow
- **Fix:** Hyperdrive pool

### 2. No prepared statement
- **Issue:** Re-parsed
- **Fix:** Prepared statements

### 3. Long-distance direct
- **Issue:** Slow
- **Fix:** Hyperdrive

### 4. Not using edge cache
- **Issue:** Repeat reads
- **Fix:** Cache hint

## Verification
- **Test:** Query works
- **Test:** Pool reuses
- **Test:** Cache works
- **Live:** Latency is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "new connection per query" anti-pattern.** Use
  pool.
- **The "no prepared" anti-pattern.** Prepare.
- **The "long-distance direct" anti-pattern.** Use
  Hyperdrive.

## Related
- `cloudflare/workers-best-practices.md`
- `cloudflare/d1-best-practices.md`
- `feature-cookbook-data-modeling.md`
- Hyperdrive: https://developers.cloudflare.com/hyperdrive/
- Drizzle: https://orm.drizzle.team/
