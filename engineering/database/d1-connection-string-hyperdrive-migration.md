# D1 Connection String and Hyperdrive Migration

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project / example.com starts on Cloudflare D1 for simplicity but may need to migrate reads or
writes to a Postgres-compatible database (Neon, Supabase, CockroachDB) as traffic grows. The
reverse path — migrating from an existing Postgres cluster to D1 — is equally common when moving
to the edge. Cloudflare Hyperdrive bridges the gap: it accepts a standard `postgres://` connection
string and exposes a connection-pooled, geographically-cached proxy that Workers can reach via a
single binding, with the same SQL API shape as D1.

## Context

D1 uses a proprietary binding (`env.DB: D1Database`) rather than a connection string. Hyperdrive
uses a connection string (`env.HYPERDRIVE.connectionString`) that maps to a standard `pg` or
`postgres` driver. Migrating between the two requires switching the query layer but can be done
incrementally — keep D1 for writes during the transition and read from Hyperdrive, or vice versa.
Both bindings live in `wrangler.toml` and are injected into the Worker's `Env` interface.

## Wrangler Configuration

### D1 Binding (current)

```toml
# wrangler.toml
name = "example project-worker"
main = "src/worker.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding  = "DB"
database_name = "example project-prod"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

### Hyperdrive Binding (target Postgres)

```toml
[[hyperdrive]]
binding    = "HYPERDRIVE"
id         = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
# Connection string stored in Cloudflare dashboard, not in toml
```

Create a Hyperdrive config pointing at an external Postgres cluster:

```bash
npx wrangler hyperdrive create example project-hyperdrive \
  --connection-string "postgres://user:pass@db.neon.tech:5432/example project?sslmode=require"
```

## Unified Query Abstraction Layer

Build a thin abstraction so application code is agnostic to the underlying database. Both D1 and
the `postgres` npm package return rows as plain objects, making the interface compatible.

```typescript
// src/db.ts
import postgres from 'postgres';   // npm: postgres (Porsager)

export interface Env {
  DB?: D1Database;           // present when using D1
  HYPERDRIVE?: Hyperdrive;   // present when using Hyperdrive
}

export type QueryResult<T> = T[];

export async function query<T>(
  env: Env,
  sql: string,
  values: unknown[] = []
): Promise<QueryResult<T>> {
  if (env.DB) {
    // D1 path — positional binding uses ?1, ?2, ...
    const d1Sql = sql.replace(/\$(\d+)/g, (_, n) => `?${n}`);
    const stmt = env.DB.prepare(d1Sql);
    const bound = values.length ? stmt.bind(...values) : stmt;
    const { results } = await bound.all<T>();
    return results;
  }

  if (env.HYPERDRIVE) {
    // Hyperdrive (Postgres) path — uses $1, $2 natively
    const sql_pg = postgres(env.HYPERDRIVE.connectionString, { max: 5 });
    const rows = await sql_pg.unsafe<T[]>(sql, values as string[]);
    await sql_pg.end();
    return rows as T[];
  }

  throw new Error('No database binding found in Env');
}
```

## Step-by-Step Migration from D1 to Hyperdrive

### 1. Export D1 data

```bash
# Dump D1 to SQL via Wrangler
npx wrangler d1 export example project-prod --output example project-dump.sql

# Or export as JSON for selective migration
npx wrangler d1 execute example project-prod \
  --command "SELECT * FROM posts" \
  --json > posts.json
```

### 2. Transform SQLite SQL to Postgres SQL

```typescript
// Common SQLite → Postgres transforms needed before import
function sqliteToPostgres(sqlite: string): string {
  return sqlite
    .replace(/INTEGER PRIMARY KEY/gi, 'SERIAL PRIMARY KEY')
    .replace(/unixepoch\(\)/gi, "EXTRACT(EPOCH FROM NOW())::INTEGER")
    .replace(/TEXT/gi, 'TEXT')       // no-op, kept for clarity
    .replace(/BLOB/gi, 'BYTEA')
    .replace(/REAL/gi, 'DOUBLE PRECISION')
    .replace(/\bIF NOT EXISTS\b/gi, 'IF NOT EXISTS');
}
```

### 3. Shadow reads — dual-write validation

```typescript
// src/shadow-query.ts
export async function shadowQuery<T>(
  env: Env,
  sql: string,
  values: unknown[]
): Promise<QueryResult<T>> {
  const [d1Result, pgResult] = await Promise.allSettled([
    query<T>({ DB: env.DB }, sql, values),
    query<T>({ HYPERDRIVE: env.HYPERDRIVE }, sql, values),
  ]);

  if (d1Result.status === 'fulfilled' && pgResult.status === 'fulfilled') {
    const d1Ids = d1Result.value.map((r: any) => r.id).sort().join(',');
    const pgIds = pgResult.value.map((r: any) => r.id).sort().join(',');
    if (d1Ids !== pgIds) {
      console.warn('Shadow query mismatch', { sql, d1Ids, pgIds });
    }
  }

  // Serve D1 until migration is validated
  return d1Result.status === 'fulfilled'
    ? d1Result.value
    : Promise.reject(d1Result.reason);
}
```

## Anti-patterns

- Referencing the Hyperdrive connection string directly in source code — it contains credentials; always use `env.HYPERDRIVE.connectionString` injected at runtime
- Opening a new `postgres()` client per request without calling `.end()` — Hyperdrive manages pooling, but unclosed clients leak in the Worker process
- Running `ALTER TABLE` SQLite syntax against Postgres — D1 and Postgres have different DDL dialects; transform DDL before migration
- Switching all traffic instantly without a shadow-read validation period — data divergence errors surface only under production load

## Gotchas

- Hyperdrive requires `compatibility_flags = ["nodejs_compat"]` or `nodejs_compat_v2` in `wrangler.toml` to use Node.js-based Postgres drivers
- D1 positional parameters use `?1`, `?2`; Postgres uses `$1`, `$2` — the abstraction layer must translate between them
- Hyperdrive caches `SELECT` query results for ~5 seconds by default; mutations require disabling caching per-query or routing writes directly
- `wrangler d1 export` produces SQLite-dialect SQL, not Postgres-compatible SQL — always apply transforms before importing

## Verification

```bash
# Confirm Hyperdrive config exists and is active
npx wrangler hyperdrive list

# Tail the Worker for binding errors during shadow mode
npx wrangler tail example project-worker --format pretty

# Smoke-test Hyperdrive binding locally (requires --local flag is NOT used;
# Hyperdrive proxies require a real Cloudflare tunnel)
npx wrangler dev --remote
```

## Related

- `/documentation/categories/database/d1-connection-pooling-workers-hyperdrive-comparison.md`
- `/documentation/categories/database/d1-connection-pooling-workers.md`
- `/documentation/categories/database/postgresql-to-d1-migration-patterns.md`
- `/documentation/categories/database/connection-string-management.md`

## Sources

- https://developers.cloudflare.com/hyperdrive/
- https://developers.cloudflare.com/hyperdrive/get-started/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/hyperdrive/
- https://developers.cloudflare.com/d1/build-with-d1/import-export-data/
