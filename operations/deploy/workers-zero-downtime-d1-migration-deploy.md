# Zero-Downtime D1 Schema Migrations Coordinated with Worker Deployments

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to rename a D1 column or add a non-nullable column. If you run the migration and then deploy the new Worker, there is a window where the old Worker hits the new schema and crashes. If you deploy the Worker first, it references a column that does not yet exist and crashes. Neither order is safe with a single atomic cutover. You need a coordinated approach that keeps both old and new code working throughout the migration.

## Context

The expand-contract pattern (also called parallel change) solves this by splitting schema changes into phases that are each backward-compatible:

1. **Expand**: Add the new column/table alongside the old one. Both old and new Worker code can run against this schema.
2. **Migrate**: Backfill data from the old structure to the new structure.
3. **Contract**: Once all Workers use the new schema exclusively, remove the old column/table.

D1 does not support multi-statement transactions via the REST API batch endpoint for DDL. Each DDL statement must be a separate `wrangler d1 execute` call. Migration state is tracked in a KV key to coordinate the Worker deploy with the migration phases.

## Solution

### Expand-contract migration: example scenario

Goal: rename `products.name` → `products.title` with zero downtime.

**Phase 1 — Expand (add new column, keep old one)**

```sql
-- migrations/0010_expand_products_title.sql
ALTER TABLE products ADD COLUMN title TEXT;
-- Backfill immediately for small tables:
UPDATE products SET title = name WHERE title IS NULL;
```

**Phase 2 — Contract (remove old column after Worker cutover)**

```sql
-- migrations/0011_contract_products_name.sql
-- Run only AFTER all Worker versions use `title`, not `name`
ALTER TABLE products DROP COLUMN name;
```

**Note:** D1 (SQLite) does not support `DROP COLUMN` prior to SQLite 3.35. D1's SQLite version supports it. Verify with `SELECT sqlite_version();`.

### Migration state tracking in KV

```typescript
// src/lib/migration-state.ts
export type MigrationPhase = "idle" | "expanded" | "migrating" | "contracted";

export interface MigrationState {
  migration_id: string;
  phase: MigrationPhase;
  started_at: string;
  completed_at?: string;
  worker_version_required?: string; // minimum Worker version for the contract phase
}

const KEY_PREFIX = "migration:";

export async function getMigrationState(
  kv: KVNamespace,
  migrationId: string
): Promise<MigrationState | null> {
  const raw = await kv.get(`${KEY_PREFIX}${migrationId}`);
  return raw ? (JSON.parse(raw) as MigrationState) : null;
}

export async function setMigrationState(
  kv: KVNamespace,
  state: MigrationState
): Promise<void> {
  await kv.put(`${KEY_PREFIX}${state.migration_id}`, JSON.stringify(state), {
    metadata: { updated: new Date().toISOString() },
  });
}
```

### Dual-write Worker (runs during the expand phase)

```typescript
// src/services/product.service.ts
import { getMigrationState } from "../lib/migration-state";

export interface Env {
  DB: D1Database;
  MIGRATION_KV: KVNamespace;
}

export async function createProduct(
  env: Env,
  data: { name: string; price: number }
): Promise<void> {
  const state = await getMigrationState(env.MIGRATION_KV, "0010_rename_title");
  const inExpand = state?.phase === "expanded" || state?.phase === "migrating";

  if (inExpand) {
    // Dual-write: populate both columns during the transition
    await env.DB.prepare(
      "INSERT INTO products (name, title, price) VALUES (?, ?, ?)"
    )
      .bind(data.name, data.name, data.price)
      .run();
  } else if (state?.phase === "contracted") {
    // Write only the new column
    await env.DB.prepare(
      "INSERT INTO products (title, price) VALUES (?, ?)"
    )
      .bind(data.name, data.price)
      .run();
  } else {
    // Original schema, write only old column
    await env.DB.prepare(
      "INSERT INTO products (name, price) VALUES (?, ?)"
    )
      .bind(data.name, data.price)
      .run();
  }
}

export async function getProducts(env: Env): Promise<{ id: number; name: string; price: number }[]> {
  const state = await getMigrationState(env.MIGRATION_KV, "0010_rename_title");

  // Read from the authoritative column based on current phase
  const column = state?.phase === "contracted" ? "title" : "COALESCE(title, name)";
  const results = await env.DB
    .prepare(`SELECT id, ${column} AS name, price FROM products`)
    .all<{ id: number; name: string; price: number }>();

  return results.results;
}
```

