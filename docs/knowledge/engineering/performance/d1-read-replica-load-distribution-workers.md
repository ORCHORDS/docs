# D1 Read Replica Load Distribution in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

D1 query latency climbs as read traffic grows. A single primary D1 database handles both writes and reads; under moderate concurrent load the p99 read latency exceeds 80 ms and the Worker CPU budget is regularly saturated. The goal is to distribute SELECT-heavy workloads across read replicas while routing mutations exclusively to the primary.

## Context

Cloudflare D1 supports read replication: writes always go to the primary, while read replicas receive async replication lag of typically < 100 ms. As of mid-2026 a Worker binding can target a replica with `{ locationHint }` or via the `__D1_BETA__experimental_readReplication` flag. The correct pattern is to detect the request's intent, route accordingly, and fall back gracefully when a replica is stale.

Replica-aware routing belongs in a thin middleware layer rather than in individual route handlers — this keeps the per-handler code identical and the routing strategy centrally configurable.

## 1. Binding Configuration (wrangler.toml)

```toml
[[d1_databases]]
binding        = "DB"
database_name  = "my-app"
database_id    = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[d1_databases]]
binding        = "DB_REPLICA_EU"
database_name  = "my-app"
database_id    = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
experimental_replication = { mode = "enabled", locationHint = "WEU" }

[[d1_databases]]
binding        = "DB_REPLICA_APAC"
database_name  = "my-app"
database_id    = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
experimental_replication = { mode = "enabled", locationHint = "APAC" }
```

## 2. Replica-Aware DB Proxy

```typescript
// lib/db-router.ts
export type Env = {
  DB: D1Database;
  DB_REPLICA_EU: D1Database;
  DB_REPLICA_APAC: D1Database;
};

type RegionHint = "WEU" | "APAC" | "primary";

function detectRegion(request: Request): RegionHint {
  // Cloudflare populates CF-Ray with a 3-letter IATA code suffix
  const cfRay = request.headers.get("CF-Ray") ?? "";
  const iata  = cfRay.slice(-3).toUpperCase();
  if (["AMS", "LHR", "CDG", "FRA", "MAD"].includes(iata)) return "WEU";
  if (["SIN", "NRT", "SYD", "HKG", "BOM"].includes(iata)) return "APAC";
  return "primary";
}

/** Classify SQL: returns true for write statements. */
function isMutation(sql: string): boolean {
  const verb = sql.trimStart().slice(0, 6).toUpperCase();
  return ["INSERT", "UPDATE", "DELETE", "CREATE", "DROP  ", "ALTER "].includes(verb);
}

export class DbRouter {
  private readonly primary: D1Database;
  private readonly replicas: Record<string, D1Database>;
  private readonly region: RegionHint;

  constructor(env: Env, request: Request) {
    this.primary  = env.DB;
    this.replicas = { WEU: env.DB_REPLICA_EU, APAC: env.DB_REPLICA_APAC };
    this.region   = detectRegion(request);
  }

  /** Returns the correct binding for a given SQL statement. */
  binding(sql: string): D1Database {
    if (isMutation(sql)) return this.primary;
    return this.replicas[this.region] ?? this.primary;
  }

  /** Thin helper: prepare + run on the correct binding. */
  prepare(sql: string): D1PreparedStatement {
    return this.binding(sql).prepare(sql);
  }
}
```

## 3. Per-Request Router Instantiation

```typescript
// worker.ts
import { DbRouter, Env } from "./lib/db-router";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const db = new DbRouter(env, request);

    // Read — routed to nearest replica automatically
    const { results } = await db
      .prepare("SELECT id, title, slug FROM posts WHERE published = 1 ORDER BY created_at DESC LIMIT 20")
      .all();

    // Write — always hits primary regardless of region
    await db
      .prepare("INSERT INTO audit_log (event, ts) VALUES (?, ?)")
      .bind("page_view", Date.now())
      .run();

    return Response.json(results);
  },
};
```

