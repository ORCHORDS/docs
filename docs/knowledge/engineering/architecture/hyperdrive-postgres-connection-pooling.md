# Hyperdrive Connection Pooling — Workers to Postgres at the Edge

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A Cloudflare Workers application needs to query a Postgres (or MySQL) database that is
not D1 — perhaps for a legacy system, a managed Postgres service (Neon, Supabase, PlanetScale),
or a self-hosted database with rich SQL features that D1 cannot yet match (materialized
views, full-text search with `tsvector`, PostGIS, pg_vector). Workers cannot maintain
long-lived TCP connections (each invocation is ephemeral), so every request would open a
fresh Postgres connection, which costs 20–100 ms and risks connection pool exhaustion.
Cloudflare Hyperdrive solves this by maintaining a persistent, regionally-distributed
connection pool on Cloudflare's network, exposing a connection string that Workers reach
via a local binding with sub-millisecond setup time.

Concrete triggers:
- Migrating an existing Postgres-backed API to Workers without re-writing the schema to D1
- Using `pg_vector` for chord embedding similarity search from a Worker
- Querying a Supabase database with Row Level Security from the edge
- Combining D1 (hot reads) with Postgres (analytics aggregations) in one application

---

## Context

### The cold-connection problem

A vanilla Workers-to-Postgres architecture without Hyperdrive:

```
Worker invocation (ephemeral, ~0 ms)
    │
    ├── TCP handshake to Postgres ──────────────────── ~15 ms (same region)
    ├── TLS handshake ──────────────────────────────── ~15 ms
    ├── Postgres auth (md5/SCRAM) ──────────────────── ~5 ms
    ├── Query execution ────────────────────────────── ~2 ms
    └── Total latency ──────────────────────────────── ~37 ms per query
```

At 1000 req/s, this means 1000 new Postgres connections per second — typical Postgres
servers support 100–500 total connections. Worker requests begin failing with
`FATAL: remaining connection slots reserved`.

### How Hyperdrive fixes it

```
Worker invocation (ephemeral)
    │
    ├── Connect to Hyperdrive local endpoint ─────── ~0.1 ms (in-network)
    ├── Hyperdrive reuses existing pooled connection  ~0 ms (pool warm)
    ├── Query execution on Postgres ─────────────── ~2 ms
    └── Total latency ───────────────────────────── ~2.1 ms per query
```

Hyperdrive maintains a pool of persistent connections per Cloudflare region, close to the
database's actual region. Workers connect to Hyperdrive (not Postgres directly), and
Hyperdrive proxies query traffic over the persistent pool.

---

## Architecture

```
                    Cloudflare Edge (global)
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  Worker invocation                                             │
│      │  sql`SELECT ...`  via postgres.js or pg-compatible lib  │
│      ▼                                                         │
│  Hyperdrive local endpoint (env.HYPERDRIVE.connectionString)  │
│      │  sub-ms in-process routing                              │
│      ▼                                                         │
│  Hyperdrive regional proxy  ──── persistent pool ────────────▶│──▶ Postgres
│  (Cloudflare-managed, near DB)      (5–10 connections)         │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

Hyperdrive also caches read queries using KV-like semantics (configurable TTL), so
repeated identical `SELECT` statements return from cache without touching Postgres.

---

## Setup

### 1. Create the Hyperdrive config

```bash
# Create a Hyperdrive config pointing to your Postgres instance
wrangler hyperdrive create chord-db \
  --connection-string "postgresql://user:password@db.example.com:5432/chorddb"

# Output includes the Hyperdrive config ID:
# Created Hyperdrive config chord-db with ID abc123...
```

### 2. Declare the binding in wrangler.toml

```toml
name = "chord-api"
main = "src/index.ts"

[[hyperdrive]]
binding = "HYPERDRIVE"
id = "abc123..."  # From wrangler hyperdrive create output

# Optional: disable caching for mutation-heavy Workers
# caching = { disabled = true }
```

### 3. Use in the Worker

```typescript
// src/index.ts
import postgres from 'postgres';  // postgres.js — works in Workers via Hyperdrive

interface Env {
  HYPERDRIVE: Hyperdrive;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Create the sql client using Hyperdrive's connection string
    // IMPORTANT: create per-request, not at module scope — Workers are ephemeral
    const sql = postgres(env.HYPERDRIVE.connectionString, {
      // Hyperdrive handles the actual pool; set max to 1 here
      max: 1,
    });

    try {
      const chords = await sql`
        SELECT id, name, voicing, created_at
        FROM chords
        WHERE user_id = ${getUserId(request)}
        ORDER BY created_at DESC
        LIMIT 20
      `;

      return Response.json(chords);
    } finally {
      // Release the logical connection back to Hyperdrive's pool
      await sql.end({ timeout: 5 });
    }
  },
};
```

---

## Query Caching Configuration

Hyperdrive's built-in read cache intercepts identical SQL strings and returns cached
results within a configured TTL window, further reducing Postgres load.

```toml
[[hyperdrive]]
binding = "HYPERDRIVE"
id = "abc123..."

