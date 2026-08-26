# D1 Hash-Partitioned Tenant Sharding Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A multi-tenant SaaS on Cloudflare Workers backed by a single D1 database is approaching the 10 GB per-database storage limit, or query latency is increasing as the working set grows beyond D1's warm cache. Splitting every tenant into its own D1 database (per-tenant isolation) is operationally expensive at thousands of tenants. A middle path is hash partitioning: tenant IDs are consistently hashed to one of N shard databases; each shard holds roughly 1/N of all tenants.

## Context

D1 supports up to 50,000 databases per account (as of 2025). Wrangler bindings allow a Worker to hold references to multiple D1 databases simultaneously — `env.DB_0` through `env.DB_N`. A hash function maps each `tenant_id` to a shard index at the Worker layer; all queries for that tenant route to the designated shard. Schema is identical across all shards; migrations must run against every shard. No cross-shard joins are possible — queries that need data from multiple tenants require a scatter-gather fan-out in the Worker.

## Shard Routing Layer

A deterministic hash function converts a `tenant_id` string to a stable shard index. Use `crypto.subtle.digest` (available in Workers) to produce a consistent numeric hash.

```typescript
// src/sharding/router.ts

export const SHARD_COUNT = 8; // number of D1 databases

/**
 * Hash a tenant_id to a shard index [0, shardCount).
 * Uses the first 4 bytes of a SHA-256 digest for a uniform distribution.
 * The mapping is deterministic and immutable — changing SHARD_COUNT
 * requires a full data migration.
 */
export async function tenantShard(
  tenantId: string,
  shardCount = SHARD_COUNT
): Promise<number> {
  const encoded = new TextEncoder().encode(tenantId);
  const hashBuffer = await crypto.subtle.digest('SHA-256', encoded);
  const view = new DataView(hashBuffer);
  const uint32 = view.getUint32(0, false); // big-endian first 4 bytes
  return uint32 % shardCount;
}

// Cache the hash in memory for the lifetime of the Worker isolate
// to avoid repeated SubtleCrypto calls per request.
const shardCache = new Map<string, number>();

export async function getShardIndex(tenantId: string): Promise<number> {
  if (shardCache.has(tenantId)) return shardCache.get(tenantId)!;
  const idx = await tenantShard(tenantId);
  shardCache.set(tenantId, idx);
  return idx;
}
```

## Binding Configuration (wrangler.toml)

Declare all shard databases as separate D1 bindings:

```toml
# wrangler.toml

[[d1_databases]]
binding = "DB_0"
database_name = "myapp-shard-0"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[d1_databases]]
binding = "DB_1"
database_name = "myapp-shard-1"
database_id   = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"

[[d1_databases]]
binding = "DB_2"
database_name = "myapp-shard-2"
database_id   = "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz"

# … repeat for DB_3 through DB_7
```

```typescript
// src/types/env.ts
export interface Env {
  DB_0: D1Database;
  DB_1: D1Database;
  DB_2: D1Database;
  DB_3: D1Database;
  DB_4: D1Database;
  DB_5: D1Database;
  DB_6: D1Database;
  DB_7: D1Database;
}

/**
 * Resolve the correct D1 binding for a given tenant at request time.
 */
export async function shardFor(tenantId: string, env: Env): Promise<D1Database> {
  const idx = await getShardIndex(tenantId);
  const key = `DB_${idx}` as keyof Env;
  return env[key] as D1Database;
}
```

## Tenant-Scoped Query Pattern

All queries remain identical across shards; the only difference is which `D1Database` binding they execute against.

```typescript
// src/db/posts.ts
import type { Env } from '../types/env';
import { shardFor } from '../types/env';

export interface Post {
  id: string;
  tenant_id: string;
  title: string;
  body: string;
  created_at: number;
}

export async function getPost(
  tenantId: string,
  postId: string,
  env: Env
): Promise<Post | null> {
  const db = await shardFor(tenantId, env);

  return db
    .prepare(
      `SELECT id, tenant_id, title, body, created_at
       FROM posts
       WHERE tenant_id = ? AND id = ?`
    )
    .bind(tenantId, postId)
    .first<Post>();
}

export async function listPosts(
  tenantId: string,
  limit: number,
  cursor: string | null,
  env: Env
): Promise<Post[]> {
  const db = await shardFor(tenantId, env);

  const { results } = await db
    .prepare(
      `SELECT id, tenant_id, title, body, created_at
       FROM posts
       WHERE tenant_id = ?
         AND (? IS NULL OR created_at < ?)
       ORDER BY created_at DESC
       LIMIT ?`
    )
    .bind(tenantId, cursor, cursor ? Number(cursor) : null, limit)
    .all<Post>();

  return results;
}
```

## Cross-Shard Fan-Out for Global Queries

Admin dashboards or background jobs that need data across all tenants must scatter the query to every shard and gather results.

