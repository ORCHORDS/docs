# Speculative Prefetch Warming: Pre-fetching D1 Queries into KV via Analytics Engine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

API endpoints that serve personalised or trending content see high D1 latency on cache-cold requests because every user who arrives first after a TTL expiry triggers a full database round-trip. Cold-cache p99 latency is 3-5× higher than warm-cache p99.

Goal: drive cache-hit rate from ~40 % to >90 % for the top-N most-requested query shapes by pre-filling KV before the TTL expires, based on historical access patterns stored in Analytics Engine.

---

## Context

Cloudflare's stack used here:

- **D1** — SQLite-compatible edge database (the source of truth)
- **KV** — low-latency eventually-consistent key-value store (the hot cache)
- **Analytics Engine** — append-only event store for high-volume telemetry, queryable via SQL over the Workers Analytics Engine REST API
- **Workers Cron Triggers** — scheduled Workers invocations (minimum 1-minute cadence)

The idea is a two-phase system:

1. **Ingest phase** (every request): write a lightweight hit-event to Analytics Engine recording which query key was served.
2. **Prefetch phase** (cron, every minute): read the top-N most-hit keys from Analytics Engine for the past 10 minutes, re-execute the corresponding D1 queries, and write results back to KV with a refreshed TTL.

---

## Phase 1 — Recording Hit Events

Every request handler writes a single `writeDataPoint` call. This is non-blocking and does not add latency.

```typescript
// src/handlers/product.ts
import type { Env } from '../types';

export interface HitEvent {
  doubles: number[];
  blobs: string[];
  indexes: [string];
}

/**
 * Serve a product listing from KV cache, falling back to D1.
 * Writes a hit-event to Analytics Engine regardless of cache outcome.
 */
export async function handleProductListing(
  request: Request,
  env: Env,
): Promise<Response> {
  const url = new URL(request.url);
  const category = url.searchParams.get('category') ?? 'all';
  const page = parseInt(url.searchParams.get('page') ?? '1', 10);

  const cacheKey = `products:${category}:${page}`;

  // --- KV cache lookup ---
  const cached = await env.CACHE_KV.get(cacheKey, { type: 'json' });

  // Record the access regardless of hit/miss so the cron has signal
  env.ANALYTICS.writeDataPoint({
    blobs: [cacheKey, cached ? 'hit' : 'miss', category],
    doubles: [page, Date.now()],
    indexes: [cacheKey], // indexed for fast GROUP BY
  } satisfies HitEvent);

  if (cached) {
    return Response.json(cached, {
      headers: { 'X-Cache': 'HIT', 'Cache-Control': 'public, max-age=60' },
    });
  }

  // --- D1 fallback ---
  const rows = await env.DB.prepare(
    `SELECT id, title, price, stock
     FROM products
     WHERE category = ?1
     ORDER BY title
     LIMIT 20 OFFSET ?2`,
  )
    .bind(category, (page - 1) * 20)
    .all();

  const payload = { category, page, items: rows.results };

  // Populate KV so subsequent requests are warm (TTL = 90 s)
  await env.CACHE_KV.put(cacheKey, JSON.stringify(payload), {
    expirationTtl: 90,
  });

  return Response.json(payload, {
    headers: { 'X-Cache': 'MISS', 'Cache-Control': 'public, max-age=60' },
  });
}
```

---

## Phase 2 — Cron Prefetch Worker

A separate Worker (or a cron handler on the same Worker) queries Analytics Engine for the hottest keys and re-warms KV proactively.

