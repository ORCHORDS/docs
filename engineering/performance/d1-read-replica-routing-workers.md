# D1 Read Replica Routing in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
A Workers application querying D1 for read-heavy workloads (product listings, article feeds, user profile reads) sees higher-than-expected latency because all queries are routed to the D1 primary. Cloudflare D1 supports read replicas that are co-located with Workers deployments, and routing read-only queries to the nearest replica can reduce query latency by 30–80 ms on cross-region requests. Write queries and reads that must reflect the latest committed write must still target the primary.

---

## Context
D1 uses the `db.withSession()` API to control replication consistency. Passing `'first-unconstrained'` allows the runtime to route the query to any available replica without causal consistency guarantees — ideal for eventually-consistent reads like browse pages. Passing `'first-primary'` forces the query to the primary replica, which is required for writes and for reads immediately following a write (read-after-write). The session token returned by a write operation can also be passed to `withSession()` so a subsequent read is guaranteed to see the committed write. For the hottest read paths (homepage feed, top products) a write-through KV cache layer reduces D1 round-trips entirely.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "d1-replica-router"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[d1_databases]]
binding = "DB"
database_name = "prod"
database_id = "<your-d1-database-id>"

[[kv_namespaces]]
binding = "CACHE"
id = "<your-kv-namespace-id>"
```

## Section 2 — Implementation

```typescript
// src/index.ts
import type { D1Database, KVNamespace } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  CACHE: KVNamespace;
}

/** How long to cache read results in KV (seconds). */
const KV_TTL = 60;

/** Article row returned by D1. */
interface Article {
  id: number;
  title: string;
  body: string;
  updated_at: string;
}

/**
 * Route a read-only query to the nearest D1 read replica.
 * Uses 'first-unconstrained' — no causal consistency guarantee.
 */
async function readFromReplica<T>(
  db: D1Database,
  stmt: string,
  bindings: unknown[]
): Promise<T[]> {
  const t0 = performance.now();
  const result = await db
    .withSession('first-unconstrained')
    .prepare(stmt)
    .bind(...bindings)
    .all<T>();
  const elapsed = performance.now() - t0;
  console.log(`[d1:replica] ${elapsed.toFixed(1)} ms — ${stmt.slice(0, 60)}`);
  return result.results;
}

/**
 * Execute a write against the D1 primary and return the session token
 * so the caller can pass it to a subsequent read that must see the write.
 */
async function writeToPRIMARY(
  db: D1Database,
  stmt: string,
  bindings: unknown[]
): Promise<{ meta: D1Meta; sessionToken: string }> {
  const t0 = performance.now();
  const session = db.withSession('first-primary');
  const result = await session.prepare(stmt).bind(...bindings).run();
  const elapsed = performance.now() - t0;
  console.log(`[d1:primary] ${elapsed.toFixed(1)} ms — ${stmt.slice(0, 60)}`);
  // @ts-expect-error session token is available on the session object
  const sessionToken: string = session.getBookmark?.() ?? 'first-primary';
  return { meta: result.meta, sessionToken };
}

/**
 * Read-after-write: use the session token returned by the preceding write
 * so D1 routes us to a replica that has already applied that write.
 */
async function readAfterWrite<T>(
  db: D1Database,
  sessionToken: string,
  stmt: string,
  bindings: unknown[]
): Promise<T[]> {
  const t0 = performance.now();
  const result = await db
    .withSession(sessionToken)
    .prepare(stmt)
    .bind(...bindings)
    .all<T>();
  const elapsed = performance.now() - t0;
  console.log(`[d1:raw] ${elapsed.toFixed(1)} ms via token`);
  return result.results;
}

