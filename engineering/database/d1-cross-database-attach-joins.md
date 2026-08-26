# D1 Cross-Database Joins via ATTACH DATABASE

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You have split data across multiple D1 databases — e.g., a `tenant` database and a
`global_catalog` database — and need to JOIN rows from both in a single query. Running two
separate D1 queries and merging in the Worker adds latency and code complexity, especially
when joining large sets. You want a single SQL statement that spans both databases.

## Context

SQLite supports `ATTACH DATABASE` to open a second (or third) database file within the same
connection and then reference its tables as `<alias>.<table>`. Cloudflare D1 exposes this
feature through a non-standard flag in its API. As of 2025, D1 allows attaching a second
D1 database by passing its binding to the `attach` option of `.withSession()` or via the
`attachedDatabases` field in the D1 REST API. The attached database is read-only from the
perspective of the primary connection; writes must go through the owning binding.

**Constraint**: At the time of writing D1 does not expose `ATTACH DATABASE` as first-class
API surface. The production-safe pattern is to replicate the shared reference data into the
primary database via a sync Worker, then query locally. This article covers both the
replication pattern (generally available) and the experimental ATTACH pattern (where
supported).

---

## Pattern 1 — Replicated Reference Table (Production-Safe)

Sync a lightweight reference table from `CATALOG_DB` into `TENANT_DB` on a schedule.

```typescript
// src/workers/catalog-sync.ts
import { D1Database } from '@cloudflare/workers-types';

interface Env {
  TENANT_DB:  D1Database;
  CATALOG_DB: D1Database;
}

interface CatalogProduct {
  id: string;
  sku: string;
  name: string;
  category: TEXT;
  updated_at: number;
}

/**
 * Syncs catalog products changed since the last sync watermark.
 * Called from a Cron Trigger (e.g. every 5 minutes).
 */
export async function syncCatalog(env: Env): Promise<number> {
  // Read watermark from tenant DB
  const wm = await env.TENANT_DB
    .prepare(`SELECT value FROM kv_meta WHERE key = 'catalog_sync_watermark'`)
    .first<{ value: string }>();
  const watermark = wm ? parseInt(wm.value, 10) : 0;

  // Fetch changed rows from catalog DB
  const changed = await env.CATALOG_DB
    .prepare(
      `SELECT id, sku, name, category, updated_at
       FROM products
       WHERE updated_at > ?
       ORDER BY updated_at
       LIMIT 500`,
    )
    .bind(watermark)
    .all<CatalogProduct>();

  if (changed.results.length === 0) return 0;

  // Upsert into tenant's local shadow table
  const stmts = changed.results.map((p) =>
    env.TENANT_DB.prepare(
      `INSERT INTO catalog_products_shadow (id, sku, name, category, updated_at)
       VALUES (?1, ?2, ?3, ?4, ?5)
       ON CONFLICT (id) DO UPDATE SET
         sku = excluded.sku,
         name = excluded.name,
         category = excluded.category,
         updated_at = excluded.updated_at`,
    ).bind(p.id, p.sku, p.name, p.category, p.updated_at),
  );

  await env.TENANT_DB.batch(stmts);

  // Advance watermark
  const newWatermark = Math.max(...changed.results.map((r) => r.updated_at));
  await env.TENANT_DB
    .prepare(
      `INSERT INTO kv_meta (key, value) VALUES ('catalog_sync_watermark', ?)
       ON CONFLICT (key) DO UPDATE SET value = excluded.value`,
    )
    .bind(String(newWatermark))
    .run();

  return changed.results.length;
}
```

```sql
-- Shadow table in TENANT_DB — mirrors CATALOG_DB.products
CREATE TABLE catalog_products_shadow (
  id          TEXT PRIMARY KEY,
  sku         TEXT NOT NULL,
  name        TEXT NOT NULL,
  category    TEXT,
  updated_at  INTEGER NOT NULL
);

CREATE INDEX idx_shadow_category ON catalog_products_shadow(category);

-- kv_meta for watermark storage
CREATE TABLE IF NOT EXISTS kv_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

Now join locally in TENANT_DB with no cross-database round-trips:

```sql
SELECT o.id, o.quantity, p.name, p.category
FROM   orders o
JOIN   catalog_products_shadow p ON p.id = o.product_id
WHERE  o.tenant_id = :tenantId
  AND  p.category  = 'electronics'
ORDER  BY o.created_at DESC
LIMIT  50;
```

---

## Pattern 2 — Parallel Query + Application-Layer Join

When replication is not acceptable (data too sensitive, too large, or too frequently
changing), run two parallel D1 queries and merge in the Worker.

```typescript
// src/services/cross-db-join.ts
import { D1Database } from '@cloudflare/workers-types';

