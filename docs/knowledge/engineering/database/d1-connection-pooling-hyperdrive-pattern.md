# Connection Pooling Strategies: D1 vs Hyperdrive-Backed Databases

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your application starts on D1 (SQLite) and later needs to migrate to or run alongside an external PostgreSQL database — for features that require PostGIS, advanced JSON operators, or an existing data warehouse. You need to understand how connection management works in both cases, how Cloudflare Hyperdrive pools connections to Postgres, and how to switch between the two via a feature flag without rewriting every query.

## Context

D1 and Hyperdrive serve different roles:

- **D1** — Cloudflare-managed SQLite. Each Worker request gets a fresh SQLite connection to a regional replica. There is no connection pool to manage; connections are ephemeral and zero-cost.
- **Hyperdrive** — Cloudflare's connection pooler and caching proxy for external databases (Postgres, MySQL). It maintains a pool of persistent connections to your database server and hands them to Workers via a connection string that looks like a standard Postgres DSN.

Without Hyperdrive, every Worker request to an external Postgres opens a new TCP connection + TLS handshake + Postgres authentication handshake — 100–400 ms of overhead before the first query runs. Hyperdrive eliminates this by reusing existing connections from the pool.

## Solution

### 1. wrangler.toml: bind both D1 and Hyperdrive

```toml
# wrangler.toml
name = "example project-api"
main = "src/index.ts"
compatibility_date = "2024-08-01"

[[d1_databases]]
binding = "DB"          # D1 binding
database_name = "example project-db"
database_id = "<your-d1-database-id>"

[[hyperdrive]]
binding = "HYPERDRIVE"  # Hyperdrive binding
id = "<your-hyperdrive-config-id>"
```

### 2. Env interface

```typescript
// src/types/env.ts
export interface Env {
  DB: D1Database;           // SQLite / D1
  HYPERDRIVE: Hyperdrive;   // Hyperdrive -> Postgres
  USE_POSTGRES: string;     // Feature flag: 'true' | 'false'
}
```

### 3. Abstract database client

```typescript
// src/lib/db-client.ts
import postgres from 'postgres';  // npm install postgres

export type QueryResult<T> = { rows: T[] };

export interface DbClient {
  query<T = Record<string, unknown>>(sql: string, params?: unknown[]): Promise<QueryResult<T>>;
  batch<T = Record<string, unknown>>(queries: Array<{ sql: string; params?: unknown[] }>): Promise<QueryResult<T>[]>;
  close?(): Promise<void>;
}

/** D1 adapter */
export class D1Client implements DbClient {
  constructor(private readonly db: D1Database) {}

  async query<T>(sql: string, params: unknown[] = []): Promise<QueryResult<T>> {
    const stmt = this.db.prepare(sql);
    const bound = params.length > 0 ? stmt.bind(...params) : stmt;
    const result = await bound.all<T>();
    return { rows: result.results };
  }

  async batch<T>(queries: Array<{ sql: string; params?: unknown[] }>): Promise<QueryResult<T>[]> {
    const stmts = queries.map(({ sql, params = [] }) => {
      const stmt = this.db.prepare(sql);
      return params.length > 0 ? stmt.bind(...params) : stmt;
    });
    const results = await this.db.batch<T>(stmts);
    return results.map((r) => ({ rows: r.results }));
  }
}

/** Hyperdrive / Postgres adapter using the `postgres` npm package */
export class PostgresClient implements DbClient {
  private readonly sql: ReturnType<typeof postgres>;

  constructor(hyperdrive: Hyperdrive) {
    // Hyperdrive exposes a standard Postgres connection string
    // The `postgres` package handles connection reuse within the pool
    this.sql = postgres(hyperdrive.connectionString, {
      max: 5,           // max connections per Worker isolate (Hyperdrive pools globally)
      idle_timeout: 20, // seconds before an idle connection is released
      connect_timeout: 10,
    });
  }

  async query<T>(sql: string, params: unknown[] = []): Promise<QueryResult<T>> {
    // postgres.js uses tagged template literals; for dynamic SQL we use sql.unsafe
    const rows = params.length > 0
      ? await this.sql.unsafe<T[]>(sql, params as any[])
      : await this.sql.unsafe<T[]>(sql);
    return { rows: rows as unknown as T[] };
  }

  async batch<T>(queries: Array<{ sql: string; params?: unknown[] }>): Promise<QueryResult<T>[]> {
    // Postgres doesn't have a native batch API like D1; run in a transaction
    const results: QueryResult<T>[] = [];
    await this.sql.begin(async (tx) => {
      for (const { sql, params = [] } of queries) {
        const rows = params.length > 0
          ? await tx.unsafe<T[]>(sql, params as any[])
          : await tx.unsafe<T[]>(sql);
        results.push({ rows: rows as unknown as T[] });
      }
    });
    return results;
  }

  async close(): Promise<void> {
    await this.sql.end();
  }
}

/** Factory: pick D1 or Postgres based on feature flag */
export function createDbClient(env: { DB: D1Database; HYPERDRIVE: Hyperdrive; USE_POSTGRES: string }): DbClient {
  if (env.USE_POSTGRES === 'true') {
    return new PostgresClient(env.HYPERDRIVE);
  }
  return new D1Client(env.DB);
}
```