### Coordinated deploy+migrate workflow

```typescript
// scripts/run-migration.ts
import { execSync } from "child_process";
import Cloudflare from "cloudflare";

const cf = new Cloudflare({ apiToken: process.env.CF_API_TOKEN });
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const KV_NAMESPACE_ID = process.env.MIGRATION_KV_ID!;
const D1_DATABASE_ID = process.env.D1_DATABASE_ID!;
const MIGRATION_ID = process.env.MIGRATION_ID!; // e.g. "0010_rename_title"
const EXPAND_SQL = process.env.EXPAND_SQL_FILE!;
const CONTRACT_SQL = process.env.CONTRACT_SQL_FILE!;

function wrangler(cmd: string): string {
  return execSync(`npx wrangler ${cmd}`, {
    encoding: "utf-8",
    env: {
      ...process.env,
      CLOUDFLARE_API_TOKEN: process.env.CF_API_TOKEN,
      CLOUDFLARE_ACCOUNT_ID: ACCOUNT_ID,
    },
  });
}

async function setKvState(phase: string): Promise<void> {
  const state = JSON.stringify({
    migration_id: MIGRATION_ID,
    phase,
    started_at: new Date().toISOString(),
  });
  await cf.kv.namespaces.values.update(KV_NAMESPACE_ID, `migration:${MIGRATION_ID}`, {
    account_id: ACCOUNT_ID,
    value: state,
    metadata: JSON.stringify({ phase }),
  });
  console.log(`Migration state set to: ${phase}`);
}

async function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

async function main(): Promise<void> {
  // Phase 1: Expand
  console.log("--- Phase 1: Expand schema ---");
  wrangler(`d1 execute ${D1_DATABASE_ID} --file ${EXPAND_SQL} --remote`);
  await setKvState("expanded");

  // Allow time for KV to propagate globally before deploying the dual-write Worker
  console.log("Waiting 60s for KV propagation...");
  await sleep(60_000);

  // Phase 2: Deploy dual-write Worker
  console.log("--- Phase 2: Deploy dual-write Worker ---");
  wrangler("deploy --env production");
  console.log("Waiting 30s for Worker deployment to propagate...");
  await sleep(30_000);

  // Phase 3: Backfill (for large tables, run in batches)
  console.log("--- Phase 3: Backfill data ---");
  await setKvState("migrating");
  wrangler(`d1 execute ${D1_DATABASE_ID} --command "UPDATE products SET title = name WHERE title IS NULL" --remote`);

  // Phase 4: Deploy contract-ready Worker (reads only `title`)
  console.log("--- Phase 4: Deploy contract Worker ---");
  wrangler("deploy --env production");
  console.log("Waiting 30s...");
  await sleep(30_000);

  // Phase 5: Contract (drop old column)
  console.log("--- Phase 5: Contract schema ---");
  wrangler(`d1 execute ${D1_DATABASE_ID} --file ${CONTRACT_SQL} --remote`);
  await setKvState("contracted");

  console.log("Migration complete.");
}

main().catch(err => { console.error(err); process.exit(1); });
```

### Rollback-safe migration design

```typescript
// scripts/migration-rollback.ts
// Rollback is only safe before the CONTRACT phase removes the old column.
// After DROP COLUMN, the only recovery is a database restore.

async function rollback(migrationId: string, kvNamespaceId: string): Promise<void> {
  const cf = new Cloudflare({ apiToken: process.env.CF_API_TOKEN });
  const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;

  // Check current phase
  const raw = await cf.kv.namespaces.values.get(kvNamespaceId, `migration:${migrationId}`, {
    account_id: ACCOUNT_ID,
  });

  const state = raw ? JSON.parse(await (raw as Response).text()) as { phase: string } : null;

  if (!state) {
    console.log("No migration state found. Nothing to roll back.");
    return;
  }

  if (state.phase === "contracted") {
    throw new Error(
      "Cannot roll back after the CONTRACT phase. The old column has been dropped. " +
      "Restore the D1 database from a Time Travel snapshot."
    );
  }

  // Safe to roll back: set state to idle so Workers revert to old-column reads
  await cf.kv.namespaces.values.update(kvNamespaceId, `migration:${migrationId}`, {
    account_id: ACCOUNT_ID,
    value: JSON.stringify({ migration_id: migrationId, phase: "idle" }),
    metadata: JSON.stringify({ phase: "idle", rolled_back_at: new Date().toISOString() }),
  });

  console.log(`Rolled back migration ${migrationId} to idle phase.`);
  console.log("Deploy the previous Worker version to stop dual-writing.");
}

rollback(
  process.env.MIGRATION_ID!,
  process.env.MIGRATION_KV_ID!
).catch(err => { console.error(err); process.exit(1); });
```

