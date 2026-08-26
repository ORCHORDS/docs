# Cloudflare Hyperdrive for PostgreSQL Payment Database Access in Workers

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

A Cloudflare Workers payment handler that connects directly to a remote PostgreSQL database (Supabase, Neon, RDS, AlloyDB) sees p99 latency of 400–900 ms because every Worker invocation must open a fresh TCP connection, negotiate TLS, and complete the PostgreSQL startup handshake before executing any query. Adding connection pooling via PgBouncer in `transaction` mode helps, but the round-trip from a Workers PoP in Singapore to a database in `us-east-1` still dominates. Hyperdrive solves this by placing a Cloudflare-managed connection pool close to the database and keeping connections warm across Worker invocations.

---

## Context

Cloudflare Hyperdrive is a database acceleration service that:
1. Accepts a Workers `connect()` call and proxies it through a persistent connection pool co-located with the target database.
2. Caches `SELECT` query results at the edge (configurable TTL, disabled for payment reads that must be consistent).
3. Exposes a `connectionString` property that any `node-postgres` (`pg`) or `postgres.js` driver accepts as-is.

It is the right primitive when:
- You have an existing PostgreSQL payment database that you cannot or will not migrate to D1.
- Your Workers need sub-100 ms query latency for time-sensitive operations (fraud checks, inventory decrements, idempotency key lookups).
- You want zero-downtime connection management — Hyperdrive holds the pool; the Worker just borrows a connection per request.

Hyperdrive **cannot** cache mutating queries (`INSERT`, `UPDATE`, `DELETE`). For payment workloads, configure `max_age = 0` on any route that reads balances or order state to avoid stale reads.

---

## 1. Provisioning Hyperdrive

```bash
# Create a Hyperdrive config pointing at your Postgres cluster
wrangler hyperdrive create payments-db \
  --connection-string "postgresql://app_user:secret@db.us-east-1.rds.amazonaws.com:5432/payments_prod"

# Inspect the returned hyperdrive ID — use it in wrangler.toml
wrangler hyperdrive list
```

```toml
# wrangler.toml
name = "payment-api"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[[hyperdrive]]
binding = "HYPERDRIVE"
id = "YOUR_HYPERDRIVE_CONFIG_ID"
```

---

## 2. Connecting with `postgres.js`

`postgres.js` is the recommended driver for Workers because it does not depend on Node.js `net` — it uses the standard `connect()` API that Cloudflare exposes.

```typescript
// src/lib/db.ts
import postgres from 'postgres';

export interface Env {
  HYPERDRIVE: Hyperdrive;
}

// Create a new client per Worker invocation — Hyperdrive pools the underlying
// TCP connections, so this is cheap (no handshake on our side).
export function getDb(env: Env) {
  return postgres(env.HYPERDRIVE.connectionString, {
    // Hyperdrive handles TLS; disable client-side TLS to avoid double-wrapping
    ssl: 'require',
    // One connection per Worker invocation is sufficient
    max: 1,
    // Do not keep the Worker alive after the request completes
    idle_timeout: 0,
    max_lifetime: 30,
    // Disable prepared statements — Hyperdrive multiplexes connections so
    // named prepared statements from one Worker may land on a different backend
    prepare: false,
  });
}
```

---

## 3. Idempotency Key Check (Critical Path)

Payment handlers must verify an idempotency key before processing. With Hyperdrive the round-trip is typically 5–15 ms from a nearby PoP.

```typescript
// src/lib/idempotency.ts
import type { Sql } from 'postgres';

export interface IdempotencyRecord {
  request_id: string;
  response_status: number;
  response_body: string;
  created_at: Date;
}

export async function checkIdempotency(
  sql: Sql,
  requestId: string
): Promise<IdempotencyRecord | null> {
  const rows = await sql<IdempotencyRecord[]>`
    SELECT request_id, response_status, response_body, created_at
      FROM idempotency_keys
     WHERE request_id = ${requestId}
       AND created_at > NOW() - INTERVAL '24 hours'
  `;
  return rows[0] ?? null;
}

export async function saveIdempotency(
  sql: Sql,
  requestId: string,
  status: number,
  body: string
): Promise<void> {
  await sql`
    INSERT INTO idempotency_keys (request_id, response_status, response_body)
    VALUES (${requestId}, ${status}, ${body})
    ON CONFLICT (request_id) DO NOTHING
  `;
}
```

---

## 4. Payment Order Write Handler

```typescript
// src/handlers/charge.ts
import { getDb } from '../lib/db';
import { checkIdempotency, saveIdempotency } from '../lib/idempotency';
import type { Env } from '../types';

export async function handleCharge(request: Request, env: Env): Promise<Response> {
  const idempotencyKey = request.headers.get('Idempotency-Key') ?? '';
  if (!idempotencyKey) {
    return Response.json({ error: 'Idempotency-Key header required' }, { status: 400 });
  }

  const sql = getDb(env);

  try {
    // Check for duplicate
    const existing = await checkIdempotency(sql, idempotencyKey);
    if (existing) {
      return new Response(existing.response_body, {
        status: existing.response_status,
        headers: { 'Content-Type': 'application/json', 'Idempotent-Replayed': 'true' },
      });
    }

    const body = await request.json<{ amount_cents: number; customer_id: string }>();

    // Write the payment order inside a transaction
    const [order] = await sql.begin(async (tx) => {
      return tx<{ id: string; status: string }[]>`
        INSERT INTO payment_orders (customer_id, amount_cents, status, created_at)
        VALUES (${body.customer_id}, ${body.amount_cents}, 'pending', NOW())
        RETURNING id, status
      `;
    });

    const responseBody = JSON.stringify({ order_id: order.id, status: order.status });
    await saveIdempotency(sql, idempotencyKey, 201, responseBody);

    return new Response(responseBody, {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    });
  } finally {
    await sql.end();
  }
}
```

