# Cloudflare Hyperdrive for Connection Pooling with PostgreSQL alongside D1

- Date: 2026-08-22
- Author: example.com
- Status: production

## Problem: Choosing between Hyperdrive-backed PostgreSQL and D1, and using both

Cloudflare Workers cannot hold a persistent TCP connection across invocations — every request
starts cold. Against a Postgres database in `us-east-1` from a Worker in Frankfurt, the TCP+TLS
handshake alone is 120–200 ms before a query even starts. Hyperdrive solves this by maintaining
a regional pool of authenticated connections inside Cloudflare's network: your Worker connects
to a local Hyperdrive endpoint (sub-millisecond) that already holds an open Postgres connection.

D1 is Cloudflare's own SQLite-based database with zero connection setup cost and global read
replicas, but it has no support for stored procedures, triggers, complex Postgres extensions, or
migrating an existing Postgres schema. Many production apps need both: D1 for edge-local reads
(user sessions, feature flags, tenant config) and Hyperdrive/Postgres for transactional writes
and complex queries against an existing data warehouse.

This article covers when to use each, Hyperdrive configuration, Worker binding patterns, latency
comparison methodology, and common pooling pitfalls.

## Context

- Postgres 15+ on RDS, Supabase, Neon, or self-hosted (TCP reachable from Cloudflare)
- `pg` or `postgres.js` driver bundled via Wrangler/esbuild
- D1 for edge reads (session tokens, feature flags)
- Hyperdrive for Postgres writes and complex analytical queries
- Wrangler 3.x

## When to Use Hyperdrive vs D1

| Concern                        | Hyperdrive + Postgres    | D1                          |
|--------------------------------|--------------------------|-----------------------------|
| Existing Postgres schema       | Yes — migrate as-is      | Requires schema rewrite     |
| Complex joins / CTEs           | Full Postgres SQL         | SQLite dialect only         |
| Stored procedures / triggers   | Yes                       | No                          |
| Global read replicas           | No (single region)        | Yes (automatic)             |
| Connection overhead            | ~1 ms via pool            | 0 ms (embedded)             |
| Write latency from edge        | Regional Postgres latency | ~10 ms (primary)            |
| Pricing model                  | Per-query, egress costs   | Per-row read/written        |
| Row size limits                | Postgres limits           | 1 MB per row                |
| Max DB size                    | Unlimited                 | 10 GB per DB                |

**Rule of thumb:** Use D1 for new, edge-native data that fits SQLite. Use Hyperdrive when you
have an existing Postgres DB, need Postgres-specific features, or your DB exceeds D1 limits.

## Hyperdrive Configuration

```bash
# Create a Hyperdrive config pointing at your Postgres instance
wrangler hyperdrive create my-pg-pool \
  --connection-string "postgresql://user:password@db.example.com:5432/mydb"

# Output includes the Hyperdrive config ID — copy it to wrangler.toml
# Hyperdrive ID: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

# Hyperdrive — provides connection pooling to Postgres
[[hyperdrive]]
binding = "HYPERDRIVE"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# D1 — edge-local SQLite for sessions and config
[[d1_databases]]
binding = "DB"
database_name = "edge-local"
database_id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
```

## Worker Using Both Hyperdrive and D1

```ts
// src/index.ts
import { Client } from 'pg';

interface Env {
  HYPERDRIVE: Hyperdrive;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Fast path: check D1 for cached session (edge-local, ~0 ms)
    const sessionToken = request.headers.get('Authorization')?.replace('Bearer ', '');
    if (!sessionToken) return new Response('Unauthorized', { status: 401 });

    const session = await env.DB.prepare(
      'SELECT user_id, expires_at FROM sessions WHERE token = ? AND expires_at > unixepoch()'
    ).bind(sessionToken).first<{ user_id: string; expires_at: number }>();

    if (!session) return new Response('Invalid session', { status: 401 });

    // Slow path: Postgres query via Hyperdrive (pooled, regional)
    const pg = new Client({ connectionString: env.HYPERDRIVE.connectionString });
    try {
      await pg.connect();

      if (url.pathname === '/orders') {
        const { rows } = await pg.query(
          `SELECT o.id, o.total_usd, o.status, o.created_at
           FROM orders o
           WHERE o.user_id = $1
           ORDER BY o.created_at DESC
           LIMIT 20`,
          [session.user_id]
        );
        return Response.json({ orders: rows });
      }

      return new Response('Not Found', { status: 404 });
    } finally {
      // Always release — Hyperdrive recycles the underlying connection
      await pg.end();
    }
  },
};
```

