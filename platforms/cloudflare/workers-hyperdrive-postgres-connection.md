# Connecting to PostgreSQL from Workers via Cloudflare Hyperdrive

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Cloudflare Worker needs to query a PostgreSQL database (Supabase, Neon, RDS, self-hosted). Direct `pg` connections from Workers fail or are extremely slow because each request cold-starts a TCP connection to the remote DB, easily adding 200–800 ms of latency before the first query.

## Context

Cloudflare Hyperdrive is a connection-pooling and query-caching proxy that runs inside Cloudflare's network. It maintains a warm pool of PostgreSQL connections so that each Worker request reuses an existing connection instead of performing a TCP/TLS handshake from scratch. Hyperdrive also optionally caches read-only query results at the edge.

Key properties:
- Hyperdrive sits between the Worker and the database; the Worker talks to a local socket-like address.
- The Worker uses a standard `pg` or `postgres.js` client with the Hyperdrive connection string — no special SDK.
- Connection pooling is handled by Hyperdrive, not by the Worker. Workers are stateless, so they should **never** instantiate a pool themselves.
- Caching is opt-in per query (read-only queries without side effects).

## Solution

### 1. Create the Hyperdrive Configuration

```bash
# Create a Hyperdrive config pointing at your Postgres instance
npx wrangler hyperdrive create my-hyperdrive \
  --connection-string="postgres://user:password@db.example.com:5432/mydb"

# Output includes the Hyperdrive ID — note it for wrangler.toml
# {
#   "id": "abc123def456...",
#   "name": "my-hyperdrive",
#   ...
# }
```

### 2. Bind Hyperdrive in wrangler.toml

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[[hyperdrive]]
binding = "HYPERDRIVE"
id = "abc123def456abcdef1234567890abcd"

# Optional: enable query caching for read-only queries
# [hyperdrive.caching]
# disabled = false
# max_age = 60   # seconds
```

### 3. TypeScript Environment Type

```typescript
// src/types.ts
export interface Env {
  HYPERDRIVE: Hyperdrive;
  // Hyperdrive exposes .connectionString — a URL pointing to the
  // Cloudflare-managed proxy, not the real DB host.
}
```

### 4. Worker with postgres.js Client

```typescript
// src/index.ts
import postgres from 'postgres';
import type { Env } from './types';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Create a new client per request — Hyperdrive manages the real pool.
    // postgres.js is preferred over pg in Workers because it uses TCP sockets
    // via the Workers Socket API rather than requiring Node net module.
    const sql = postgres(env.HYPERDRIVE.connectionString, {
      // Must be 1 in Workers — stateless execution model
      max: 1,
      // Workers have a 30s CPU limit; keep queries well under this
      idle_timeout: 20,
      max_lifetime: 60 * 10,
      // Disable SSL — Hyperdrive handles TLS to the origin
      ssl: 'prefer',
    });

    try {
      const url = new URL(request.url);
      const pathname = url.pathname;

      if (pathname === '/users' && request.method === 'GET') {
        return await getUsers(sql);
      }

      if (pathname === '/users' && request.method === 'POST') {
        return await createUser(sql, request);
      }

      return Response.json({ error: 'Not found' }, { status: 404 });
    } finally {
      // Always close the client; Hyperdrive returns the underlying
      // connection to the pool rather than closing it to the DB.
      ctx.waitUntil(sql.end());
    }
  },
};

async function getUsers(sql: postgres.Sql): Promise<Response> {
  const users = await sql`
    SELECT id, name, email, created_at
    FROM users
    ORDER BY created_at DESC
    LIMIT 50
  `;
  return Response.json({ data: users });
}

