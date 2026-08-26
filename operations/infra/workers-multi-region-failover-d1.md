# Multi-Region Failover Pattern with D1 and Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A D1 primary database experiencing a regional outage or elevated latency causes read queries to fail across all Workers instances globally, even those served from regions far from the fault. Teams need a pattern that automatically falls back to a D1 read replica in a different region when the primary returns errors, without requiring a manual failover procedure.

---

## Context

Cloudflare Workers run at the edge closest to the requesting client, but D1 database reads are routed to the primary database's home region unless a session hint is provided. D1's `withSession` API accepts `'first-unconstrained'` to allow a read from any available replica, which can be in a different physical region. Analytics Engine lets the Worker record a structured event on every request so that region distribution and failover frequency can be monitored in real time via GraphQL. The failover pattern described here wraps every read query in a try/catch; on a D1 error it retries the query against the replica binding using `'first-unconstrained'` and logs the event to Analytics Engine.

---

## Section 1 — wrangler.toml configuration

```toml
# wrangler.toml
name = "orchords-api"
main = "src/index.ts"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding     = "DB_PRIMARY"
database_name = "orchords-main"
database_id = "<primary-db-uuid>"

# Read replica in a second Cloudflare region
# Created via: wrangler d1 create orchords-replica --location=weur
[[d1_databases]]
binding     = "DB_REPLICA"
database_name = "orchords-replica"
database_id = "<replica-db-uuid>"

[[analytics_engine_datasets]]
binding = "AE"
dataset = "workers_db_events"
```

---

## Section 2 — Worker implementation

```typescript
// src/index.ts
import type { D1Database, AnalyticsEngineDataset } from "@cloudflare/workers-types";

export interface Env {
  DB_PRIMARY: D1Database;
  DB_REPLICA: D1Database;
  AE: AnalyticsEngineDataset;
}

type Region = "primary" | "replica";

interface DbEvent {
  region: Region;
  failover: boolean;
  latencyMs: number;
  errorCode?: string;
  cf?: IncomingRequestCfProperties;
}

function recordEvent(ae: AnalyticsEngineDataset, event: DbEvent): void {
  ae.writeDataPoint({
    blobs: [
      event.region,
      event.errorCode ?? "",
      event.cf?.colo ?? "unknown",
      event.cf?.country ?? "unknown",
    ],
    doubles: [event.latencyMs, event.failover ? 1 : 0],
    indexes: [event.region],
  });
}

// ── resilient query helper ─────────────────────────────────────────────────────
async function queryWithFailover<T>(
  env: Env,
  sql: string,
  params: unknown[],
  cf?: IncomingRequestCfProperties
): Promise<{ rows: T[]; region: Region; failover: boolean }> {
  const t0 = Date.now();

  // --- Try primary first ---
  try {
    // withSession('first-primary') routes to the primary region
    const session = env.DB_PRIMARY.withSession("first-primary");
    const stmt = session.prepare(sql).bind(...params);
    const { results } = await stmt.all<T>();
    const latencyMs = Date.now() - t0;
    recordEvent(env.AE, { region: "primary", failover: false, latencyMs, cf });
    return { rows: results, region: "primary", failover: false };
  } catch (primaryErr: unknown) {
    const errorCode =
      primaryErr instanceof Error ? primaryErr.message.slice(0, 64) : "unknown";
    console.error("D1 primary error, attempting replica:", errorCode);
    recordEvent(env.AE, {
      region: "primary",
      failover: true,
      latencyMs: Date.now() - t0,
      errorCode,
      cf,
    });
  }

  // --- Fall back to replica with unconstrained session ---
  const t1 = Date.now();
  // 'first-unconstrained' allows reads from any available replica
  const session = env.DB_REPLICA.withSession("first-unconstrained");
  const stmt = session.prepare(sql).bind(...params);
  const { results } = await stmt.all<T>();
  const latencyMs = Date.now() - t1;
  recordEvent(env.AE, { region: "replica", failover: true, latencyMs, cf });
  return { rows: results, region: "replica", failover: true };
}

// ── example route handler ──────────────────────────────────────────────────────
async function handleGetChords(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const key = url.searchParams.get("key") ?? "C";

  const { rows, region, failover } = await queryWithFailover<{
    id: number;
    name: string;
    fingering: string;
  }>(
    env,
    "SELECT id, name, fingering FROM chords WHERE key = ? LIMIT 20",
    [key],
    request.cf as IncomingRequestCfProperties | undefined
  );

  return Response.json(
    { chords: rows, meta: { region, failover } },
    {
      headers: {
        "X-Db-Region": region,
        "X-Db-Failover": String(failover),
      },
    }
  );
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);
    if (pathname === "/chords") return handleGetChords(request, env);
    return new Response("Not Found", { status: 404 });
  },
};
```