## 4. Replica Staleness Guard

Some endpoints cannot tolerate replication lag (e.g., post-write reads). Use a `Consistency-Token` header to force primary routing when the client indicates it just mutated data.

```typescript
// lib/consistency.ts
export function requireFreshRead(request: Request): boolean {
  // Client sets X-Consistency: strong after any mutation it triggered
  return request.headers.get("X-Consistency") === "strong";
}

// Usage inside DbRouter.binding():
binding(sql: string): D1Database {
  if (isMutation(sql) || this.forcePrimary) return this.primary;
  return this.replicas[this.region] ?? this.primary;
}

// Constructor addition:
this.forcePrimary = requireFreshRead(request);
```

## 5. Replica Health Monitoring via Analytics Engine

```typescript
// lib/db-metrics.ts
export async function recordQueryMetric(
  ae: AnalyticsEngineDataset,
  target: "primary" | "replica",
  durationMs: number,
  ok: boolean
): Promise<void> {
  ae.writeDataPoint({
    indexes: [target],
    blobs:   [ok ? "ok" : "error"],
    doubles: [durationMs],
  });
}

// Wrap DbRouter.prepare with timing:
async function timedQuery<T>(
  stmt: D1PreparedStatement,
  ae: AnalyticsEngineDataset,
  target: "primary" | "replica"
): Promise<T> {
  const t0 = Date.now();
  try {
    const result = await stmt.all() as T;
    await recordQueryMetric(ae, target, Date.now() - t0, true);
    return result;
  } catch (err) {
    await recordQueryMetric(ae, target, Date.now() - t0, false);
    throw err;
  }
}
```

## Anti-patterns

- **Sending writes to a replica binding** — D1 silently re-routes them to the primary, adding network round-trip overhead; always classify mutations explicitly.
- **Hardcoding region strings** — IATA codes change; keep the mapping in a `const` map that can be updated without re-deploying handler logic.
- **Sharing a `DbRouter` instance across requests** — the class must be constructed per-request since `CF-Ray` is request-scoped.
- **Ignoring replication lag on session-sensitive reads** — a user who just submitted a form and immediately reloads will see their old data if the replica hasn't caught up. Use the `X-Consistency: strong` pattern or a short exponential-backoff primary fallback.

## Gotchas

- `locationHint` is advisory: Cloudflare places the replica geographically close to the hint but does not guarantee co-location with the Worker PoP. Measure actual latency by region before assuming a replica is faster.
- D1 replication lag has a soft cap of ~150 ms under normal conditions but can spike during high write throughput; design consumers to tolerate this.
- The `experimental_replication` flag may be promoted to GA with a different wrangler key — pin your `wrangler` version in CI.
- Prepared statement caches are per-binding; the same SQL string prepared on the primary is a distinct object from the same SQL on a replica binding.

## Verification

```typescript
// health-check.ts — run as a scheduled cron trigger
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const start = Date.now();
    await env.DB_REPLICA_EU.prepare("SELECT 1").first();
    const latencyMs = Date.now() - start;
    console.log(JSON.stringify({ replica: "EU", latencyMs }));
    // Alert if latency exceeds threshold
    if (latencyMs > 200) {
      // Post to alerting webhook
    }
  },
};
```

Confirm routing in production by checking `CF-Ray` suffix against the `target` dimension in Analytics Engine; read queries should show `replica` targets for EU and APAC traffic.

## Related

- `d1-prepared-statement-reuse.md`
- `d1-query-result-caching-kv-workers.md`
- `hyperdrive-connection-pooling-workers.md`
- `workers-smart-placement-origin-latency.md`

## Sources

- Cloudflare D1 Read Replication docs — developers.cloudflare.com/d1/reference/replication
- Cloudflare D1 Bindings / locationHint — developers.cloudflare.com/d1/configuration/bindings
- D1 changelog (2025-Q4) — D1 read replication GA announcement