## pgBouncer Equivalent Behavior

Hyperdrive behaves like pgBouncer in **transaction mode**: the underlying Postgres connection is
held only for the duration of a transaction, then returned to the pool. This means:

```ts
// WORKS — transaction-scoped connection held for both queries
const pg = new Client({ connectionString: env.HYPERDRIVE.connectionString });
await pg.connect();

await pg.query('BEGIN');
const { rows } = await pg.query('SELECT balance FROM accounts WHERE id=$1 FOR UPDATE', [accountId]);
await pg.query('UPDATE accounts SET balance=balance-$1 WHERE id=$2', [amount, accountId]);
await pg.query('COMMIT');

await pg.end();
```

```ts
// AVOID — prepared statements with names don't survive across connections in transaction mode
await pg.query({ name: 'get-user', text: 'SELECT * FROM users WHERE id=$1' }, [id]);
// Use unnamed prepared statements (text only) or parameterized queries instead
```

## Latency Comparison

Measure actual latency from your Worker to compare strategies:

```ts
// src/benchmark.ts
export async function benchmarkLatencies(env: Env): Promise<Record<string, number>> {
  const results: Record<string, number> = {};

  // D1 read latency
  const d1Start = Date.now();
  await env.DB.prepare('SELECT 1').first();
  results['d1_ms'] = Date.now() - d1Start;

  // Hyperdrive connect + query latency
  const pgStart = Date.now();
  const pg = new Client({ connectionString: env.HYPERDRIVE.connectionString });
  await pg.connect();
  await pg.query('SELECT 1');
  await pg.end();
  results['hyperdrive_ms'] = Date.now() - pgStart;

  return results;
  // Typical results from edge PoP near Postgres region:
  // { d1_ms: 2, hyperdrive_ms: 8 }
  // From distant PoP without Hyperdrive:
  // { d1_ms: 2, hyperdrive_ms: 180 }
}
```

## Anti-patterns

- Do not call `pg.connect()` and `pg.end()` inside a loop — create one client per request and reuse across queries in that request
- Do not use session-mode Postgres features (advisory locks, `SET` variables, temporary tables) — Hyperdrive pools connections in transaction mode; session state is lost between calls
- Do not store both hot and cold data in D1 when data volume exceeds 1 GB — D1 query performance degrades on large tables without careful indexing; move bulk historical data to Postgres
- Do not use `COPY` or `\COPY` protocol — not supported through Hyperdrive; use batch `INSERT` instead

## Gotchas

- Hyperdrive caches `SELECT` queries by default for 60 s — add `Cache-Control: no-store` to the Hyperdrive config or disable caching for write-after-read consistency
- The `HYPERDRIVE.connectionString` changes format between Wrangler versions — always read it at runtime, never hardcode the host
- Connection pool size is managed by Hyperdrive; you cannot configure max connections from the Worker side — size is set in the Hyperdrive dashboard
- `pg` and `postgres.js` must be bundled at build time; `require('pg')` does not work natively in Workers without `node_compat = true` in wrangler.toml

## Verification

```ts
// Health check endpoint returns latency for both databases
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (new URL(request.url).pathname !== '/health') {
      return new Response('Not Found', { status: 404 });
    }
    const latencies = await benchmarkLatencies(env);
    return Response.json({ ok: true, ...latencies });
  },
};
// Expected: { ok: true, d1_ms: 1-5, hyperdrive_ms: 5-15 } from nearby PoP
```

## Related

- documentation/categories/cloudflare/hyperdrive-best-practices.md
- documentation/categories/cloudflare/d1-best-practices.md
- documentation/categories/cloudflare/workers-postgres-d1-pattern.md
- documentation/categories/cloudflare/d1-read-replication.md

## Sources

- https://developers.cloudflare.com/hyperdrive/
- https://developers.cloudflare.com/hyperdrive/configuration/how-hyperdrive-works/
- https://developers.cloudflare.com/d1/
- https://node-postgres.com/
- https://developers.cloudflare.com/workers/runtime-apis/nodejs/
