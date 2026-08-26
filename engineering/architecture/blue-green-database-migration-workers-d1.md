# Blue-Green Database Migration for Cloudflare Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to apply a destructive or structurally incompatible D1 schema change — one that
cannot be done incrementally with the expand-contract pattern — while keeping the Worker
serving live traffic without downtime. Examples include changing a primary-key strategy,
migrating from a denormalized to a normalized schema, or switching from a row-based to a
JSON-column design.

Blue-green database migration extends the blue-green deployment concept to the database
layer: two D1 databases (blue = current, green = new) exist simultaneously. Traffic
migrates from blue to green in a controlled cut-over, with the ability to roll back to blue
if problems appear.

---

## Context

Blue-green deployment for Workers (without the DB) is well-supported via Workers Versions
and gradual rollouts. The database dimension adds complexity because:

- D1 is mutable; writes to the blue database after the green database is prepared will not
  appear in green unless replicated.
- D1 does not natively replicate across databases; application-level dual-write is required
  during the cut-over window.
- The cut-over window must be as short as possible to minimize the dual-write surface.

The pattern has four phases: Provision → Sync → Dual-write cut-over → Decommission.

---

## Phase 0 — Provision Green Database

```bash
# Create the green D1 database
wrangler d1 create orders-db-green

# Note the database_id from the output, then add to wrangler.toml:
# [[d1_databases]]
# binding = "DB_GREEN"
# database_name = "orders-db-green"
# database_id = "<green-db-id>"

# Apply new schema to green
wrangler d1 migrations apply orders-db-green --env production
```

---

## Phase 1 — Bulk Sync (Read-Only from Blue)

Export blue data and import into green. For large tables, do this in batches.

```typescript
// scripts/sync-blue-to-green.ts
// Run via:  npx tsx scripts/sync-blue-to-green.ts

async function syncTable(
  blueDb: D1Database,
  greenDb: D1Database,
  tableName: string,
  batchSize = 500
): Promise<void> {
  let offset = 0;
  let rows: Record<string, unknown>[];

  do {
    const result = await blueDb
      .prepare(`SELECT * FROM ${tableName} LIMIT ? OFFSET ?`)
      .bind(batchSize, offset)
      .all<Record<string, unknown>>();

    rows = result.results;

    if (rows.length === 0) break;

    // Build a batch insert for green
    const placeholders = rows.map(() => "(?, ?, ?, ?)").join(", ");
    const values = rows.flatMap((r) => [r.id, r.name, r.status, r.created_at]);

    await greenDb
      .prepare(`INSERT OR IGNORE INTO ${tableName} (id, name, status, created_at) VALUES ${placeholders}`)
      .bind(...values)
      .run();

    offset += rows.length;
    console.log(`Synced ${offset} rows from ${tableName}`);
  } while (rows.length === batchSize);
}
```

This sync runs against a snapshot and is not real-time. New writes to blue during sync
will be picked up in the next phase.

---

## Phase 2 — Enable Dual-Write (Blue + Green)

Deploy a Worker that writes to both databases simultaneously. Reads still come from blue.
This bridges the gap between the bulk sync and the cut-over.

```typescript
// src/index.ts — dual-write mode

export interface Env {
  DB_BLUE: D1Database;
  DB_GREEN: D1Database;
  MIGRATION_STATE: KVNamespace; // "blue" | "dual-write" | "green"
}

type MigrationState = "blue" | "dual-write" | "green";

async function getState(env: Env): Promise<MigrationState> {
  return ((await env.MIGRATION_STATE.get("db-state")) ?? "blue") as MigrationState;
}

function getReadDb(state: MigrationState, env: Env): D1Database {
  return state === "green" ? env.DB_GREEN : env.DB_BLUE;
}

async function writeOrder(
  env: Env,
  state: MigrationState,
  order: { id: string; name: string; status: string }
): Promise<void> {
  const stmt = `INSERT OR REPLACE INTO orders (id, name, status, updated_at)
                VALUES (?, ?, ?, ?)`;
  const args = [order.id, order.name, order.status, new Date().toISOString()];

  if (state === "blue") {
    await env.DB_BLUE.prepare(stmt).bind(...args).run();
  } else if (state === "dual-write") {
    // Write to both; use Promise.allSettled so a green failure doesn't block the response
    const [blueResult, greenResult] = await Promise.allSettled([
      env.DB_BLUE.prepare(stmt).bind(...args).run(),
      env.DB_GREEN.prepare(stmt).bind(...args).run(),
    ]);
    if (blueResult.status === "rejected") throw blueResult.reason;
    if (greenResult.status === "rejected") {
      // Log but don't fail — green is not yet authoritative
      console.error("Green write failed (non-fatal):", greenResult.reason);
    }
  } else {
    // "green" — write to green only
    await env.DB_GREEN.prepare(stmt).bind(...args).run();
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const state = await getState(env);
    const readDb = getReadDb(state, env);

    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname.startsWith("/orders/")) {
      const id = url.pathname.split("/").pop()!;
      const row = await readDb
        .prepare("SELECT * FROM orders WHERE id = ?")
        .bind(id)
        .first();
      return Response.json(row ?? {}, { status: row ? 200 : 404 });
    }

    if (request.method === "POST" && url.pathname === "/orders") {
      const body = await request.json<{ id: string; name: string; status: string }>();
      await writeOrder(env, state, body);
      return Response.json({ ok: true }, { status: 201 });
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

---

## Phase 3 — Catch-Up Sync (Delta)

While in dual-write mode, sync any rows written to blue but not yet in green. Use a
change-tracking column (`updated_at`) or a change-data-capture table:

```sql
-- On blue DB: ensure an updated_at index exists for efficient delta queries
CREATE INDEX IF NOT EXISTS idx_orders_updated_at ON orders (updated_at);
```

```typescript
// scripts/delta-sync.ts
async function deltaSyncOrders(
  blueDb: D1Database,
  greenDb: D1Database,
  sinceTimestamp: string
): Promise<void> {
  const rows = await blueDb
    .prepare("SELECT * FROM orders WHERE updated_at > ? ORDER BY updated_at ASC LIMIT 1000")
    .bind(sinceTimestamp)
    .all<{ id: string; name: string; status: string; updated_at: string }>();

  for (const row of rows.results) {
    await greenDb
      .prepare("INSERT OR REPLACE INTO orders (id, name, status, updated_at) VALUES (?, ?, ?, ?)")
      .bind(row.id, row.name, row.status, row.updated_at)
      .run();
  }

  console.log(`Delta sync: ${rows.results.length} rows applied`);
}
```

Run the delta sync in a loop until the lag between blue and green is within an acceptable
window (e.g., < 1 second of writes).

---

## Phase 4 — Cut-Over to Green

When green is caught up and dual-write has been stable for a validation window:

```bash
# 1. Switch reads to green (still dual-writing)
wrangler kv key put --namespace-id=<NS_ID> db-state dual-write  # already here
# Confirm green reads are returning correct data via health-check endpoint