[hyperdrive.caching]
# Cache TTL in seconds (default: 60)
max_age = 30
# Stale-while-revalidate window
stale_while_revalidate = 15
```

Rules:
- Only `SELECT` statements are cached; mutations bypass the cache unconditionally
- Cache key is the full SQL string including parameter values (after binding)
- Cache is invalidated on any DML (`INSERT`/`UPDATE`/`DELETE`) to the same connection
- Caching can be disabled per-binding or globally for a Worker

```typescript
// Bypass cache for a specific query (add a comment to break the cache key)
const fresh = await sql`
  /* no-cache */
  SELECT balance FROM accounts WHERE id = ${accountId}
`;
```

---

## Combining Hyperdrive (Postgres) with D1

A hybrid pattern uses D1 for low-latency hot data and Postgres via Hyperdrive for
complex analytics:

```typescript
interface Env {
  HYPERDRIVE: Hyperdrive;
  DB: D1Database;  // D1 for fast, simple lookups
}

async function getChordWithAnalytics(chordId: string, env: Env): Promise<Response> {
  // D1: fast lookup of chord metadata (cached in Workers KV automatically)
  const chord = await env.DB
    .prepare('SELECT * FROM chords WHERE id = ?')
    .bind(chordId)
    .first();

  if (!chord) return new Response('Not found', { status: 404 });

  // Hyperdrive/Postgres: complex analytics query not feasible in D1
  const sql = postgres(env.HYPERDRIVE.connectionString, { max: 1 });
  try {
    const analytics = await sql`
      SELECT
        COUNT(DISTINCT user_id)    AS unique_plays,
        AVG(EXTRACT(EPOCH FROM play_duration)) AS avg_play_seconds,
        array_agg(DISTINCT tag ORDER BY tag) AS tags
      FROM chord_events
      WHERE chord_id = ${chordId}
        AND played_at > NOW() - INTERVAL '30 days'
      GROUP BY chord_id
    `;
    return Response.json({ ...chord, analytics: analytics[0] ?? null });
  } finally {
    await sql.end({ timeout: 5 });
  }
}
```

---

## pg_vector for Chord Similarity Search

```sql
-- Postgres schema with pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chord_embeddings (
  chord_id  TEXT PRIMARY KEY REFERENCES chords(id),
  embedding vector(1536),  -- OpenAI / Cloudflare AI embedding dimension
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON chord_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

```typescript
async function findSimilarChords(
  queryEmbedding: number[],
  env: Env,
  limit = 10
): Promise<Array<{ chord_id: string; distance: number }>> {
  const sql = postgres(env.HYPERDRIVE.connectionString, { max: 1 });
  try {
    const embedding = `[${queryEmbedding.join(',')}]`;
    const results = await sql<Array<{ chord_id: string; distance: number }>>`
      SELECT chord_id, embedding <=> ${embedding}::vector AS distance
      FROM chord_embeddings
      ORDER BY distance
      LIMIT ${limit}
    `;
    return results;
  } finally {
    await sql.end({ timeout: 5 });
  }
}
```

---

## D1 Schema for Caching Hyperdrive Results

When Hyperdrive's built-in cache TTL is insufficient (e.g., you need invalidation on
write events), implement a manual cache layer in D1:

```sql
-- D1 cache for expensive Postgres aggregations
CREATE TABLE pg_cache (
  cache_key   TEXT PRIMARY KEY,
  value       TEXT NOT NULL,  -- JSON
  expires_at  INTEGER NOT NULL,  -- Unix seconds
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_pg_cache_expires ON pg_cache(expires_at);
```

```typescript
async function getCachedAnalytics(
  chordId: string, env: Env, ttlSeconds = 300
): Promise<unknown> {
  const cacheKey = `analytics:${chordId}`;
  const now = Math.floor(Date.now() / 1000);

  // Check D1 cache first
  const cached = await env.DB
    .prepare('SELECT value FROM pg_cache WHERE cache_key = ? AND expires_at > ?')
    .bind(cacheKey, now)
    .first<{ value: string }>();

  if (cached) return JSON.parse(cached.value);

  // Cache miss — query Postgres
  const sql = postgres(env.HYPERDRIVE.connectionString, { max: 1 });
  let analytics: unknown;
  try {
    [analytics] = await sql`SELECT ... FROM chord_events WHERE chord_id = ${chordId}`;
  } finally {
    await sql.end({ timeout: 5 });
  }

  // Write to D1 cache
  await env.DB
    .prepare(`
      INSERT OR REPLACE INTO pg_cache (cache_key, value, expires_at)
      VALUES (?, ?, ?)
    `)
    .bind(cacheKey, JSON.stringify(analytics), now + ttlSeconds)
    .run();

  return analytics;
}
```

---

## Mobile API Consumer Considerations (example project React Native)

Hyperdrive is entirely server-side and invisible to the React Native app. From the
mobile client's perspective, all requests go to `api.example.com` and receive standard
JSON responses. Considerations:

- **Response pagination**: Postgres queries may return large result sets. Always apply
  cursor-based pagination to avoid transferring large payloads to mobile.
- **Offline-first**: Cache Postgres query results in the app (via MMKV or SQLite) to
  support offline viewing. The server can send `Cache-Control: max-age=300` on analytics
  endpoints.
- **Query complexity**: Mobile-initiated queries should be simple lookups. Complex
  aggregations should be pre-computed by a background Cron Worker and stored in D1 for
  fast edge reads.

```typescript
// Pagination pattern for mobile clients
router.get('/v1/chords', async (req, env) => {
  const cursor = req.query.cursor ?? null;
  const limit = Math.min(Number(req.query.limit ?? 20), 100);

  const sql = postgres(env.HYPERDRIVE.connectionString, { max: 1 });
  try {
    const rows = await sql`
      SELECT id, name, created_at FROM chords
      WHERE (${cursor}::text IS NULL OR created_at < ${cursor}::timestamptz)
      ORDER BY created_at DESC
      LIMIT ${limit + 1}
    `;
    const hasMore = rows.length > limit;
    const items = rows.slice(0, limit);
    const nextCursor = hasMore ? items[items.length - 1].created_at : null;
    return Response.json({ items, nextCursor });
  } finally {
    await sql.end({ timeout: 5 });
  }
});
```

---

## Anti-patterns

- **Creating `postgres()` client at module scope**: Workers share module scope across
  requests in the same isolate, but the connection string may be stale after a Hyperdrive
  rotation. Always construct the client per-request and call `sql.end()` when done.
- **Setting `max` > 1 on the `postgres()` client**: Hyperdrive manages the real pool.
  Setting `max: 10` in the Worker just creates 10 logical connections per Worker
  invocation that Hyperdrive must multiplex — wasteful and slower.
- **Using Hyperdrive for `localhost` databases in production**: Hyperdrive must be able
  to reach the Postgres endpoint from Cloudflare's network. Use Cloudflare Tunnel
  if your DB is behind a private network.
- **Not calling `sql.end()`**: Forgetting to release the connection prevents Hyperdrive
  from reclaiming it to the pool until the Worker invocation times out.
- **Disabling caching on read-heavy routes**: Hyperdrive's read cache provides ~10×
  throughput improvement for repeated identical queries. Only disable it for strongly
  consistent reads.
- **Mixing Hyperdrive and D1 for the same entity**: Pick one authoritative store per
  entity. Use Hyperdrive/Postgres when D1 is insufficient; don't write the same data
  to both and merge later.

---

## Gotchas

- Hyperdrive requires Cloudflare Workers paid plan ($5/month as of 2025; first 10 GB
  free per month).
- Connection strings must use `postgresql://` scheme (not `postgres://`) in some client
  libraries. `postgres.js` accepts both.
- Hyperdrive does NOT support Postgres `LISTEN`/`NOTIFY` — these require a persistent
  TCP connection, which Hyperdrive's ephemeral model cannot maintain.
- Prepared statements with `DEALLOCATE` or session-scoped state (`SET LOCAL`, temporary
  tables) do not persist across requests because each request may get a different pooled
  connection.
- The Hyperdrive connection string (from `env.HYPERDRIVE.connectionString`) is a
  localhost URL at runtime — do not log it, as it encodes credentials.
- Hyperdrive is region-aware: it connects to the Postgres instance from the nearest
  Cloudflare data centre, not from the edge PoP handling the request. There is one hop:
  user → edge PoP → Hyperdrive regional proxy → Postgres.

---

## Verification

```bash
# List Hyperdrive configs
wrangler hyperdrive list
# NAME       ID          DATABASE   STATUS
# chord-db   abc123...   chorddb    active

# Test connectivity from wrangler dev
wrangler dev --local
curl http://localhost:8787/v1/chords
# Should return results without connection timeout errors

# Check pool stats (Hyperdrive does not expose pool metrics directly;
# check Postgres pg_stat_activity instead)
# Expected: far fewer connections than Worker instances
psql $PG_URL -c "SELECT count(*) FROM pg_stat_activity WHERE application_name = 'hyperdrive';"
```

---

## Related

- `caching-layers-cloudflare-workers-kv-r2.md` — KV and R2 caching strategies
- `read-through-cache.md` — cache-aside pattern applied to Hyperdrive results
- `d1-batch-operations-query-optimisation.md` — D1 for simple hot data
- `distributed-caching.md` — multi-layer cache design
- `data-replication-strategies.md` — Postgres to D1 replication
- `zero-downtime-schema-migrations.md` — Postgres migrations without downtime

---

## Sources

- Cloudflare Hyperdrive documentation (developers.cloudflare.com/hyperdrive)
- postgres.js library (github.com/porsager/postgres) — Workers-compatible Postgres client
- pgvector extension (github.com/pgvector/pgvector)
- Cloudflare Workers limits and pricing (developers.cloudflare.com/workers/platform/pricing)