### 4. Repository using the abstract client

```typescript
// src/repositories/articles-generic.ts
import { DbClient } from '../lib/db-client';

export interface Article {
  id: number;
  tenant_id: string;
  title: string;
  body: string;
  created_at: string;
}

export class ArticlesRepository {
  constructor(
    private readonly db: DbClient,
    private readonly tenantId: string
  ) {}

  async list(limit = 50, offset = 0): Promise<Article[]> {
    const result = await this.db.query<Article>(
      `SELECT id, tenant_id, title, body, created_at
       FROM articles
       WHERE tenant_id = $1
       ORDER BY created_at DESC
       LIMIT $2 OFFSET $3`,
      [this.tenantId, limit, offset]
    );
    return result.rows;
  }

  async getById(id: number): Promise<Article | null> {
    const result = await this.db.query<Article>(
      `SELECT id, tenant_id, title, body, created_at
       FROM articles
       WHERE id = $1 AND tenant_id = $2`,
      [id, this.tenantId]
    );
    return result.rows[0] ?? null;
  }
}
```

> **Note on placeholders**: D1 uses `?` positional placeholders; Postgres uses `$1`, `$2`. If you need to support both with the same SQL string, write a small normalizer or maintain separate SQL strings per adapter. The abstract interface above uses `$n` style and relies on the D1 adapter to handle them (D1 actually accepts `?1`, `?2` style but not `$1` — adjust as needed or keep separate SQL files).

### 5. Worker handler with feature flag switching

```typescript
// src/index.ts
import { createDbClient } from './lib/db-client';
import { ArticlesRepository } from './repositories/articles-generic';
import { extractAuth } from './middleware/auth';
import type { Env } from './types/env';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    let auth;
    try {
      auth = await extractAuth(request);
    } catch (resp) {
      return resp as Response;
    }

    const db = createDbClient(env);
    const repo = new ArticlesRepository(db, auth.tenantId);

    const url = new URL(request.url);

    try {
      if (url.pathname === '/articles' && request.method === 'GET') {
        const articles = await repo.list();
        return Response.json({ articles });
      }

      if (url.pathname.startsWith('/articles/') && request.method === 'GET') {
        const id = parseInt(url.pathname.split('/').pop()!, 10);
        const article = await repo.getById(id);
        if (!article) return Response.json({ error: 'Not found' }, { status: 404 });
        return Response.json({ article });
      }

      return new Response('Not found', { status: 404 });
    } finally {
      // Close Postgres connections gracefully; D1 has no close step
      if (db.close) {
        ctx.waitUntil(db.close());
      }
    }
  },
};
```

### 6. Hyperdrive configuration via wrangler

```bash
# Create a Hyperdrive config pointing at your Postgres instance
npx wrangler hyperdrive create example project-hyperdrive \
  --connection-string "postgresql://user:password@db.example.com:5432/example project"

# List existing configs
npx wrangler hyperdrive list

# Update connection string (e.g. after password rotation)
npx wrangler hyperdrive update <config-id> \
  --connection-string "postgresql://user:newpassword@db.example.com:5432/example project"
```

### 7. Pool exhaustion handling

```typescript
// src/lib/db-client.ts (addition to PostgresClient)
export class PostgresClient implements DbClient {
  // ...

  async query<T>(sql: string, params: unknown[] = []): Promise<QueryResult<T>> {
    try {
      const rows = params.length > 0
        ? await this.sql.unsafe<T[]>(sql, params as any[])
        : await this.sql.unsafe<T[]>(sql);
      return { rows: rows as unknown as T[] };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);

      // Detect pool exhaustion or connection errors
      if (
        msg.includes('too many clients') ||
        msg.includes('connection timeout') ||
        msg.includes('pool is full')
      ) {
        // Return 503 so the caller (load balancer / retry middleware) can retry
        throw Object.assign(new Error('Database pool exhausted'), {
          status: 503,
          retryable: true,
        });
      }

      throw err;
    }
  }
}
```

## Implementation Details

