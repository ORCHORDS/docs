# D1 Read Replication Routing Workers Deploy

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Read queries to your D1 database are slow for users far from the primary region
because every `SELECT` fans out to the primary replica, adding 50–150 ms of
latency. D1's read replication distributes read replicas globally, but Workers
do not automatically route to the nearest replica unless the binding is
configured correctly and the application explicitly opts into read-only paths
for queries that do not need write consistency.

## Context

D1 read replication (GA as of 2025) creates up to 6 regional read replicas
from the primary. A Worker that holds a `D1Database` binding will route reads
to the nearest replica when:
1. The database has read replication enabled.
2. The query is issued on a read-replica-eligible session.
3. The Worker does not force consistency by using `firstBatch()` immediately
   after a write in the same request.

Wrangler does not surface replication config; you configure it through the API
or dashboard and verify via response headers (`CF-D1-Replica-Region`).

---

## 1. Enable Read Replication via API

```typescript
// scripts/enable-read-replication.ts
const CF_ACCOUNT = process.env.CF_ACCOUNT_ID!;
const CF_TOKEN   = process.env.CF_API_TOKEN!;
const DB_ID      = process.env.D1_DATABASE_ID!;

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT}/d1/database/${DB_ID}`,
  {
    method : "PUT",
    headers: {
      Authorization : `Bearer ${CF_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      read_replication: { mode: "auto" },   // "auto" | "disabled"
    }),
  }
);

const { result, success } = await res.json<{
  success: boolean;
  result : { read_replication: { mode: string } };
}>();

if (!success) throw new Error("Failed to enable read replication");
console.log("Read replication mode:", result.read_replication.mode);
```

---

## 2. Wrangler Config — No Change Required

```toml
# wrangler.toml
# Replication is a server-side setting; the binding declaration is unchanged.
name = "my-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding       = "DB"
database_name = "my-app-db"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

---

## 3. Routing Reads vs. Writes in the Worker

D1 sessions control consistency. Use a read-only session for queries that do
not need to see the latest write.

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { method, url } = request;
    const path = new URL(url).pathname;

    if (method === "GET" && path.startsWith("/api/products")) {
      return handleReadOnly(env.DB, request);
    }
    if (method === "POST" && path === "/api/orders") {
      return handleWrite(env.DB, request);
    }
    return new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;

async function handleReadOnly(db: D1Database, req: Request): Promise<Response> {
  // withSession("first-unconstrained") routes to nearest read replica
  const result = await db
    .withSession("first-unconstrained")
    .prepare("SELECT id, name, price FROM products WHERE active = 1")
    .all();

  return Response.json(result.results);
}

async function handleWrite(db: D1Database, req: Request): Promise<Response> {
  const body  = await req.json<{ product_id: number; qty: number }>();

  // Writes always go to primary; no session option needed
  const { meta } = await db
    .prepare("INSERT INTO orders (product_id, qty, created_at) VALUES (?, ?, ?)")
    .bind(body.product_id, body.qty, Date.now())
    .run();

  return Response.json({ order_id: meta.last_row_id });
}
```

---

## 4. Consistency-Sensitive Reads After Writes

For flows that write then immediately read their own write, use a bookmark
to pin to the primary until replication catches up.

```typescript
// src/handlers/checkout.ts
export async function checkout(db: D1Database, req: Request): Promise<Response> {
  const body = await req.json<{ cart: number[] }>();

  // 1. Write order
  const write = await db
    .prepare("INSERT INTO orders (status) VALUES ('pending') RETURNING id")
    .first<{ id: number }>();

  // 2. Read with consistency bookmark so the replica has the write
  //    "first-primary" forces the read to go to the primary
  const order = await db
    .withSession("first-primary")
    .prepare("SELECT * FROM orders WHERE id = ?")
    .bind(write!.id)
    .first<{ id: number; status: string }>();

  return Response.json({ order });
}
```

---

## 5. CI Gate — Verify Replication Status Pre-Deploy

```typescript
// scripts/verify-d1-replication.ts
const CF_ACCOUNT = process.env.CF_ACCOUNT_ID!;
const CF_TOKEN   = process.env.CF_API_TOKEN!;
const DB_ID      = process.env.D1_DATABASE_ID!;

interface D1DB {
  read_replication: { mode: "auto" | "disabled" };
  num_read_replicas?: number;
}

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT}/d1/database/${DB_ID}`,
  { headers: { Authorization: `Bearer ${CF_TOKEN}` } }
);
const { result } = await res.json<{ result: D1DB }>();

if (result.read_replication.mode !== "auto") {
  console.error(
    `D1 read replication is '${result.read_replication.mode}' — expected 'auto'.\n`
    + "Enable it before deploying to production."
  );
  process.exit(1);
}
console.log(
  `Read replication: ${result.read_replication.mode} `
  + `(${result.num_read_replicas ?? "?"} replicas)`
);
```

---

## 6. GitHub Actions — Full Deploy with Replication Gate

```yaml
# .github/workflows/deploy-d1-replicated.yml
name: Deploy with D1 Read Replication Gate

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm ci

      - name: Verify D1 read replication is enabled
        run: npx tsx scripts/verify-d1-replication.ts
        env:
          CF_ACCOUNT_ID:  ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN:   ${{ secrets.CF_API_TOKEN }}
          D1_DATABASE_ID: ${{ secrets.D1_DATABASE_ID }}

      - name: Run D1 migrations
        run: |
          npx wrangler d1 migrations apply my-app-db --remote
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Deploy Worker
        run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Smoke test replica routing
        run: |
          REPLICA_REGION=$(curl -si https://my-api.example.com/api/products \
            | grep -i "cf-d1-replica" | awk '{print $2}')
          echo "Serving from D1 replica region: $REPLICA_REGION"
```

---

## Anti-patterns

- **Using `withSession("first-primary")` for all queries** — defeats the
  purpose of read replication; all reads still fan to the primary.
- **Using `first-unconstrained` immediately after a write in the same request** —
  the replica may not have the write yet; reads return stale or empty data.
- **Enabling read replication on a D1 database with active schema migrations** —
  `ALTER TABLE` and `CREATE INDEX` replay on replicas asynchronously; long-running
  migrations cause replication lag spikes; run migrations during low-traffic
  windows.
- **Disabling replication without draining Workers** — if a Worker session holds
  a replica bookmark and replication is disabled, subsequent reads throw; deploy
  Workers updated to remove replica sessions before disabling.

---

## Gotchas

- D1 read replication adds a per-query overhead (~1–2 ms) for routing; verify
  your p50 latency improvement exceeds this overhead before enabling on
  sub-millisecond queries.
- `withSession()` is not chainable with `batch()` in D1; batch operations always
  target the primary regardless of session mode.
- The `CF-D1-Replica-Region` response header is only present when the query
  actually hit a replica; primary hits return no header.
- Local `wrangler dev` never uses real replicas; test replication behavior with
  `wrangler dev --remote` or a staging environment.
- `num_read_replicas` in the API response reflects provisioned replicas, not
  healthy replicas; a replica bootstrapping after enablement may not yet serve
  traffic.

---

## Verification

```bash
# Check replication mode and replica count
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/d1/database/$D1_DATABASE_ID" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '{name, read_replication, num_read_replicas}'

# Test read replica routing from the edge
curl -si https://my-api.example.com/api/products | grep -i "cf-d1"
# Expected: CF-D1-Replica-Region: weur  (or nearest regional code)
```

---

## Related

- `d1-zero-downtime-schema-migration-workers-compatibility.md`
- `d1-migration-dry-run-ci-gate.md`
- `d1-large-table-batch-migration-strategy.md`
- `cloudflare-workers-deploy-pipeline.md`

---

## Sources

- D1 read replication docs: https://developers.cloudflare.com/d1/configuration/read-replication/
- D1 Sessions and consistency: https://developers.cloudflare.com/d1/worker-api/d1-database/#withsession
- D1 REST API — database update: https://developers.cloudflare.com/api/resources/d1/subresources/database/
