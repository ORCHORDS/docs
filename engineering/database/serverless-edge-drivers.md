# serverless-edge-drivers

## Symptom

Serverless functions (Cloudflare Workers, AWS Lambda, Vercel Edge) exhaust database connections or suffer multi-second cold starts because traditional TCP database drivers (pg, mysql2) open persistent connections that don't fit the serverless lifecycle.

## Pattern / Solution

Use HTTP/WebSocket-based drivers designed for serverless and edge runtimes:

### Neon Serverless Driver (`@neondatabase/serverless`)
- Uses WebSocket (or HTTP fetch) instead of TCP — works in Workers/Lambda
- Connection pooling built into Neon's proxy
- Drop-in replacement for `pg`:

```javascript
import { neon } from '@neondatabase/serverless';
const sql = neon(process.env.DATABASE_URL);
const users = await sql`SELECT * FROM users WHERE id = ${userId}`;
// Parameterized — no injection risk
```

### Turso libSQL (HTTP)
- SQLite-compatible, HTTP-based, edge-friendly
- Embedded replica: read locally, write to primary

```javascript
import { createClient } from '@libsql/client';
const db = createClient({ url: process.env.TURSO_URL, authToken: process.env.TURSO_TOKEN });
const result = await db.execute({ sql: 'SELECT * FROM users WHERE id = ?', args: [userId] });
```

### Cloudflare Hyperdrive (connection pooling for Workers)
- Caches TCP connections to your existing Postgres near Cloudflare's edge
- No driver change — works with `pg` via Hyperdrive binding
- Eliminates per-request TCP + TLS handshake

### Prisma Accelerate
- Global connection pool + query cache in front of your database
- Works with any Prisma-supported database
- Reduces direct DB connections to near-zero from serverless

## When to use what

| Environment | Driver | Why |
|---|---|---|
| Cloudflare Workers | Neon serverless or Hyperdrive + pg | No TCP support in Workers (unless Hyperdrive) |
| AWS Lambda | pg with connection pooler (PgBouncer/RDS Proxy) | Lambda has TCP but cold start kills connections |
| Vercel Edge | Neon serverless or Turso libSQL | Edge runtime has no Node APIs |
| Long-running server | Standard pg/mysql2 driver | No serverless constraints |

## Gotchas

- Neon serverless driver over HTTP has ~10-30ms higher latency per query vs TCP — batch queries where possible.
- Turso embedded replicas have eventual consistency for reads — stale reads possible on the edge replica.
- Hyperdrive adds a proxy hop but caches connection setup — first request per region is slower, subsequent are faster.
- Prisma Accelerate adds a subscription cost but eliminates connection management entirely.
- Serverless databases (Neon, Turso) scale-to-zero: first query after idle has 1-3s cold start (compute spin-up).
- Do NOT use `pool` with serverless drivers — one client per invocation, let the platform manage pooling.

## Related

- `database/connection-pooling-pgbouncer.md`
- `database/database-connection-pooling.md`
- `cloudflare/hyperdrive-best-practices.md`