# 2. Switch to green-only
wrangler kv key put --namespace-id=<NS_ID> db-state green
# Monitor error rates for 15-30 minutes

# 3. If rollback needed within the window:
wrangler kv key put --namespace-id=<NS_ID> db-state blue
```

---

## Phase 5 — Decommission Blue

After green has been stable (recommended: 48–72 hours), remove the blue binding and delete
the old database.

```bash
# Remove DB_BLUE binding from wrangler.toml, redeploy
wrangler deploy --env production

# Delete old database
wrangler d1 delete orders-db-blue
```

---

## Rollback Decision Tree

```
Cut-over to green
    │
    ├─ Error rate spike → set db-state = "blue" immediately
    │
    ├─ Data inconsistency found → set db-state = "dual-write", run delta sync
    │
    └─ Stable for 48 h → decommission blue
```

---

## Anti-patterns

**Cutting over at the same time as a code change.** Deploy the dual-write Worker first as
a separate step. Mixing schema migration with feature changes makes rollback attribution
impossible.

**Not measuring green write failures during dual-write.** If green writes silently fail,
you cut over to an incomplete database. Alert on any non-zero green write error rate before
cutting over.

**Skipping the delta sync.** The bulk sync is a point-in-time snapshot. Without a delta
sync before cut-over, rows written to blue between bulk sync and cut-over are lost in green.

**Long dual-write windows.** Every write that fails on green during dual-write is a
consistency risk. Keep the dual-write window as short as possible; complete validation with
tooling before switching, not days later.

---

## Gotchas

- D1 does not have an `EXPORT` command like Postgres's `pg_dump`. Export via `wrangler d1
  export` (available from Wrangler 3.x) to get a SQL dump, or use the REST API for batch
  reads.
- KV read-after-write consistency is eventual (up to 60 s). During the cut-over, a small
  number of requests may still read from blue after `db-state = "green"` is written. Use
  `cacheTtl: 0` or a Durable Object to store migration state for strong consistency.
- Green database IDs must be in wrangler.toml before deploying the dual-write Worker. You
  cannot bind a D1 database to a deployed Worker without a redeploy.
- The `updated_at` delta sync pattern misses hard deletes. If rows are deleted in blue,
  they must be replicated to green via a separate delete-tracking mechanism (e.g., a soft
  delete flag or a `deleted_ids` table).

---

## Verification Checklist

- [ ] Green DB created and new schema applied: `wrangler d1 migrations list orders-db-green`
- [ ] Bulk sync complete: row counts match between blue and green.
- [ ] Dual-write Worker deployed: check logs for green write errors.
- [ ] Delta sync confirms lag < 1 s before cut-over.
- [ ] Cut-over executed: `db-state = "green"` in KV.
- [ ] Error rate unchanged for 30 min post-cut-over.
- [ ] Blue DB decommissioned after 48-h stability window.

---

## Related

- `blue-green-architecture.md` — blue-green at the Worker level (no database migration)
- `zero-downtime-schema-migrations.md` — in-place schema changes using expand-contract
- `parallel-change-expand-contract-workers-d1.md` — column-level migration within one DB
- `dual-write-problem-queues-workers.md` — consistency risks of writing to two stores
- `change-data-capture-d1-queues.md` — CDC as an alternative to delta sync

---

## Sources

- Cloudflare D1 docs — developers.cloudflare.com/d1
- Wrangler D1 export — developers.cloudflare.com/workers/wrangler/commands/#d1
- Cloudflare Workers Versions — developers.cloudflare.com/workers/configuration/versions-and-deployments
- Martin Fowler, "BlueGreenDeployment", martinfowler.com/bliki/BlueGreenDeployment.html
