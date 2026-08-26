# Shared Database Anti-pattern and Service Decoupling

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Two or more Cloudflare Workers share the same D1 database binding. One service reads tables
owned by another service, or both services write to the same table without coordination.
Schema changes break downstream services silently, and query patterns from Service A degrade
the performance SLA of Service B. Deployments require cross-team synchronisation.

## Context

The shared database anti-pattern is the most common cause of coupling in service-oriented
systems. When multiple services share a schema they implicitly share a data contract. Any
`ALTER TABLE`, index removal, or column rename that one team makes can silently break every
other service that touches the same rows.

On Cloudflare Workers the pattern manifests as multiple service bindings that all receive the
same D1 binding in `wrangler.toml`. Because D1 is schema-full (SQLite) the coupling is
structural, not just incidental. The canonical fix is the **Database-per-Service** pattern:
each service has exclusive ownership of its own schema, and data crossing service boundaries
travels through APIs or events, never via a shared table.

## Identifying the Anti-pattern

```typescript
// ANTI-PATTERN — two services sharing one D1 binding
// inventory-worker/wrangler.toml → DB = "shared-db"
// orders-worker/wrangler.toml    → DB = "shared-db"  ← same binding!

// orders-worker reading inventory data directly:
export default {
  async fetch(req: Request, env: Env) {
    // Orders Worker should not know about the `inventory` table schema
    const stock = await env.DB.prepare(
      "SELECT quantity FROM inventory WHERE sku = ?"
    ).bind(req.headers.get("x-sku")).first<{ quantity: number }>();
    return Response.json({ inStock: (stock?.quantity ?? 0) > 0 });
  },
};
```

The orders service now knows the column name `quantity`, the table name `inventory`, and the
key type of the inventory service. Renaming the column in Inventory requires a coordinated
deploy of Orders.

## Database-per-Service Split

Each service gets its own D1 database. Cross-service data access goes through the owning
service's public API.

```toml
# inventory-worker/wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "inventory-db"
database_id = "aaa-111"

# orders-worker/wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "orders-db"
database_id = "bbb-222"

# Orders uses a service binding to call Inventory's API, never its DB
[[services]]
binding = "INVENTORY_SERVICE"
service = "inventory-worker"
```

## Replacing Direct DB Access with a Service API

```typescript
// inventory-worker — exposes a typed API
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname === "/stock") {
      const sku = url.searchParams.get("sku");
      if (!sku) return new Response("Bad Request", { status: 400 });
      const row = await env.DB.prepare(
        "SELECT quantity FROM inventory WHERE sku = ? AND active = 1"
      ).bind(sku).first<{ quantity: number }>();
      return Response.json({ sku, inStock: (row?.quantity ?? 0) > 0 });
    }
    return new Response("Not Found", { status: 404 });
  },
};
```