```typescript
// src/cron/prefetch.ts
import type { Env } from '../types';

const AE_SQL_ENDPOINT =
  'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/analytics_engine/sql';

interface AERow {
  blob1: string; // cacheKey
  blob3: string; // category
  double1: number; // page
  hits: number;
}

/**
 * Called by the Workers Cron Trigger every minute.
 * Fetches the top-20 hottest cache keys from the last 10 minutes
 * and re-populates KV before TTLs expire.
 */
export async function runPrefetchCron(env: Env): Promise<void> {
  // 1. Query Analytics Engine for top keys
  const sql = `
    SELECT
      blob1 AS cacheKey,
      blob3 AS category,
      toInt32(double1) AS page,
      count() AS hits
    FROM product_hits
    WHERE timestamp >= now() - INTERVAL '10' MINUTE
      AND blob2 = 'miss'            -- only re-warm keys that were misses
    GROUP BY blob1, blob3, double1
    ORDER BY hits DESC
    LIMIT 20
  `;

  const aeRes = await fetch(AE_SQL_ENDPOINT.replace('{ACCOUNT_ID}', env.ACCOUNT_ID), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query: sql }),
  });

  if (!aeRes.ok) {
    console.error('Analytics Engine query failed', await aeRes.text());
    return;
  }

  const { data } = (await aeRes.json()) as { data: AERow[] };

  if (data.length === 0) {
    console.log('Prefetch cron: no miss candidates found');
    return;
  }

  // 2. Re-execute D1 queries and push results into KV
  //    Use D1 batch to reduce per-key round-trips (see batch article)
  const prefetchResults = await Promise.allSettled(
    data.map((row) => prefetchKey(row, env)),
  );

  const succeeded = prefetchResults.filter((r) => r.status === 'fulfilled').length;
  const failed = prefetchResults.filter((r) => r.status === 'rejected').length;
  console.log(`Prefetch cron: ${succeeded} warmed, ${failed} failed`);
}

async function prefetchKey(row: AERow, env: Env): Promise<void> {
  const { category, page, cacheKey } = {
    category: row.blob3 ?? row.category,
    page: row.double1 ?? row.page,
    cacheKey: row.blob1 ?? row.cacheKey,
  };

  const result = await env.DB.prepare(
    `SELECT id, title, price, stock
     FROM products
     WHERE category = ?1
     ORDER BY title
     LIMIT 20 OFFSET ?2`,
  )
    .bind(category, (page - 1) * 20)
    .all();

  await env.CACHE_KV.put(
    cacheKey,
    JSON.stringify({ category, page, items: result.results }),
    { expirationTtl: 120 }, // 2-minute TTL — cron runs every minute
  );
}
```

---

## wrangler.toml Configuration

```toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[d1_databases]]
binding = "DB"
database_name = "prod-db"
database_id = "<YOUR_D1_ID>"

[[kv_namespaces]]
binding = "CACHE_KV"
id = "<YOUR_KV_ID>"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "product_hits"

[triggers]
crons = ["* * * * *"]  # every minute
```

---

## Anti-patterns

- **Warming every key**: only pre-warm keys with proven demand. Warming cold-long-tail keys wastes KV write quota and D1 reads.
- **Blocking the request path**: `writeDataPoint` is fire-and-forget. Never `await` it on the hot path.
- **KV TTL shorter than cron cadence**: if the TTL is 60 s and cron runs every 60 s there is a window of coldness. TTL should be at least 2× the cron interval.
- **Re-warming on every miss in real-time**: this moves the latency penalty to the first user after each TTL expiry; the cron approach distributes the cost off the critical path.

---

## Gotchas

- Analytics Engine data has a ~5-minute propagation delay; adjust the `INTERVAL` in the SQL to at least `15 MINUTE` in low-traffic environments to get statistically significant samples.
- The Analytics Engine SQL API is a REST endpoint, not a D1 binding — it requires a Cloudflare API token with `Account Analytics: Read` permission.
- KV `expirationTtl` minimum is 60 seconds.
- Workers Cron minimum cadence is 1 minute; for sub-minute freshness, use Durable Objects alarms instead.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Tail logs to observe cache hit/miss ratio in real time
npx wrangler tail --format pretty

# Manually trigger the cron (Wrangler >= 3.x)
npx wrangler triggers dispatch --trigger-type=cron

# Check KV entries populated by the cron
npx wrangler kv key list --binding CACHE_KV --prefix "products:"

# Query Analytics Engine directly to verify event ingestion
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT count() FROM product_hits WHERE timestamp >= now() - INTERVAL 5 MINUTE"}'
```

Expected outcome: after two cron cycles the miss rate in Analytics Engine drops by 50 %+ for the top-20 keys.

---

## Related

- `workers-d1-query-batch-reduce-roundtrips.md` — batching the D1 queries inside `prefetchKey`
- `workers-tcp-connection-reuse-upstream.md` — keeping the Analytics Engine API connection warm
- [Cloudflare Analytics Engine docs](https://developers.cloudflare.com/analytics/analytics-engine/)
- [Workers KV docs](https://developers.cloudflare.com/kv/)
- [Workers Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/)

---

## Sources

- Cloudflare Analytics Engine SQL API — https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Workers KV — https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
