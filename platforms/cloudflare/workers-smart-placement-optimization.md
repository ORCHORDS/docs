# Using Cloudflare Smart Placement to Reduce Latency for Database-Heavy Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker performs multiple round-trips to a database (D1, Hyperdrive-proxied Postgres, or an external database). Even though your Worker executes in milliseconds of CPU time, the wall-clock latency is high because the Worker was placed in a PoP geographically far from the database. Users in the same region as the database paradoxically see slower responses than if you had used a traditional server, because the request fans out through Cloudflare's global network to an arbitrary edge node.

Smart Placement solves this by routing Worker invocations to the Cloudflare PoP nearest to the data source rather than nearest to the requesting client.

## Context

By default, Cloudflare Workers run at the edge PoP closest to the **client**. This is ideal for compute-only tasks (HTML rendering, auth token validation) but suboptimal when the Worker must make multiple sequential calls to a **centralised data source** (a single-region D1 database, a Hyperdrive connection pool pointing at a fixed Postgres instance, or a third-party API hosted in one region).

Smart Placement is a Worker-level setting. Once enabled:

1. Cloudflare measures the latency between its PoPs and your data sources.
2. Each Worker invocation is routed to the PoP with the best aggregate round-trip to those sources.
3. The client's request is transparently proxied from their nearest edge to the selected PoP — adding one extra hop, which is offset by the saved database round-trips.

Smart Placement works best when:
- The Worker makes 2 or more sequential database queries per request.
- The database is in a single geographic region.
- Request payloads are small (Smart Placement is not beneficial for large file uploads/downloads).

## Solution

```typescript
// src/index.ts — a typical database-heavy API endpoint

import { drizzle } from 'drizzle-orm/d1';
import { users, orders } from './schema';
import { eq, desc } from 'drizzle-orm';

export interface Env {
  DB: D1Database;
  ANALYTICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const start = Date.now();
    const url = new URL(request.url);
    const userId = url.searchParams.get('userId');

    if (!userId) {
      return Response.json({ error: 'userId required' }, { status: 400 });
    }

    const db = drizzle(env.DB);

    // Sequential queries — this is where Smart Placement helps.
    // Without it, each query adds a cross-continental RTT.
    const [user] = await db
      .select()
      .from(users)
      .where(eq(users.id, userId))
      .limit(1);

    if (!user) {
      return Response.json({ error: 'not found' }, { status: 404 });
    }

    const recentOrders = await db
      .select()
      .from(orders)
      .where(eq(orders.userId, userId))
      .orderBy(desc(orders.createdAt))
      .limit(10);

    const wallClock = Date.now() - start;

    // Emit a latency data point to Analytics Engine for before/after comparison.
    // The `cf.colo` binding tells you which PoP handled this invocation.
    ctx.waitUntil(
      emitLatencyMetric(env.ANALYTICS, {
        colo: (request as any).cf?.colo ?? 'unknown',
        durationMs: wallClock,
        queryCount: 2,
      }),
    );

    return Response.json({ user, recentOrders, meta: { durationMs: wallClock } });
  },
};

interface LatencyPoint {
  colo: string;
  durationMs: number;
  queryCount: number;
}

async function emitLatencyMetric(
  dataset: AnalyticsEngineDataset,
  point: LatencyPoint,
): Promise<void> {
  dataset.writeDataPoint({
    blobs: [point.colo],
    doubles: [point.durationMs, point.queryCount],
    indexes: ['workers_latency'],
  });
}
```

**wrangler.toml — enabling Smart Placement:**

```toml
name = "my-api"
main = "src/index.ts"
compatibility_date = "2025-08-01"

# Enable Smart Placement
[placement]
mode = "smart"

[[d1_databases]]
binding = "DB"
database_name = "my-production-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "workers_latency"
```

**Querying latency improvement from Analytics Engine:**