---

## 5. Disabling Query Caching for Payment Reads

Hyperdrive caches `SELECT` results by default (default TTL: 60 s). Balance and order-status reads must bypass the cache.

```typescript
// src/lib/db-nocache.ts
import postgres from 'postgres';
import type { Env } from '../types';

/** Returns a connection that bypasses Hyperdrive's query cache. Use for balance reads. */
export function getDbNoCache(env: Env) {
  // Hyperdrive exposes a `cacheDisabled` variant of the connection string.
  return postgres(env.HYPERDRIVE.connectionString, {
    ssl: 'require',
    max: 1,
    idle_timeout: 0,
    prepare: false,
    // Mark the connection as cache-bypass at the application level by using
    // the `HYPERDRIVE_CACHE_DISABLED=true` URL parameter if your config enables it,
    // or rely on the HYPERDRIVE binding's `.connectionString` (cache already off for
    // mutating statements; for SELECTs on payment state, wrap in a dummy tx):
    // BEGIN; SELECT ...; COMMIT; — Hyperdrive never caches statements inside transactions.
    fetch_types: false,
  });
}

export async function getOrderStatus(sql: ReturnType<typeof getDbNoCache>, orderId: string) {
  // Wrapping in an explicit transaction prevents Hyperdrive result caching
  const [row] = await sql.begin((tx) =>
    tx<{ status: string; amount_cents: number }[]>`
      SELECT status, amount_cents FROM payment_orders WHERE id = ${orderId}
    `
  );
  return row ?? null;
}
```

---

## 6. Health Check Endpoint

```typescript
// src/handlers/health.ts
import { getDb } from '../lib/db';
import type { Env } from '../types';

export async function handleHealth(_req: Request, env: Env): Promise<Response> {
  const sql = getDb(env);
  try {
    const [{ now }] = await sql<{ now: Date }[]>`SELECT NOW() AS now`;
    await sql.end();
    return Response.json({ status: 'ok', db_time: now.toISOString() });
  } catch (err: any) {
    return Response.json({ status: 'error', message: err.message }, { status: 503 });
  }
}
```

---

## Anti-patterns

- **Reusing a single global `sql` client across invocations** — Workers is stateless; global state can leak between requests in the same isolate. Always call `sql.end()` in a `finally` block.
- **Enabling `prepare: true`** — Hyperdrive multiplexes connections; named prepared statements are session-scoped and will silently fail on a different backend connection.
- **Relying on Hyperdrive caching for payment balances** — stale cache can cause double-charges or incorrect balance displays. Disable caching for consistency-critical reads.
- **Opening Postgres directly without Hyperdrive in production** — each Worker invocation then pays the full TCP + TLS + startup cost (~200–600 ms depending on region).

---

## Gotchas

- Hyperdrive only supports PostgreSQL 12+. MySQL/MariaDB support is available separately via a different Hyperdrive tier.
- Hyperdrive connections count against your database's `max_connections`. Set `max` to 1 in the `postgres.js` config; Hyperdrive manages the actual pool size (configurable per Hyperdrive config).
- The `nodejs_compat` compatibility flag is required for `postgres.js` in Workers.
- Hyperdrive is not available in the `workerd` local dev server by default. Use `wrangler dev --remote` or set `HYPERDRIVE.connectionString` in `.dev.vars` to a local Postgres URL for local testing.
- `sql.end()` inside `finally` is essential. Without it, the Worker isolate may hang until the connection times out, delaying the response.

---

## Verification

```bash
# Deploy and time a query via Hyperdrive
curl -w '\nTotal: %{time_total}s\n' https://payment-api.workers.dev/health

# Compare without Hyperdrive (direct Postgres) using wrangler dev --local
# Expect 5-20x latency difference from edge PoPs distant from the DB region

# Confirm no prepared-statement errors in Workers logs
wrangler tail --format pretty
```

---

## Related

- `payment-method-vaulting-d1-workers.md`
- `idempotency-keys-payment-apis.md`
- `double-entry-ledger-payments.md`
- `payment-reconciliation-settlement.md`

---

## Sources

- Cloudflare Hyperdrive overview: https://developers.cloudflare.com/hyperdrive/
- Hyperdrive `get-started` guide: https://developers.cloudflare.com/hyperdrive/get-started/
- `postgres.js` Workers compatibility: https://developers.cloudflare.com/workers/databases/connect-to-postgres/
- Hyperdrive caching behaviour: https://developers.cloudflare.com/hyperdrive/configuration/query-caching/
