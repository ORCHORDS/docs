# Hyperdrive PostgreSQL Read Replica Routing in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You have a primary PostgreSQL database and one or more read replicas. All writes must reach the
primary, but heavy analytical or reporting queries should hit a replica to reduce primary load.
Workers fetch data on every request edge-side, so naively all traffic goes to one Hyperdrive
binding — saturating the primary and leaving replicas idle.

## Context

Hyperdrive caches query results at the edge and maintains connection pools in every Cloudflare
region. Each Hyperdrive config points at exactly one PostgreSQL origin. To route reads vs. writes
you need **two Hyperdrive configs** — one pointing at the primary, one pointing at a read replica
— and your Worker selects the right binding per query intent.

Cloudflare enforces that Hyperdrive does not track PostgreSQL replication lag; callers must tolerate
eventual consistency (typically 10–200 ms lag on managed providers).

---

## Creating Two Hyperdrive Configs

```bash
# Primary (writes + latency-sensitive reads)
npx wrangler hyperdrive create example project-pg-primary \
  --connection-string "postgresql://user:pass@primary.db.example.com:5432/example project"

# Read replica (analytics, reports, heavy SELECT)
npx wrangler hyperdrive create example project-pg-replica \
  --connection-string "postgresql://user:pass@replica.db.example.com:5432/example project"
```

Bind both in `wrangler.toml`:

```toml
[[hyperdrive]]
binding = "DB_PRIMARY"
id     = "<primary-hyperdrive-id>"

[[hyperdrive]]
binding = "DB_REPLICA"
id     = "<replica-hyperdrive-id>"
```

---

## Worker Environment Types

```typescript
// src/types.ts
export interface Env {
  DB_PRIMARY: Hyperdrive;
  DB_REPLICA:  Hyperdrive;
}
```

---

## Query Router Utility

```typescript
// src/db/router.ts
import postgres from "postgres";

export type Intent = "write" | "read";

/**
 * Returns a postgres.js client backed by the correct Hyperdrive binding.
 * Always call .end() after the query to release the pooled connection.
 */
export function getClient(env: Env, intent: Intent) {
  const hyperdrive = intent === "write" ? env.DB_PRIMARY : env.DB_REPLICA;
  return postgres(hyperdrive.connectionString, {
    // Hyperdrive manages pooling; keep Worker-side connections at 1
    max: 1,
    // Disable prepare — Hyperdrive does not persist prepared statements
    prepare: false,
  });
}

export async function query<T>(
  env: Env,
  intent: Intent,
  fn: (sql: ReturnType<typeof postgres>) => Promise<T>
): Promise<T> {
  const sql = getClient(env, intent);
  try {
    return await fn(sql);
  } finally {
    await sql.end();
  }
}
```

---

## Read vs. Write Routing in a Handler

```typescript
// src/handlers/orders.ts
import { query } from "../db/router";

export async function handleGetOrders(request: Request, env: Env) {
  const orders = await query(env, "read", (sql) =>
    sql`SELECT id, status, total FROM orders ORDER BY created_at DESC LIMIT 50`
  );
  return Response.json(orders);
}

export async function handleCreateOrder(request: Request, env: Env) {
  const body = await request.json<{ userId: string; items: unknown[] }>();

  // Write always targets the primary
  const [order] = await query(env, "write", (sql) =>
    sql`
      INSERT INTO orders (user_id, items, status)
      VALUES (${body.userId}, ${JSON.stringify(body.items)}, 'pending')
      RETURNING id, status, created_at
    `
  );
  return Response.json(order, { status: 201 });
}
```

---

## Forcing Primary After a Write (Read-Your-Writes)

Hyperdrive caches read results at the edge. Immediately after a write the replica may not yet have
propagated the new row. Use the primary for reads that must reflect a just-completed write:

```typescript
export async function handleConfirmOrder(request: Request, env: Env) {
  const { id } = await request.json<{ id: string }>();

  // Write + confirm read from primary to avoid stale replica data
  await query(env, "write", (sql) =>
    sql`UPDATE orders SET status = 'confirmed' WHERE id = ${id}`
  );

  const [order] = await query(env, "write", (sql) =>
    sql`SELECT id, status FROM orders WHERE id = ${id}`
  );

  return Response.json(order);
}
```

---

## Anti-patterns

- **Sending all traffic to `DB_PRIMARY`**: defeats Hyperdrive caching on the replica and overloads
  the primary.
- **Opening multiple pooled connections per Worker invocation**: Workers are short-lived; use
  `max: 1` per client and close it in `finally`.
- **Assuming replica is always consistent**: do not read replica immediately after a write for
  user-visible confirmations — use primary or add an explicit sleep/poll loop.
- **Sharing one Hyperdrive binding for both primary and replica**: Hyperdrive connects to a fixed
  origin; you cannot switch targets at runtime through a single binding.

---

## Gotchas

- Hyperdrive caches **only** `SELECT` queries that do not use session-scoped features (temporary
  tables, `SET` variables). If your "read" queries use transactions or session state, caching is
  bypassed automatically.
- Replica lag varies. On primary failover, the new primary may briefly appear as replica; Hyperdrive
  does not reroute automatically — your upstream provider's DNS/proxy handles promotion.
- `prepare: false` is required. Hyperdrive multiplexes connections from many Workers into a shared
  pool; named prepared statements from one Worker would collide with another Worker's session.
- Each additional Hyperdrive binding costs an additional monthly fee per config. Budget accordingly.

---

## Verification

```typescript
// Confirm replica lag is acceptable
export async function handleReplicaLag(_req: Request, env: Env) {
  const [primary] = await query(env, "write", (sql) =>
    sql`SELECT extract(epoch from now()) AS ts`
  );
  const [replica] = await query(env, "read", (sql) =>
    sql`SELECT extract(epoch from now()) AS ts,
               extract(epoch from (now() - pg_last_xact_replay_timestamp())) AS lag_s`
  );
  return Response.json({ primaryTs: primary.ts, replicaLagSeconds: replica.lag_s });
}
```

---

## Related

- `d1-connection-pooling-workers-hyperdrive-comparison.md`
- `d1-connection-string-hyperdrive-migration.md`
- `d1-read-replicas-mobile-latency.md`
- `read-replica-lag-handling.md`
- `cqrs-read-write-split.md`

## Sources

- Cloudflare Hyperdrive docs: https://developers.cloudflare.com/hyperdrive/
- Hyperdrive configuration reference: https://developers.cloudflare.com/hyperdrive/configuration/
- postgres.js driver: https://github.com/porsager/postgres