```typescript
// scripts/query-latency.ts

const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN = process.env.CF_API_TOKEN!;

const query = `
  SELECT
    blob1 AS colo,
    AVG(double1) AS avg_duration_ms,
    QUANTILE(0.95)(double1) AS p95_duration_ms,
    COUNT() AS request_count
  FROM workers_latency
  WHERE timestamp > NOW() - INTERVAL '24' HOUR
  GROUP BY colo
  ORDER BY avg_duration_ms ASC
`;

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
  {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      'Content-Type': 'text/plain',
    },
    body: query,
  },
);

const data = await res.json();
console.table(data.data);
```

## Implementation Details

**How Smart Placement determines the optimal PoP:**

Cloudflare continuously probes latency from every PoP to your bound data sources (D1 database, Hyperdrive connection pool). When a request arrives, the system selects the PoP with the lowest measured latency to those sources. The extra client-to-PoP hop is typically 20-40ms, while the database RTT savings are often 80-300ms for cross-regional setups.

**Verifying which PoP handled a request:**

```typescript
// Inside your fetch handler:
const colo = (request as any).cf?.colo; // e.g. "DUB", "SIN", "IAD"
console.log(`Handled by: ${colo}`);
```

With Smart Placement enabled and a database in `us-east-1`, you should consistently see `colo` values like `IAD` or `EWR` regardless of where the client request originated.

**Hyperdrive compatibility:**

Smart Placement is aware of Hyperdrive connection pool locations. If you bind a Hyperdrive config, Cloudflare factors the Hyperdrive origin's location into the placement decision. No extra configuration is needed.

```toml
[[hyperdrive]]
binding = "HYPERDRIVE"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

## Anti-patterns

- **Enabling Smart Placement for compute-only Workers.** If your Worker doesn't make external calls (pure transformation, header manipulation), Smart Placement adds latency without benefit. Only enable it when database calls dominate response time.
- **Expecting Smart Placement to help with multi-region databases.** If you use CockroachDB or PlanetScale with a globally distributed setup, there is no single best PoP. Smart Placement will pick one arbitrarily. Use client-side region routing instead.
- **Streaming responses with Smart Placement.** Smart Placement proxies the response back through the original edge PoP, adding latency for streaming (SSE, large downloads). For streaming endpoints, run Smart Placement on a separate route or disable it.
- **Not measuring before enabling.** Always establish a baseline latency metric before enabling, so you can quantify the improvement (or regression).

## Gotchas

- **Local development (`wrangler dev`)** ignores Smart Placement — it always runs locally. Test placement effects only against preview or production.
- **Cold starts are not affected by placement.** Smart Placement routes requests to an already-warm instance when available, but the first invocation after a cold start incurs normal cold-start overhead.
- **Pricing:** Smart Placement is included at no extra cost as of 2026. Verify on the pricing page if this changes.
- **Rollout is gradual.** After setting `mode = "smart"`, placement decisions start optimizing within minutes but may take up to an hour to fully converge as latency probes accumulate.

## Verification

```bash
# Deploy with Smart Placement enabled
npx wrangler deploy

# Send requests from different geographic locations
# (use a VPN or a multi-region test tool like k6 cloud)
# Check the `colo` value in response metadata — it should cluster
# around the region nearest your database.

# Query Analytics Engine after 30 minutes of traffic:
tsx scripts/query-latency.ts
# Look for avg_duration_ms drop compared to your pre-deployment baseline.

# Disable Smart Placement to compare:
# Comment out [placement] in wrangler.toml and deploy to a test route.
```

## Related

- `workers-d1-read-replication.md` — complementary strategy using D1 read replicas to bring data closer to the edge
- `workers-hyperdrive-postgres.md` — Hyperdrive connection pooling with Postgres
- `workers-analytics-engine-metrics.md` — writing custom metrics to Analytics Engine

## Sources

- https://developers.cloudflare.com/workers/configuration/smart-placement/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/hyperdrive/
- https://developers.cloudflare.com/d1/