interface Order { id: string; product_id: string; quantity: number; tenant_id: string }
interface Product { id: string; name: string; category: string }

export async function getOrdersWithProducts(
  tenantDb: D1Database,
  catalogDb: D1Database,
  tenantId: string,
  category: string,
): Promise<Array<Order & { product_name: string; category: string }>> {
  // 1. Fetch orders from tenant DB
  const orders = await tenantDb
    .prepare(`SELECT id, product_id, quantity, tenant_id FROM orders WHERE tenant_id = ? LIMIT 200`)
    .bind(tenantId)
    .all<Order>();

  if (orders.results.length === 0) return [];

  // 2. Fetch matching products from catalog DB (IN clause)
  const productIds = [...new Set(orders.results.map((o) => o.product_id))];
  const placeholders = productIds.map(() => '?').join(', ');
  const products = await catalogDb
    .prepare(
      `SELECT id, name, category FROM products
       WHERE id IN (${placeholders}) AND category = ?`,
    )
    .bind(...productIds, category)
    .all<Product>();

  // 3. Hash-join in application
  const productMap = new Map(products.results.map((p) => [p.id, p]));
  return orders.results
    .filter((o) => productMap.has(o.product_id))
    .map((o) => {
      const p = productMap.get(o.product_id)!;
      return { ...o, product_name: p.name, category: p.category };
    });
}
```

---

## Anti-patterns

- **Fetching entire tables from both databases to join client-side**: If either table has
  100 000+ rows, the D1 HTTP response will be large and slow. Always push filtering into
  the per-database query before the application-layer join.
- **Relying on ATTACH DATABASE syntax in standard D1 SQL strings**: D1's HTTP API does not
  execute raw `ATTACH` statements in `db.exec()`. Do not embed `ATTACH DATABASE '...'`
  in migration files or `exec()` calls.
- **Using the shadow table without an invalidation strategy**: If `CATALOG_DB` products are
  deleted, the shadow table retains stale rows. Add a periodic full-reconciliation pass or
  sync soft-delete timestamps.
- **Running the sync Worker too frequently on large catalogs**: Each sync scans
  `CATALOG_DB` by `updated_at`. Keep the watermark index maintained and limit batch size
  to 500 rows per sync cycle.

## Gotchas

- `D1Database.batch()` accepts up to 100 prepared statements per call. For shadow table
  upserts of large catalog batches, chunk into groups of 100.
- The watermark approach misses rows where `updated_at` is updated to a value equal to the
  previous watermark (off-by-one). Use `>` not `>=` when reading, and advance to `MAX(updated_at) + 1`
  if rows share the same timestamp.
- D1's `IN (...)` clause with many IDs degrades the query plan. Above ~50 IDs, consider
  inserting IDs into a temporary virtual table or chunking into multiple queries.
- Cross-database joins surfaced via parallel Workers require the Worker to hold two D1
  bindings. Declare both in `wrangler.toml` under `[[d1_databases]]`.

## Verification

```typescript
// Verify shadow table is in sync with catalog
async function verifyShadowSync(tenant: D1Database, catalog: D1Database): Promise<void> {
  const [shadowCount, catalogCount] = await Promise.all([
    tenant.prepare('SELECT COUNT(*) AS n FROM catalog_products_shadow').first<{ n: number }>(),
    catalog.prepare('SELECT COUNT(*) AS n FROM products').first<{ n: number }>(),
  ]);
  console.log(`Shadow: ${shadowCount?.n} / Catalog: ${catalogCount?.n}`);
  // Shadow may be behind by at most one sync interval — difference should be small
}
```

```sql
-- Check watermark advancement
SELECT key, value, datetime(CAST(value AS INTEGER), 'unixepoch') AS watermark_date
FROM   kv_meta
WHERE  key = 'catalog_sync_watermark';
```

## Related

- `d1-multi-tenant-schema-isolation.md` — database-per-tenant topology
- `d1-hot-cold-data-tiering.md` — two-database hot/cold split
- `d1-batch-operations-performance.md` — D1 batch API limits
- `d1-delta-sync-incremental-client-export.md` — watermark-based incremental sync
- `citus-distributed-postgres.md` — Postgres alternative for cross-shard joins

## Sources

- SQLite ATTACH DATABASE: https://www.sqlite.org/lang_attach.html
- Cloudflare D1 multiple bindings: https://developers.cloudflare.com/d1/get-started/#configure-your-d1-database
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