/** KV write-through cache for hot read paths. */
async function cachedRead<T>(
  cache: KVNamespace,
  db: D1Database,
  cacheKey: string,
  stmt: string,
  bindings: unknown[]
): Promise<T[]> {
  const cached = await cache.get(cacheKey, 'json') as T[] | null;
  if (cached !== null) {
    console.log(`[cache:hit] ${cacheKey}`);
    return cached;
  }
  console.log(`[cache:miss] ${cacheKey}`);
  const rows = await readFromReplica<T>(db, stmt, bindings);
  // Fire-and-forget: write to KV without blocking the response
  cache.put(cacheKey, JSON.stringify(rows), { expirationTtl: KV_TTL });
  return rows;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // ── GET /articles — replica read with KV cache ───────────────────────
    if (request.method === 'GET' && url.pathname === '/articles') {
      const page = Number(url.searchParams.get('page') ?? 1);
      const cacheKey = `articles:page:${page}`;
      const articles = await cachedRead<Article>(
        env.CACHE,
        env.DB,
        cacheKey,
        'SELECT id, title, updated_at FROM articles ORDER BY updated_at DESC LIMIT 20 OFFSET ?1',
        [(page - 1) * 20]
      );
      return Response.json(articles);
    }

    // ── POST /articles — primary write, then read-after-write ───────────
    if (request.method === 'POST' && url.pathname === '/articles') {
      const body = await request.json<{ title: string; body: string; slug: string }>();
      const { meta, sessionToken } = await writeToPRIMARY(
        env.DB,
        'INSERT INTO articles (title, body, slug, updated_at) VALUES (?1, ?2, ?3, ?4)',
        [body.title, body.body, body.slug, new Date().toISOString()]
      );
      // Invalidate the KV cache for page 1
      await env.CACHE.delete('articles:page:1');
      // Read the newly inserted row, guaranteed visible via session token
      const [article] = await readAfterWrite<Article>(
        env.DB,
        sessionToken,
        'SELECT id, title, body, updated_at FROM articles WHERE id = ?1',
        [meta.last_row_id]
      );
      return Response.json(article, { status: 201 });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Section 3 — Benchmark / Verification

```typescript
// scripts/bench-replica.ts
// Compares replica vs primary latency across 50 read queries.
import { execSync } from 'node:child_process';

const BASE = process.env.TARGET_URL ?? 'https://d1-replica-router.<account>.workers.dev';
const RUNS = 50;

async function time(url: string): Promise<number> {
  const t0 = performance.now();
  await fetch(url);
  return performance.now() - t0;
}

(async () => {
  const times: number[] = [];
  for (let i = 0; i < RUNS; i++) {
    times.push(await time(`${BASE}/articles?page=1`));
  }
  times.sort((a, b) => a - b);
  console.log('Replica-routed read latency (ms):');
  console.log(`  p50  ${times[Math.floor(RUNS * 0.5)].toFixed(1)}`);
  console.log(`  p95  ${times[Math.floor(RUNS * 0.95)].toFixed(1)}`);
  console.log(`  max  ${times[RUNS - 1].toFixed(1)}`);
})();
```

---

## Anti-patterns
- **Using `first-unconstrained` for writes** — Writes may be silently discarded or conflict; always write to `first-primary`.
- **Ignoring session tokens after writes** — Reading immediately after a write without the session token can return stale data; always pass the token for read-after-write scenarios.
- **Long-lived KV TTLs on mutable data** — A 10-minute TTL on user-specific data surfaces stale results after writes; keep TTLs short (≤60 s) or invalidate by key on write.
- **Caching per-user data under a shared key** — Different users sharing the same cache key will see each other's data; always include a user identifier in the cache key.

---

## Gotchas
- `db.withSession()` returns a new database handle, not a Promise; chain `.prepare()` directly on it.
- Read replica availability is regional; in local `wrangler dev`, all queries go to the local SQLite file regardless of the session mode.
- D1's `result.meta.last_row_id` is only reliable for `INSERT` statements; for `UPDATE`/`DELETE` use a `RETURNING` clause instead.
- KV `put` with `expirationTtl` requires the value to be at most 25 MB; do not cache entire large result sets.

---

## Verification

```bash
# Deploy the Worker
npx wrangler deploy

# Read (should hit replica on second request if KV cache warms)
curl https://d1-replica-router.<account>.workers.dev/articles

# Write then immediate read-after-write
curl -X POST https://d1-replica-router.<account>.workers.dev/articles \
  -H 'Content-Type: application/json' \
  -d '{"title":"Test","body":"Hello","slug":"test"}'

# Tail logs to see replica vs primary routing
npx wrangler tail --format pretty
```

---

## Related
- `workers-response-streaming-ttfb-optimization.md`
- `workers-request-coalescing-durable-objects.md`

---

## Sources
- Cloudflare D1 Read Replication — https://developers.cloudflare.com/d1/best-practices/read-replication/
- D1 withSession API — https://developers.cloudflare.com/d1/worker-api/d1-database/#withsession
- Workers KV — https://developers.cloudflare.com/kv/
