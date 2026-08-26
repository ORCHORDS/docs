# D1 vs Hyperdrive Connection Patterns for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers project is growing and you are deciding between Cloudflare D1 (managed SQLite at the edge) and Cloudflare Hyperdrive (connection pooler that proxies an existing PostgreSQL or MySQL database). You need to know which fits your current workload and how to migrate from one to the other as data volume increases.

## Context

D1 and Hyperdrive solve different problems. D1 is a first-class serverless database — you do not bring your own server. Hyperdrive is not a database; it is a connection pooler and regional caching layer that sits in front of a database you already operate. Understanding which to use requires looking at data volume, latency profile, query complexity, and operational overhead.

---

## Decision Matrix

| Dimension | D1 | Hyperdrive + Postgres/MySQL |
|---|---|---|
| Own a DB server? | No — fully managed | Yes — you bring it |
| Data volume sweet spot | Up to ~500 GB / table | Unlimited (your DB's limits) |
| Write latency | ~10–30 ms edge-local | ~5–50 ms to regional pooler |
| Read latency (cold) | ~5–15 ms | ~5–30 ms to pooler + DB RTT |
| SQL dialect | SQLite | PostgreSQL / MySQL |
| Full-text search | FTS5 (SQLite) | pg_trgm / full Postgres FTS |
| JSON support | json1 extension | JSONB (Postgres), JSON (MySQL) |
| Transactions | Single-node ACID | Full ACID + savepoints |
| Schema migrations | Manual or via migration tool | Any migration framework |
| Monthly cost baseline | Included in Workers paid plan | Hyperdrive + external DB costs |

## Binding Configuration

```toml
# wrangler.toml

# D1 binding
[[d1_databases]]
binding  = "DB"
database_name = "my-app-db"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# Hyperdrive binding (points to an existing Postgres instance)
[[hyperdrive]]
binding  = "HYPERDRIVE"
id       = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
```

## D1 Access Pattern

```typescript
// src/db/d1Client.ts
import type { D1Database } from '@cloudflare/workers-types';

export async function getUserD1(
  db: D1Database,
  userId: string,
): Promise<{ id: string; email: string } | null> {
  return db
    .prepare(`SELECT id, email FROM users WHERE id = ? AND deleted_at IS NULL`)
    .bind(userId)
    .first<{ id: string; email: string }>();
}
```

## Hyperdrive Access Pattern

```typescript
// src/db/hyperdrive.ts
// Hyperdrive exposes a standard TCP Postgres connection string.
// Use any Postgres client that works in the Workers runtime.
// @neondatabase/serverless is the recommended edge-compatible client.
import { neon } from '@neondatabase/serverless';
import type { Hyperdrive } from '@cloudflare/workers-types';

export function getHyperdriveClient(hyperdrive: Hyperdrive) {
  // hyperdrive.connectionString injects Hyperdrive's regional pooler URL.
  // The neon() client uses HTTP/fetch under the hood — no raw TCP socket needed.
  return neon(hyperdrive.connectionString);
}

export async function getUserHyperdrive(
  hyperdrive: Hyperdrive,
  userId: string,
): Promise<{ id: string; email: string } | null> {
  const sql = getHyperdriveClient(hyperdrive);
  const rows = await sql`
    SELECT id, email
    FROM users
    WHERE id = ${userId}
      AND deleted_at IS NULL
  `;
  return (rows[0] as { id: string; email: string }) ?? null;
}
```

## Hyperdrive Pool Sizing

```typescript
// Hyperdrive's maxPoolSize is configured via the dashboard or Wrangler,
// not at query time. The recommended starting point:
//
//   maxPoolSize = (expected concurrent Workers invocations) * 2
//
// Workers scale to thousands of concurrent invocations. Set maxPoolSize
// to a value your database server can handle — typically 10–100 for
// most managed Postgres plans (e.g. Neon, Supabase, RDS).
//
// Configure via CLI:
//   npx wrangler hyperdrive update <id> --max-connections 50
//
// Or in the Cloudflare dashboard under Workers > Hyperdrive.

// At query time, all connections are managed by Hyperdrive automatically.
// Your Worker does not manage a connection pool itself.
```

## Latency Comparison

```
D1 (edge-local SQLite)
  Worker in FRA → D1 replica in FRA: ~5–15 ms
  Worker in SIN → D1 replica in SIN: ~5–15 ms
  Write propagation to other regions: eventual (seconds to minutes)

Hyperdrive + Postgres (regionalised pooler)
  Worker in FRA → Hyperdrive FRA pooler → Postgres eu-west-1: ~15–40 ms
  Worker in SIN → Hyperdrive SIN pooler → Postgres eu-west-1: ~80–150 ms
    (cross-region penalty when DB is not co-located with user)
  Hyperdrive caches repeated SELECT results for 60 s by default.

Conclusion:
  - D1 wins on read latency for globally distributed reads (edge-local replicas).
  - Hyperdrive wins when you need Postgres-only features or data volumes
    beyond D1's practical range.
  - For writes, both have comparable latency; D1 routes writes to a single
    primary, Hyperdrive writes go to your Postgres primary directly.
```

## Migration Path: D1 → Hyperdrive-backed Postgres

```typescript
// Step 1: Export D1 data via the REST API
//   curl https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{db_id}/export \
//     -H "Authorization: Bearer $CF_API_TOKEN" > dump.sql

// Step 2: The dump is SQLite SQL. Convert to PostgreSQL:
//   - Replace INTEGER PRIMARY KEY → SERIAL PRIMARY KEY or BIGINT GENERATED ALWAYS
//   - Replace TEXT (for dates) → TIMESTAMPTZ
//   - Replace json_extract(...) in views → jsonb operators
//   - Remove SQLite-specific PRAGMA statements

// Step 3: Load into Postgres
//   psql $DATABASE_URL < dump_converted.sql

// Step 4: Create Hyperdrive config pointing at the new Postgres
//   npx wrangler hyperdrive create my-app-hd \
//     --connection-string "postgres://user:pass@host:5432/dbname"

// Step 5: Update wrangler.toml to add [[hyperdrive]] binding
//   and update application code to use the Hyperdrive client
//   (swap DB.prepare().bind() calls for tagged template SQL)

// Step 6: Run both in parallel with a feature flag before cutting over
export function getDb(env: Env) {
  if (env.USE_HYPERDRIVE === 'true') {
    return { type: 'hyperdrive' as const, client: neon(env.HYPERDRIVE.connectionString) };
  }
  return { type: 'd1' as const, client: env.DB };
}
```

## Anti-patterns

- **Using Hyperdrive when you have no existing database.** Hyperdrive is not a database. If you are starting from zero, D1 is the right choice — less operational overhead, no server to provision, no VPC to configure.
- **Connecting directly to Postgres from a Worker without Hyperdrive.** Raw TCP from Workers requires the `connect()` API and gives you no connection pooling. Every Worker invocation opens and closes its own connection, exhausting Postgres's `max_connections` under moderate load.
- **Assuming Hyperdrive caching is safe for all queries.** Hyperdrive caches `SELECT` results. If your application requires read-your-own-writes consistency immediately after a mutation, disable caching for those queries: `neon(env.HYPERDRIVE.connectionString, { fetchConnectionCache: false })`.
- **Migrating to Postgres prematurely.** D1 handles most OLTP workloads comfortably up to hundreds of millions of rows. Do not absorb the operational cost of a Postgres server before you need Postgres features.

## Gotchas

- D1's SQLite dialect does not support `RETURNING` on `INSERT`/`UPDATE` in older D1 versions — check the current D1 release notes. Postgres via Hyperdrive supports `RETURNING` fully.
- Hyperdrive's default query cache TTL is 60 seconds. This can cause stale reads if you mutate and read in quick succession across different Worker invocations. Tune with `--cache-ttl` on the Hyperdrive config.
- D1 uses `datetime('now')` for current timestamps; Postgres uses `NOW()` or `CURRENT_TIMESTAMP`. Update all timestamp expressions during migration.
- Hyperdrive connection strings contain credentials. Store them in Wrangler secrets, not in `wrangler.toml` or source code: `npx wrangler secret put HYPERDRIVE_CONNECTION_STRING`.

## Verification

```bash
# Verify D1 database size
npx wrangler d1 info my-app-db

# Test Hyperdrive connectivity from a Worker (logs latency)
npx wrangler tail my-worker --format pretty

# Inspect Hyperdrive config
npx wrangler hyperdrive get <hyperdrive-id>

# Benchmark D1 query latency locally
npx wrangler d1 execute my-app-db \
  --command "SELECT COUNT(*) FROM items" \
  --json
```

## Related

- `d1-cursor-pagination-workers.md` — pagination strategies for large D1 tables
- `d1-soft-delete-pattern-workers.md` — patterns that work the same on both D1 and Postgres
- Cloudflare Hyperdrive documentation
- Neon serverless driver for Workers

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/hyperdrive/
- https://developers.cloudflare.com/hyperdrive/configuration/connect-to-postgres/
- https://neon.tech/docs/serverless/serverless-driver
