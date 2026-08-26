# D1 Single-Writer Durable Object Connection Multiplexing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Multiple Worker instances all bind to the same D1 database. Each Worker independently issues writes
and occasionally races with others, causing `SQLITE_BUSY` errors or violating business-level
ordering guarantees (e.g., inventory decrement, seat reservation). You want a single serialisation
point without an external queue service.

## Context

D1's SQLite-on-Cloudflare writes go to a single primary node, but concurrent Workers can still
race inside a transaction window. The **Durable Objects single-writer** pattern routes all mutating
requests through exactly one DO instance, which:

1. Holds the D1 binding and serialises calls via its own event loop (no concurrency inside one DO).
2. Accepts RPCs from any Worker instance via the same stub URL key.
3. Returns structured results so callers remain stateless.

Read-only queries should bypass the DO entirely and hit D1 directly to preserve throughput.

---

## Durable Object Class

```typescript
// src/do/D1Writer.ts
import { DurableObject } from "cloudflare:workers";

export interface WriteRequest {
  sql:    string;
  params: unknown[];
}

export interface WriteResponse {
  success: boolean;
  results: unknown[];
  error?:  string;
}

export class D1Writer extends DurableObject {
  private db: D1Database;

  constructor(state: DurableObjectState, env: Env) {
    super(state, env);
    this.db = env.DB;
  }

  async fetch(request: Request): Promise<Response> {
    const body = await request.json<WriteRequest>();
    try {
      const stmt   = this.db.prepare(body.sql);
      const result = await stmt.bind(...body.params).all();
      const resp: WriteResponse = { success: true, results: result.results };
      return Response.json(resp);
    } catch (err) {
      const resp: WriteResponse = {
        success: false,
        results: [],
        error: err instanceof Error ? err.message : String(err),
      };
      return Response.json(resp, { status: 500 });
    }
  }
}
```

---

## Environment & Binding Setup

```toml
# wrangler.toml
[[d1_databases]]
binding  = "DB"
database_name = "example project-prod"
database_id   = "<d1-database-id>"

[[durable_objects.bindings]]
name       = "D1_WRITER"
class_name = "D1Writer"

[[migrations]]
tag = "v1"
new_classes = ["D1Writer"]
```

```typescript
// src/types.ts
export interface Env {
  DB:        D1Database;
  D1_WRITER: DurableObjectNamespace;
}
```

---

## Client Helper (Worker-side)

```typescript
// src/db/writer.ts
import type { WriteRequest, WriteResponse } from "../do/D1Writer";

// All mutations are routed to one named DO instance ("singleton")
const DO_KEY = "global-writer";

export async function doWrite(
  env: Env,
  sql: string,
  params: unknown[] = []
): Promise<unknown[]> {
  const id   = env.D1_WRITER.idFromName(DO_KEY);
  const stub = env.D1_WRITER.get(id);

  const payload: WriteRequest = { sql, params };
  const res  = await stub.fetch("https://do-internal/write", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(payload),
  });

  const data: WriteResponse = await res.json();
  if (!data.success) throw new Error(`D1Writer error: ${data.error}`);
  return data.results;
}

// Reads bypass the DO entirely
export async function doRead(
  env: Env,
  sql: string,
  params: unknown[] = []
): Promise<unknown[]> {
  const stmt = env.DB.prepare(sql);
  const result = await stmt.bind(...params).all();
  return result.results;
}
```

---

## Using the Pattern in a Handler

```typescript
// src/handlers/inventory.ts
import { doWrite, doRead } from "../db/writer";

export async function handleDecrementStock(request: Request, env: Env) {
  const { productId, qty } = await request.json<{ productId: string; qty: number }>();

  // Serialised through DO — no concurrent Workers can interleave here
  const rows = await doWrite(
    env,
    `UPDATE inventory
        SET stock = stock - ?1
      WHERE product_id = ?2
        AND stock >= ?1
      RETURNING product_id, stock`,
    [qty, productId]
  );

  if (rows.length === 0) {
    return Response.json({ error: "Insufficient stock" }, { status: 409 });
  }
  return Response.json(rows[0]);
}

export async function handleGetStock(request: Request, env: Env) {
  const productId = new URL(request.url).searchParams.get("productId")!;
  const rows = await doRead(
    env,
    "SELECT product_id, stock FROM inventory WHERE product_id = ?1",
    [productId]
  );
  return Response.json(rows[0] ?? null);
}
```

---

## Batching Multiple Statements Inside the DO

For higher throughput, accept a batch of statements in one fetch:

```typescript
// Extended D1Writer fetch — supports "batch" action
async fetch(request: Request): Promise<Response> {
  const { action, statements } =
    await request.json<{ action: "batch"; statements: WriteRequest[] }>();

  if (action === "batch") {
    const batch = statements.map((s) => this.db.prepare(s.sql).bind(...s.params));
    const results = await this.db.batch(batch);
    return Response.json({ success: true, results: results.map((r) => r.results) });
  }
  // ... single write handling from above
}
```

---

## Anti-patterns

- **Routing reads through the DO**: the DO's single event loop becomes a throughput bottleneck for
  reads; always use the D1 binding directly from the Worker for SELECT queries.
- **Multiple DO keys for the same logical resource**: you lose serialisation guarantees if two
  Workers derive different DO IDs for the same table or row.
- **Blocking inside the DO without a timeout**: a long-running INSERT/UPDATE without a deadline can
  stall the entire write queue for that DO instance.
- **Using DO alarm as a write queue**: alarms fire at most once per second; for burst writes use
  the in-memory RPC queue pattern above instead.

---

## Gotchas

- A DO instance runs in one Cloudflare colo. If Workers are globally distributed, the round-trip to
  the DO (which lives where it was first created) adds latency — typically 20–80 ms for cross-region
  hops. Pin the DO colo with `idFromName` on a jurisdiction-scoped namespace if needed.
- DO hibernation: the D1Writer class will be evicted after ~10 s of inactivity. The next request
  cold-starts it in ~5–15 ms. Persistent connections inside the DO class do not help D1 (D1 is HTTP
  not a native socket), so hibernation is benign.
- DO instances are billed per request and per GB-s of compute. High-frequency writes accumulate DO
  cost — budget accordingly.
- `env.DB` must be bound **to the DO class**, not just the Worker entrypoint. Verify both appear in
  `wrangler.toml` under `[durable_objects]` and `[[d1_databases]]`.

---

## Verification

```bash
# Concurrent stampede test — all requests should succeed, none conflict
for i in $(seq 1 20); do
  curl -s -X POST https://example project.example.com/inventory/decrement \
    -d '{"productId":"sku-001","qty":1}' &
done
wait
# Expect: final stock = initial_stock - 20; no 5xx responses
```

---

## Related

- `d1-durable-objects-serialized-writes-workers.md`
- `d1-advisory-lock-pattern-workers.md`
- `d1-optimistic-locking-version-column-workers.md`
- `d1-batch-operations-performance.md`
- `d1-savepoint-nested-transaction-workers.md`

## Sources

- Cloudflare Durable Objects docs: https://developers.cloudflare.com/durable-objects/
- D1 Workers binding: https://developers.cloudflare.com/d1/worker-api/
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