---

## Section 3 — Analytics Engine monitoring query

```typescript
// scripts/query-ae.ts — run with ts-node or bun
// Queries the Analytics Engine GraphQL API to report failover rate
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN  = process.env.CF_API_TOKEN!;

const query = `
  query FailoverReport($accountTag: String!) {
    viewer {
      accounts(filter: { accountTag: $accountTag }) {
        workersDbEventsAdaptiveGroups(
          limit: 100
          filter: { datetime_geq: "2024-09-01T00:00:00Z" }
          orderBy: [count_DESC]
        ) {
          count
          sum { doubles }   # index 1 = failover flag sum
          dimensions {
            blob1             # region
            blob3             # colo
          }
        }
      }
    }
  }
`;

const res = await fetch(
  "https://api.cloudflare.com/client/v4/graphql",
  {
    method: "POST",
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query, variables: { accountTag: ACCOUNT_ID } }),
  }
);

const data = await res.json();
console.dir(data, { depth: null });
```

```bash
# Run the monitoring query
bun scripts/query-ae.ts

# Quick failover check via curl
curl -sf https://api.example.com/chords?key=G \
  -w "\nRegion: %header{X-Db-Region}  Failover: %header{X-Db-Failover}\n"
```

---

## Anti-patterns

- **Using `withSession('first-unconstrained')` for every read** — This defeats D1's strong-consistency guarantees; use it only as a fallback path.
- **Write queries against the replica** — D1 replicas are read-only; attempting a write on `DB_REPLICA` will throw immediately.
- **Silently swallowing the primary error** — Always log the original error and record it in Analytics Engine so failover spikes surface in dashboards.
- **Configuring both `DB_PRIMARY` and `DB_REPLICA` to the same database ID** — This makes the failover a no-op; ensure the replica is a genuinely separate D1 database placed in a different location.

---

## Gotchas

- `D1Database.withSession` is available from compatibility date `2024-09-23` and above; older compatibility dates do not expose this method and will throw at runtime.
- D1 read replicas are eventually consistent; queries executed immediately after a write to primary may return stale data from the replica during the replication window.
- Analytics Engine `writeDataPoint` is fire-and-forget and does not block the response; it uses the Workers sub-request budget (50 subrequests per invocation on the free plan).
- The `doubles` array passed to `writeDataPoint` is indexed positionally; changing the order of values in the array breaks existing Grafana/GraphQL queries that reference them by index.

---

## Verification

```bash
# Confirm both D1 databases exist
wrangler d1 list

# Verify replica is in a different location
wrangler d1 info orchords-replica
# Should show location: weur (or your chosen secondary)

# Simulate primary failure by querying with a bad SQL to trigger fallback
curl -sf https://api.example.com/chords?key=A \
  -H "X-Force-Replica: true"  # implement a debug header in dev only

# Check failover count in Analytics Engine (last 1 hour)
bun scripts/query-ae.ts 2>&1 | grep failover
```

---

## Related

- `terraform-cloudflare-workers-d1-iac.md`
- `cloudflare-access-service-token-workers.md`

---

## Sources

- D1 Read Replication — https://developers.cloudflare.com/d1/best-practices/read-replication/
- D1 withSession API — https://developers.cloudflare.com/d1/worker-api/d1-database/#withsession
- Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
