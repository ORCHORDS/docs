# D1 Read Replica Routing Pattern for Read-Heavy Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Worker serving a content-heavy application issues 90%+ read queries against D1 but
routes all traffic through the primary database binding. As read load grows, query
latency increases and primary write throughput degrades. D1 read replicas offer
geographically distributed read capacity, but the Worker must explicitly route reads
to replica bindings while directing writes to the primary.

---

## Context

Cloudflare D1 (as of 2024) supports read replicas through multiple D1 binding names
pointing to the same database's replica instances. The primary binding handles writes;
replica bindings serve eventually-consistent reads from regional PoPs closer to the
Worker instance.

Key properties of D1 read replicas:
- **Replica lag**: Replicas typically lag 100–500 ms behind the primary after a write.
- **Eventual consistency**: A read immediately after a write may return stale data from
  a replica. For user-visible writes (form submissions, purchases), read from primary
  or wait for replication.
- **Cost**: Replica reads are billed at the same rate as primary reads but reduce primary
  load, improving write throughput and overall latency for high-read workloads.
- **Failover**: If a replica is unavailable, the Worker must fall back to the primary.
  D1 bindings throw on unavailability, so wrap replica calls in try/catch.

---

## Solution

### 1. Wrangler binding configuration

```toml
# wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id = "<primary-db-id>"

[[d1_databases]]
binding = "DB_REPLICA"
database_name = "my-app-db-replica"
database_id = "<replica-db-id>"
```

### 2. D1 router — read/write separation

```typescript
interface Env {
  DB: D1Database;
  DB_REPLICA: D1Database;
}

type QueryMode = 'read' | 'write' | 'primary'; // primary = always use primary

class D1Router {
  private primary: D1Database;
  private replica: D1Database;
  private replicaErrors = 0;
  private readonly MAX_REPLICA_ERRORS = 3;
  private replicaDisabledUntil = 0;

  constructor(env: Env) {
    this.primary = env.DB;
    this.replica = env.DB_REPLICA;
  }

  private shouldUseReplica(): boolean {
    if (Date.now() < this.replicaDisabledUntil) return false;
    if (this.replicaErrors >= this.MAX_REPLICA_ERRORS) return false;
    return true;
  }

  async query<T = Record<string, unknown>>(
    sql: string,
    params: (string | number | boolean | null)[] = [],
    mode: QueryMode = 'read',
  ): Promise<D1Result<T>> {
    if (mode === 'write' || mode === 'primary' || !this.shouldUseReplica()) {
      return this.primary.prepare(sql).bind(...params).all<T>();
    }

    // Attempt replica read with primary fallback
    try {
      const result = await this.replica.prepare(sql).bind(...params).all<T>();
      this.replicaErrors = 0; // Reset on success
      return result;
    } catch (err) {
      this.replicaErrors++;
      console.warn(`Replica read failed (${this.replicaErrors}/${this.MAX_REPLICA_ERRORS}):`, err);

      // Circuit-break replica for 30 seconds after too many errors
      if (this.replicaErrors >= this.MAX_REPLICA_ERRORS) {
        this.replicaDisabledUntil = Date.now() + 30_000;
      }

      // Fallback to primary
      return this.primary.prepare(sql).bind(...params).all<T>();
    }
  }

  async queryFirst<T = Record<string, unknown>>(
    sql: string,
    params: (string | number | boolean | null)[] = [],
    mode: QueryMode = 'read',
  ): Promise<T | null> {
    const db = (mode === 'write' || mode === 'primary' || !this.shouldUseReplica())
      ? this.primary
      : this.replica;

    try {
      return await db.prepare(sql).bind(...params).first<T>();
    } catch (err) {
      if (db === this.replica) {
        console.warn('Replica queryFirst failed, falling back to primary:', err);
        this.replicaErrors++;
        return this.primary.prepare(sql).bind(...params).first<T>();
      }
      throw err;
    }
  }

  async exec(sql: string): Promise<D1Result> {
    // DDL and writes always go to primary
    return this.primary.exec(sql);
  }
}
```

### 3. Write-then-read consistency window

```typescript
// After a write, maintain a per-request "primary preferred" window
class ConsistencyAwareRouter extends D1Router {
  private wroteAt: number | null = null;
  private readonly CONSISTENCY_WINDOW_MS = 500;

  async write<T>(
    sql: string,
    params: (string | number | boolean | null)[] = [],
  ): Promise<D1Result<T>> {
    const result = await this.query<T>(sql, params, 'write');
    this.wroteAt = Date.now();
    return result;
  }

  protected override shouldUseReplica(): boolean {
    if (this.wroteAt !== null) {
      const elapsed = Date.now() - this.wroteAt;
      if (elapsed < this.CONSISTENCY_WINDOW_MS) {
        return false; // Stay on primary within consistency window
      }
    }
    return super['shouldUseReplica']();
  }
}

// Usage in a form submission handler
async function handleCreatePost(
  request: Request,
  router: ConsistencyAwareRouter,
): Promise<Response> {
  const body = await request.json() as { title: string; content: string; authorId: string };

  // Write to primary
  await router.write(
    'INSERT INTO posts (title, content, author_id) VALUES (?, ?, ?)',
    [body.title, body.content, body.authorId],
  );

  // Read-back within consistency window — routes to primary
  const post = await router.queryFirst<{ id: string; title: string }>(
    'SELECT id, title FROM posts WHERE author_id = ? ORDER BY created_at DESC LIMIT 1',
    [body.authorId],
  );

  return Response.json({ success: true, post });
}
```

### 4. Replica lag monitoring