- **D1 connection model**: Each Worker request receives a SQLite connection to the closest D1 regional replica. The connection is held for the duration of the request and then discarded. There is no connection limit beyond Cloudflare's per-worker concurrency limits. Latency to D1 from within a Worker is typically 1–5 ms for cached reads.
- **Hyperdrive pool model**: Hyperdrive maintains a pool of long-lived TCP connections to your Postgres server. Workers connect to Hyperdrive (local, within Cloudflare's network), which then reuses an existing Postgres connection from the pool. The pool size is configurable per Hyperdrive config (default: 10 per colo). Hyperdrive also caches read query results in memory, reducing Postgres load further.
- **Feature flag via env var**: `USE_POSTGRES` is set in `wrangler.toml` under `[vars]` or as a Cloudflare Worker secret. Changing it triggers a Worker redeploy, which is the recommended mechanism for gradual migration (blue/green or per-colo rollout).
- **SQL dialect differences**: D1 (SQLite) and Postgres have different functions, types, and placeholder syntax. Keep SQL strings in separate files (`queries/articles.d1.sql`, `queries/articles.pg.sql`) and load them via the factory, or use an ORM that targets both (Drizzle ORM supports both D1 and Postgres).
- **`ctx.waitUntil`**: Postgres connections must be closed after the response is sent to avoid connection leaks. `ctx.waitUntil(db.close())` lets the Worker runtime keep the isolate alive long enough to drain the connection pool without blocking the response.

## Anti-patterns

- **Opening a new Postgres connection per query** — Without Hyperdrive (or with a misconfigured pool), every Worker request opens a new TCP+TLS+auth handshake. This hammers Postgres with connection overhead and can exhaust `max_connections` quickly.
- **Not calling `db.close()` in finally block** — Forgetting to close Postgres connections causes the pool to grow unbounded across Worker isolate restarts, eventually hitting Postgres's `max_connections`.
- **Using D1 batch() semantics for Postgres** — D1 batch() sends multiple statements in one HTTP round-trip; Postgres has no equivalent. The PostgresClient above wraps batches in a `BEGIN`/`COMMIT` transaction, which has different semantics (atomic, rollback on error). Ensure your business logic expects this.
- **Hardcoding connection strings in source** — Never put Postgres credentials in `wrangler.toml` or source files. Use `wrangler secret put` and reference via `env.HYPERDRIVE.connectionString`.
- **Ignoring Hyperdrive caching for writes** — Hyperdrive caches SELECT results by default. After a write, cached reads may return stale data until the cache TTL expires. Disable caching for queries that must see the latest write, or set a short TTL.

## Gotchas

- Hyperdrive uses PgBouncer-style pooling in transaction mode. This means you cannot use server-side cursors, `LISTEN`/`NOTIFY`, or `SET` session variables across queries — the connection may be handed to a different worker between statements.
- The `postgres` npm package (`postgres.js`) is the recommended Postgres client for Workers. `pg` (node-postgres) requires Node.js compatibility mode (`nodejs_compat` flag in wrangler.toml) and has known issues with the Workers runtime.
- D1 `db.batch()` returns results as an array in the same order as the input statements. Postgres transaction results from `sql.begin()` must be accumulated manually in order.
- Hyperdrive adds a small latency overhead (~1–2 ms) compared to a direct Postgres connection from the same data center, but saves 100–400 ms compared to establishing a new connection from a different region.
- When `USE_POSTGRES` is flipped to `'true'` and D1 is the source of truth, you must first migrate data to Postgres. The feature flag alone does not migrate data.

## Verification

```bash
# Test D1 path
curl https://api.example project.internal/articles \
  -H 'Authorization: Bearer <token>'
# Should return articles from D1

# Enable Postgres path (update wrangler.toml [vars] USE_POSTGRES = "true", redeploy)
npx wrangler deploy

# Test Postgres path
curl https://api.example project.internal/articles \
  -H 'Authorization: Bearer <token>'
# Should return articles from Postgres via Hyperdrive

# Verify Hyperdrive is being used (check Cloudflare dashboard -> Hyperdrive -> Analytics)
# Metrics show connections reused vs. new connections opened

# Simulate pool exhaustion (set max: 1 in PostgresClient, send concurrent requests)
npx autocannon -c 50 -d 5 https://api.example project.internal/articles
# Expect 503 responses to be handled gracefully, not unhandled errors
```

## Related

- `documentation/docs/policies/database/d1-row-level-security-pattern.md` — RLS pattern applies equally to both D1 and Postgres paths
- `documentation/docs/policies/database/d1-schema-version-tracking.md` — migration runner must target the active database backend
- `documentation/docs/policies/database/d1-json-column-queries.md` — JSON functions differ between SQLite and Postgres (use `->>`/`@>` in Postgres)

## Sources

- https://developers.cloudflare.com/hyperdrive/
- https://developers.cloudflare.com/hyperdrive/configuration/pool-size/
- https://developers.cloudflare.com/d1/reference/data-location/
- https://github.com/porsager/postgres