```typescript
// src/admin/global-stats.ts
import type { Env } from '../types/env';
import { SHARD_COUNT } from '../sharding/router';

export interface ShardStats {
  shard: number;
  tenant_count: number;
  post_count: number;
}

/**
 * Scatter a stats query across all shards in parallel.
 * Each D1 call is independent — use Promise.allSettled to
 * continue even if one shard is temporarily unavailable.
 */
export async function globalStats(env: Env): Promise<ShardStats[]> {
  const shardKeys = Array.from({ length: SHARD_COUNT }, (_, i) => `DB_${i}` as keyof Env);

  const results = await Promise.allSettled(
    shardKeys.map(async (key, idx) => {
      const db = env[key] as D1Database;
      const row = await db
        .prepare(
          `SELECT
             COUNT(DISTINCT tenant_id) AS tenant_count,
             COUNT(*)                  AS post_count
           FROM posts`
        )
        .first<{ tenant_count: number; post_count: number }>();

      return {
        shard: idx,
        tenant_count: row?.tenant_count ?? 0,
        post_count: row?.post_count ?? 0,
      } satisfies ShardStats;
    })
  );

  return results
    .filter((r): r is PromiseFulfilledResult<ShardStats> => r.status === 'fulfilled')
    .map((r) => r.value);
}
```

## Migration Runner Across All Shards

Schema changes must be applied to every shard. A Cloudflare Worker scheduled task (cron trigger) or a local script via Wrangler can iterate all shards.

```typescript
// scripts/run-migration.ts  (run with: npx ts-node scripts/run-migration.ts)
// Uses Cloudflare REST API to execute SQL against each database

const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const API_TOKEN  = process.env.CF_API_TOKEN!;

const SHARD_DATABASE_IDS = [
  'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', // DB_0
  'yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy', // DB_1
  // …
];

const MIGRATION_SQL = `
  ALTER TABLE posts ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;
  CREATE INDEX IF NOT EXISTS idx_posts_pinned ON posts(tenant_id, pinned, created_at DESC);
`;

async function applyMigration(databaseId: string, sql: string): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/d1/database/${databaseId}/query`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ sql }),
    }
  );
  if (!res.ok) throw new Error(`Migration failed on ${databaseId}: ${await res.text()}`);
  console.log(`Migration applied to ${databaseId}`);
}

for (const id of SHARD_DATABASE_IDS) {
  await applyMigration(id, MIGRATION_SQL);
}
```

## Anti-patterns

- Changing `SHARD_COUNT` after data is in production — every tenant's shard index changes, effectively losing all data routing. The shard count is immutable once data exists; plan capacity upfront.
- Running cross-shard queries (SELECT across multiple shards in one SQL statement) — D1 does not support attached cross-database queries at scale; implement scatter-gather in the Worker.
- Storing the shard assignment in a separate "directory" database without caching — every request queries the directory, adding latency and a single point of failure; the hash function is the directory.
- Using non-deterministic routing (random, round-robin load balancing) — queries for the same tenant must always hit the same shard; only deterministic hashing guarantees this.
- Neglecting to run schema migrations against all shards simultaneously — a partial migration causes SQL errors on tenants whose shard received the migration versus those that did not.

## Gotchas

- The SHA-256 approach above distributes uniformly only when `tenant_id` values are unique random strings (UUIDs). If tenant IDs have a common prefix pattern (e.g., sequential integers), verify distribution is acceptable with a sample before production rollout.
- Cloudflare Workers have a 50-binding limit per Worker script (across all types). With 8 D1 shards plus KV, R2, and other bindings, plan binding budget carefully; `DB_0`–`DB_7` consumes 8 binding slots.
- `Promise.allSettled` fan-out across all shards in a single Worker request may exceed the 128 MB Worker memory limit if each shard returns large result sets — stream or paginate fan-out results.
- Wrangler's `wrangler d1 migrations apply` targets one `--database` at a time; automate multi-shard migration via CI with a loop over all shard database IDs.
- Tenant reassignment between shards (for rebalancing) requires a copy-and-delete operation — copy all tenant rows to the new shard, then delete from the old shard, coordinating with an atomic directory update to prevent split-brain during the window.

## Verification

```typescript
// tests/shard-routing.test.ts
import { tenantShard } from '../src/sharding/router';

describe('tenantShard', () => {
  it('maps the same tenant_id to the same shard consistently', async () => {
    const id = 'ten_abc123';
    const idx1 = await tenantShard(id, 8);
    const idx2 = await tenantShard(id, 8);
    expect(idx1).toBe(idx2);
  });

  it('distributes 1000 tenant IDs within expected range', async () => {
    const counts = new Array(8).fill(0);
    for (let i = 0; i < 1000; i++) {
      const idx = await tenantShard(`tenant-${i}`, 8);
      counts[idx]++;
    }
    // Each shard should hold 10–15% of tenants (target 12.5%)
    for (const count of counts) {
      expect(count).toBeGreaterThan(80);
      expect(count).toBeLessThan(170);
    }
  });
});
```

```bash
# Verify shard assignment for a specific tenant via CLI
npx ts-node -e "
  const { tenantShard } = require('./src/sharding/router');
  tenantShard('ten_abc123').then(i => console.log('Shard:', i));
"
```

## Related

- `database/d1-multi-tenant-schema-isolation.md` — per-tenant schema-per-database isolation
- `database/d1-multi-tenant-schema-per-tenant-isolation.md` — row-level vs schema-level strategies
- `database/d1-row-level-security-tenant-id.md` — enforcing tenant_id scoping within a shared schema
- `database/database-sharding-strategies.md` — general sharding concepts
- `database/d1-connection-pooling-workers-hyperdrive-comparison.md` — Hyperdrive vs direct D1 access

## Sources

- https://developers.cloudflare.com/d1/platform/limits/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/
- https://developers.cloudflare.com/d1/worker-api/d1-database/