```typescript
async function measureReplicaLag(env: Env): Promise<number | null> {
  // Write a heartbeat timestamp to the primary
  const heartbeatKey = '__lag_check__';
  const now = Date.now();

  try {
    await env.DB.prepare(
      'INSERT OR REPLACE INTO _heartbeat (id, ts) VALUES (1, ?)'
    ).bind(now).run();

    // Read from replica
    const row = await env.DB_REPLICA
      .prepare('SELECT ts FROM _heartbeat WHERE id = 1')
      .first<{ ts: number }>();

    if (!row) return null;
    return now - row.ts; // Lag in milliseconds
  } catch (err) {
    console.error('Lag check failed:', err);
    return null;
  }
}

// Expose via a health endpoint
async function handleHealth(request: Request, env: Env): Promise<Response> {
  const lagMs = await measureReplicaLag(env);
  return Response.json({
    status: 'ok',
    replicaLagMs: lagMs,
    replicaHealthy: lagMs !== null && lagMs < 2000,
  });
}
```

### 5. Batch read routing

```typescript
async function batchReadFromReplica<T>(
  replica: D1Database,
  queries: Array<{ sql: string; params: unknown[] }>,
): Promise<T[][]> {
  const statements = queries.map(({ sql, params }) =>
    replica.prepare(sql).bind(...params)
  );

  // D1 batch runs all statements in a single round-trip
  const results = await replica.batch<T>(statements);
  return results.map((r) => r.results);
}

// Prefetch multiple read queries in parallel using batch
async function prefetchDashboardData(
  env: Env,
  userId: string,
): Promise<{
  posts: unknown[];
  comments: unknown[];
  stats: unknown[];
}> {
  const [posts, comments, stats] = await batchReadFromReplica(env.DB_REPLICA, [
    {
      sql: 'SELECT id, title, created_at FROM posts WHERE author_id = ? ORDER BY created_at DESC LIMIT 10',
      params: [userId],
    },
    {
      sql: 'SELECT id, content, post_id FROM comments WHERE author_id = ? ORDER BY created_at DESC LIMIT 5',
      params: [userId],
    },
    {
      sql: 'SELECT COUNT(*) as total_posts, SUM(views) as total_views FROM posts WHERE author_id = ?',
      params: [userId],
    },
  ]);

  return { posts, comments, stats };
}
```

---

## Implementation Details

- **Circuit breaker**: The `replicaDisabledUntil` mechanism prevents repeated replica
  failures from cascading. After 30 s, the router re-attempts replica use.
- **Module-scope router**: The `D1Router` instance can be module-scoped (not
  request-scoped) to persist circuit-breaker state across requests on the same isolate.
  Note: `replicaErrors` is then shared across concurrent requests — acceptable for a
  counter, but ensure no mutable request-specific state leaks into the module scope.
- **D1 batch API**: `db.batch([...statements])` executes multiple statements in a single
  HTTP round-trip to D1, further reducing latency for read-heavy pages.
- **SQLite consistency**: D1 is SQLite-based. `INSERT OR REPLACE` for heartbeat rows
  avoids constraint violations on repeated writes.

---

## Anti-patterns

- **Writing to the replica binding**: D1 replicas are read-only. Write attempts will
  throw. Always guard writes with `mode === 'write'` routing to primary.
- **Ignoring replica lag for user-visible state**: After a purchase or profile update,
  reading from a lagged replica and showing stale data erodes user trust. Use the
  consistency window pattern for post-write reads.
- **No fallback to primary**: If you route reads exclusively to the replica with no
  fallback, replica downtime takes down the entire read path.
- **Module-scope `wroteAt` timestamp**: Storing the write timestamp at module scope
  causes cross-request contamination. Keep it request-scoped.

---

## Gotchas

- D1 replica binding names (`DB_REPLICA`) are independent of D1's internal replication.
  Ensure the `database_id` in `wrangler.toml` points to the correct replica instance ID,
  not the primary ID.
- D1 read replicas may not be available in all Cloudflare plans. Check your plan's D1
  limits before relying on this pattern.
- The `_heartbeat` table used for lag monitoring must exist. Create it in your D1
  migration: `CREATE TABLE IF NOT EXISTS _heartbeat (id INTEGER PRIMARY KEY, ts INTEGER);`
- Replica reads from a PoP far from the primary's region may have higher lag than
  expected. Monitor per-region lag with the health endpoint.

---

## Verification

```bash
# Query the health endpoint for replica lag
curl -s https://your-worker.example.com/_health | jq .replicaLagMs

# Run a write/read cycle and check timing
curl -X POST https://your-worker.example.com/posts \
  -H 'Content-Type: application/json' \
  -d '{"title":"Test","content":"Hello","authorId":"u1"}'

# Verify replica routes read queries via Server-Timing
curl -v https://your-worker.example.com/posts?userId=u1 2>&1 | grep -i 'server-timing'
```

Add `Server-Timing` to expose which DB was used:

```typescript
headers.set('Server-Timing', `db-${dbUsed};desc="d1-${dbUsed}-query";dur=${queryMs}`);
// Example: Server-Timing: db-replica;desc="d1-replica-query";dur=8
```

---

## Related

- `d1-query-batch-reduce-roundtrips.md`
- `workers-kv-bulk-prefetch-pattern.md`
- `workers-request-coalescing-durable-objects.md`
- `workers-cache-api-fine-grained-control.md`

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- D1 Read Replication — https://developers.cloudflare.com/d1/best-practices/read-replication/
- D1 batch API — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Workers D1 limits — https://developers.cloudflare.com/d1/platform/limits/