```typescript
// orders-worker — calls the Inventory API through a service binding
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const sku = req.headers.get("x-sku") ?? "";
    // Orders has zero knowledge of Inventory's schema
    const stockRes = await env.INVENTORY_SERVICE.fetch(
      new Request(`https://inventory/stock?sku=${encodeURIComponent(sku)}`)
    );
    if (!stockRes.ok) {
      return new Response("Inventory check failed", { status: 502 });
    }
    const { inStock } = await stockRes.json<{ inStock: boolean }>();
    if (!inStock) return new Response("Out of stock", { status: 409 });
    // proceed with order creation in own DB
    await env.DB.prepare(
      "INSERT INTO orders (sku, status) VALUES (?, 'pending')"
    ).bind(sku).run();
    return new Response("Order created", { status: 201 });
  },
};
```

## Event-Driven Alternative for Read-Heavy Cross-Service Data

When the Orders service needs inventory data for reporting (read-heavy, slight staleness
acceptable), an event-driven projection is more scalable than synchronous API calls.

```typescript
// inventory-worker — emits events on stock changes
async function updateStock(env: Env, sku: string, delta: number): Promise<void> {
  await env.DB.prepare(
    "UPDATE inventory SET quantity = quantity + ? WHERE sku = ?"
  ).bind(delta, sku).run();
  // Emit event for downstream projections
  await env.STOCK_EVENTS.send({ sku, delta, ts: Date.now() });
}
```

```typescript
// orders-worker — maintains a local read-model in its own D1
export default {
  async queue(
    batch: MessageBatch<{ sku: string; delta: number; ts: number }>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      const { sku, delta } = msg.body;
      await env.DB.prepare(`
        INSERT INTO stock_snapshot (sku, quantity, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT (sku) DO UPDATE SET
          quantity  = quantity + excluded.quantity,
          updated_at = excluded.updated_at
      `).bind(sku, delta, Date.now()).run();
      msg.ack();
    }
  },
};
```

## Migration Strategy — Strangler Fig for Shared Tables

When migrating from an existing shared database, use the Strangler Fig pattern.

```typescript
// migration-proxy.ts — temporary adapter in the Inventory Worker
// Phase 1: read from shared DB, write to new isolated DB
export async function getStockMigration(
  env: Env,
  sku: string
): Promise<{ quantity: number }> {
  // Try new isolated DB first
  const newRow = await env.INVENTORY_DB.prepare(
    "SELECT quantity FROM inventory WHERE sku = ?"
  ).bind(sku).first<{ quantity: number }>();
  if (newRow) return newRow;
  // Fallback to legacy shared DB (remove after migration)
  const legacyRow = await env.SHARED_DB.prepare(
    "SELECT quantity FROM inventory WHERE sku = ?"
  ).bind(sku).first<{ quantity: number }>();
  return legacyRow ?? { quantity: 0 };
}
```

## Anti-patterns

- Sharing a D1 database across services "just for joins" — joins that cross service
  boundaries indicate a missing service API or a misaligned bounded context.
- Adding a view on top of the shared schema and calling it an API — the view still
  exposes the physical schema; rename a column and the view breaks.
- Using a shared KV namespace as a rendezvous point between services — treat KV
  ownership the same as DB ownership: one service writes, others read via the
  owning service's API.
- Skipping the event model because it's "too complex for small teams" — the coupling
  cost of a shared DB compounds quickly once the schema has > 20 tables.

## Gotchas

- Cloudflare D1 enforces no access controls inside the database itself; all access
  control is at the binding level (`wrangler.toml`). Removing a binding from a Worker
  is the only reliable way to prevent it from accessing a database.
- Service bindings (`env.INVENTORY_SERVICE.fetch`) call the bound Worker directly over
  the local loopback; they do not consume egress and do not traverse the internet.
- When splitting tables out of a shared DB, D1's `ATTACH DATABASE` is not supported;
  you must copy data using the D1 REST API or a migration Worker, not SQL `ATTACH`.
- An event-driven read model will be stale by the Queue consumer lag (typically < 1 s
  in normal conditions). Document the staleness SLA in the service contract.

## Verification

1. Confirm no `wrangler.toml` in Service B references the D1 `database_id` owned by Service A.
2. Run `wrangler d1 info <service-a-db>` and cross-check no other Worker has that binding.
3. Integration test: change a column name in Service A's schema and confirm Service B's
   tests do not compile or fail (proving there is no compile-time or runtime coupling).
4. Measure the round-trip latency of the service binding API call in a staging environment
   to confirm it is within SLA before removing the fallback to the shared DB.

## Related

- `bounded-context-design.md`
- `strangler-fig-cloudflare-migration.md`
- `data-isolation-strategies.md`
- `event-carried-state-transfer-workers-kv.md`
- `worker-to-worker-rpc-service-bindings.md`

## Sources

- Sam Newman — Building Microservices (Chapter 4: Integration)
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Cloudflare Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