async function createUser(sql: postgres.Sql, request: Request): Promise<Response> {
  const body = await request.json<{ name: string; email: string }>();

  if (!body.name || !body.email) {
    return Response.json({ error: 'name and email are required' }, { status: 422 });
  }

  const [user] = await sql`
    INSERT INTO users (name, email)
    VALUES (${body.name}, ${body.email})
    RETURNING id, name, email, created_at
  `;

  return Response.json({ data: user }, { status: 201 });
}
```

### 5. Using pg (node-postgres) as Alternative

```typescript
// src/index-pg.ts  (requires nodejs_compat flag)
import { Client } from 'pg';
import type { Env } from './types';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const client = new Client({
      connectionString: env.HYPERDRIVE.connectionString,
      // Hyperdrive handles TLS; disable cert verification at this layer
      ssl: false,
    });

    await client.connect();

    try {
      const { rows } = await client.query(
        'SELECT id, name, email FROM users WHERE id = $1',
        [new URL(request.url).searchParams.get('id')]
      );
      return Response.json({ data: rows[0] ?? null });
    } finally {
      ctx.waitUntil(client.end());
    }
  },
};
```

### 6. Transactions

```typescript
async function transferFunds(
  sql: postgres.Sql,
  fromId: number,
  toId: number,
  amount: number
): Promise<void> {
  await sql.begin(async (tx) => {
    const [from] = await tx`
      SELECT balance FROM accounts WHERE id = ${fromId} FOR UPDATE
    `;

    if (from.balance < amount) {
      throw new Error('Insufficient funds');
    }

    await tx`UPDATE accounts SET balance = balance - ${amount} WHERE id = ${fromId}`;
    await tx`UPDATE accounts SET balance = balance + ${amount} WHERE id = ${toId}`;

    await tx`
      INSERT INTO ledger (from_id, to_id, amount, created_at)
      VALUES (${fromId}, ${toId}, ${amount}, now())
    `;
  });
}
```

### 7. Local Development Without Hyperdrive

```typescript
// src/index.ts — local dev fallback
const connectionString = env.HYPERDRIVE?.connectionString
  ?? process.env.DATABASE_URL  // set in .dev.vars
  ?? 'postgres://postgres:postgres@localhost:5432/mydb';

const sql = postgres(connectionString, { max: 1 });
```

```ini
# .dev.vars (git-ignored)
DATABASE_URL=postgres://postgres:postgres@localhost:5432/mydb
```

```bash
# Start local dev server with .dev.vars loaded automatically
npx wrangler dev
```

## Implementation Details

**Connection string anatomy:** `env.HYPERDRIVE.connectionString` returns a URL like `postgres://user:password@127.0.0.1:PORT/dbname`. The host is a loopback address inside the Cloudflare PoP, not your origin DB. Hardcoding this value externally is useless — it changes per deployment.

**max: 1 requirement:** Workers are single-threaded and stateless. A pool larger than 1 in postgres.js wastes the connection slot and can leak connections if the isolate is recycled before all pool members close.

**Latency improvement:** Without Hyperdrive, a cold Worker → Postgres round trip is typically 150–600 ms for TCP+TLS setup. With Hyperdrive, the Worker → Hyperdrive hop is ~1 ms (same PoP), and the Hyperdrive → Postgres connection is already warm.

**Caching:** Hyperdrive can cache read-only query results at the PoP level. Cache hits skip the DB entirely. Enable per-config and tune `max_age` based on data freshness requirements.

**Region pinning:** For very latency-sensitive queries, deploy your Worker with a [Smart Placement](https://developers.cloudflare.com/workers/configuration/smart-placement/) hint so Cloudflare co-locates it near the DB region.

## Anti-patterns

- Do not instantiate `postgres({ max: 10 })` — the pool will not be reused across requests and you will exhaust DB connections rapidly.
- Do not store the `sql` client in a module-level variable intending to reuse it — the isolate lifecycle is not guaranteed.
- Do not disable TLS (`ssl: false`) when connecting to a remote DB without Hyperdrive — Hyperdrive itself maintains TLS to the origin.
- Do not commit `.dev.vars` — it contains the real DB password.

## Gotchas

- `nodejs_compat` compatibility flag is required for both `pg` and `postgres.js` in Workers. Without it, the TCP socket layer is unavailable.
- Hyperdrive does not support `LISTEN`/`NOTIFY` (pub/sub) or `COPY` streaming commands.
- Query parameter placeholders differ: `pg` uses `$1, $2`; `postgres.js` uses tagged template literals with automatic parameterization.
- Hyperdrive caching is bypassed automatically for queries inside transactions and for any query that modifies data.

## Verification

```bash
# Create Hyperdrive and inspect
npx wrangler hyperdrive create my-hyperdrive \
  --connection-string="postgres://user:pass@host:5432/db"
npx wrangler hyperdrive list
npx wrangler hyperdrive get <id>

# Run locally (Hyperdrive is simulated; uses local DB URL from .dev.vars)
npx wrangler dev

# Tail production logs
npx wrangler tail --format pretty

# Check latency before/after: compare Time-To-First-Byte in wrangler tail output
```

## Related

- `workers-pages-functions-api-routes.md` — using these DB patterns inside Pages Functions
- `workers-workflows-durable-execution.md` — durable order processing that writes to Postgres
- Hyperdrive docs: https://developers.cloudflare.com/hyperdrive/

## Sources

- https://developers.cloudflare.com/hyperdrive/get-started/
- https://developers.cloudflare.com/hyperdrive/configuration/
- https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/
- https://github.com/porsager/postgres