### D1 Time Travel safety net

Before running the contract phase (DROP COLUMN), create a D1 Time Travel bookmark:

```bash
# Bookmark the state before the destructive step
wrangler d1 time-travel info <database-name>
# Note the current timestamp; you can restore to it within 30 days
# (D1 Time Travel is automatic — no explicit snapshot command needed)
# To restore:
wrangler d1 time-travel restore <database-name> --timestamp 2026-08-24T10:00:00Z
```

## Implementation Details

- For large tables (>1M rows), the backfill `UPDATE` in Phase 3 should be chunked: `UPDATE products SET title = name WHERE title IS NULL LIMIT 10000` in a loop with a short pause between iterations to avoid hitting D1's 10-second query timeout.
- The KV migration state is the coordination mechanism between phases. Any Worker — old or new version — can read it and adjust behavior accordingly. This means a rollout of multiple Worker instances across Cloudflare's network converges correctly.
- D1 does not have a concept of "begin transaction / commit" across multiple HTTP API calls. Each `wrangler d1 execute` is its own auto-committed transaction. Plan migrations to be idempotent at the SQL level (`IF NOT EXISTS`, `WHERE title IS NULL`).
- D1 Time Travel retains 30 days of history. Schedule the contract phase no earlier than 24 hours after the expand phase to ensure a clean restore window exists.

## Anti-patterns

- **Rename column in a single step**: `ALTER TABLE RENAME COLUMN` is atomic but requires both old and new Worker code to be deployed simultaneously — impossible without a brief outage window.
- **Running DDL and deploying the Worker in the same CI step**: Even with a 0-second gap, Cloudflare's global network takes 5–30 seconds to propagate a new Worker version. DDL changes apply instantly to D1. The old Worker will read the new schema before the new Worker takes over.
- **Ignoring in-flight requests during phase transitions**: Requests that start on the old Worker version and take more than a few seconds (e.g., streaming responses) may straddle a phase boundary. Design the dual-write path to handle both schema states for the lifetime of a single request.
- **Dropping columns without Time Travel confirmation**: Always verify that D1 Time Travel is active on the database before executing destructive DDL. Check `wrangler d1 time-travel info <db>`.

## Gotchas

- SQLite's `ALTER TABLE DROP COLUMN` requires that the column is not referenced by any index, unique constraint, foreign key, or view. Drop dependent indexes before dropping the column.
- `wrangler d1 execute --file` with a file containing multiple statements separated by semicolons may fail on some D1 versions. Split each DDL into its own `--command` call or its own `.sql` file.
- KV `put` with metadata does not automatically expire. Clean up migration state keys after the contract phase completes to avoid accumulating stale state.
- D1's HTTP API has a maximum SQL statement size of 100KB. Large backfill queries with many `IN (...)` values may need to be split.

## Verification

```bash
# Confirm new column exists and old column is still present (during expand phase)
wrangler d1 execute <db-name> --command "PRAGMA table_info(products)" --remote

# Spot-check dual-write integrity
wrangler d1 execute <db-name> \
  --command "SELECT id, name, title FROM products WHERE title IS NULL OR name != title LIMIT 5" \
  --remote

# Confirm migration state in KV
wrangler kv key get migration:0010_rename_title --namespace-id $MIGRATION_KV_ID

# After contract phase: confirm old column is gone
wrangler d1 execute <db-name> --command "PRAGMA table_info(products)" --remote
```

## Related

- `workers-gradual-traffic-migration-routes.md`
- `workers-environment-promotion-pipeline.md`
- `workers-deployment-verification-smoke-tests.md`

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/d1/platform/time-travel/
- https://developers.cloudflare.com/d1/platform/client-api/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- https://martinfowler.com/bliki/ParallelChange.html
