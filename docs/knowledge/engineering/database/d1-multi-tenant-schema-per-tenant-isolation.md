# Schema-per-Tenant Isolation in Cloudflare D1

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

SaaS applications running on Cloudflare Workers need strong data isolation between tenants without the operational overhead of managing a traditional database cluster. D1's multi-database support allows each tenant to own a dedicated SQLite database, providing hard schema and storage boundaries at the platform level. The challenge is routing requests to the correct database and keeping migrations in sync across potentially thousands of tenant databases.

## Context

D1 supports binding multiple databases to a single Worker at deploy time via `wrangler.toml`, but dynamic binding resolution—selecting a database at runtime based on tenant identity—requires the REST API or the `cloudflare:sockets` approach combined with a registry pattern. Each D1 database has its own storage quota, query log, and access control scope, making per-tenant databases a natural fit for compliance-sensitive workloads (GDPR, HIPAA) where cross-tenant data leakage must be provably impossible at the infrastructure layer rather than enforced purely by application logic.

## Dynamic Database Binding Resolution

At Worker boot time all bindings are fixed, so per-tenant routing requires looking up the tenant's `databaseId` from a control-plane D1 (the "registry") and issuing queries via the REST API for that specific database. Use a short-lived in-memory cache (per isolate) to avoid paying the registry lookup cost on every request.

```typescript
// src/tenant-db.ts
import { Env } from './types';

interface TenantRecord {
  tenantId: string;
  databaseId: string;
  region: string;
  plan: string;
}

// Per-isolate LRU cache — survives for the lifetime of the Worker isolate.
const resolverCache = new Map<string, { databaseId: string; expiresAt: number }>();
const CACHE_TTL_MS = 60_000; // 1 minute

export async function resolveTenantDb(
  tenantId: string,
  registry: D1Database,
): Promise<string> {
  const cached = resolverCache.get(tenantId);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.databaseId;
  }

  const row = await registry
    .prepare('SELECT database_id FROM tenants WHERE tenant_id = ? AND active = 1')
    .bind(tenantId)
    .first<{ database_id: string }>();

  if (!row) throw new Error(`Unknown tenant: ${tenantId}`);

  resolverCache.set(tenantId, {
    databaseId: row.database_id,
    expiresAt: Date.now() + CACHE_TTL_MS,
  });

  return row.database_id;
}

export async function queryTenantDb<T = unknown>(
  databaseId: string,
  sql: string,
  params: (string | number | null)[],
  env: Env,
): Promise<T[]> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/d1/database/${databaseId}/query`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ sql, params }),
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`D1 REST query failed [${response.status}]: ${err}`);
  }

  const data = (await response.json()) as { result: [{ results: T[] }] };
  return data.result[0].results;
}
```

## Provisioning Tenant Databases

New tenant signup triggers database creation via the Cloudflare REST API, followed by schema bootstrapping using the same `queryTenantDb` helper.

```typescript
// src/provision.ts
import { queryTenantDb } from './tenant-db';
import { Env } from './types';

const BASELINE_SCHEMA = `
CREATE TABLE IF NOT EXISTS users (
  id       TEXT PRIMARY KEY,
  email    TEXT NOT NULL UNIQUE,
  name     TEXT NOT NULL,
  role     TEXT NOT NULL DEFAULT 'member',
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS schema_migrations (
  version    INTEGER PRIMARY KEY,
  applied_at INTEGER NOT NULL DEFAULT (unixepoch()),
  checksum   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
`;

export async function provisionTenant(
  tenantId: string,
  name: string,
  registry: D1Database,
  env: Env,
): Promise<string> {
  // 1. Create the D1 database via REST API.
  const createUrl = `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/d1/database`;
  const createRes = await fetch(createUrl, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ name: `tenant-${tenantId}` }),
  });

  if (!createRes.ok) throw new Error(`Failed to create D1 database for tenant ${tenantId}`);
  const { result } = (await createRes.json()) as { result: { uuid: string } };
  const databaseId = result.uuid;

  // 2. Apply baseline schema — split on semicolons, filter empty statements.
  const statements = BASELINE_SCHEMA.split(';')
    .map(s => s.trim())
    .filter(Boolean);

  for (const sql of statements) {
    await queryTenantDb(databaseId, sql, [], env);
  }

  // 3. Register in control-plane registry.
  await registry
    .prepare(
      'INSERT INTO tenants (tenant_id, name, database_id, active) VALUES (?, ?, ?, 1)',
    )
    .bind(tenantId, name, databaseId)
    .run();

  return databaseId;
}
```

## Migration Orchestration Across Tenant Databases

Running a migration across all tenants requires listing active databases from the registry and applying changes sequentially (or in bounded parallel batches) to avoid overwhelming the D1 API rate limits.

```typescript
// scripts/migrate-all-tenants.ts  (run via `wrangler dev --local` or a Cron Trigger)
import { queryTenantDb } from '../src/tenant-db';
import { Env } from '../src/types';

interface Migration {
  version: number;
  sql: string;
  checksum: string;
}

const PENDING_MIGRATIONS: Migration[] = [
  {
    version: 2,
    sql: `ALTER TABLE users ADD COLUMN avatar_url TEXT;`,
    checksum: 'sha256:abc123',
  },
  {
    version: 3,
    sql: `CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);`,
    checksum: 'sha256:def456',
  },
];

async function migrateTenant(
  databaseId: string,
  migrations: Migration[],
  env: Env,
): Promise<void> {
  const applied = await queryTenantDb<{ version: number }>(
    databaseId,
    'SELECT version FROM schema_migrations ORDER BY version',
    [],
    env,
  );
  const appliedVersions = new Set(applied.map(r => r.version));

  for (const migration of migrations) {
    if (appliedVersions.has(migration.version)) continue;

    await queryTenantDb(databaseId, migration.sql, [], env);
    await queryTenantDb(
      databaseId,
      'INSERT INTO schema_migrations (version, checksum) VALUES (?, ?)',
      [migration.version, migration.checksum],
      env,
    );
    console.log(`[${databaseId}] Applied migration v${migration.version}`);
  }
}

export async function migrateAllTenants(registry: D1Database, env: Env): Promise<void> {
  const tenants = await registry
    .prepare('SELECT database_id FROM tenants WHERE active = 1')
    .all<{ database_id: string }>();

  // Process in batches of 10 to stay within API rate limits.
  const BATCH_SIZE = 10;
  for (let i = 0; i < tenants.results.length; i += BATCH_SIZE) {
    const batch = tenants.results.slice(i, i + BATCH_SIZE);
    await Promise.all(
      batch.map(t => migrateTenant(t.database_id, PENDING_MIGRATIONS, env)),
    );
  }
}
```

## Anti-patterns

- Binding all tenant databases statically in `wrangler.toml` — this works up to ~10 tenants but becomes unmanageable at scale and requires a redeployment every time a tenant is onboarded.
- Using a single D1 database with a `tenant_id` discriminator column instead of per-tenant databases when strict data isolation or per-tenant GDPR deletion is required — row-level isolation relies on application correctness, not platform guarantees.
- Skipping `schema_migrations` version tracking per tenant database — without it, reruns of migration scripts apply DDL changes multiple times, causing errors on `ALTER TABLE` statements that are not idempotent.
- Deleting tenant databases immediately on churn without an archival grace period — D1 has no soft-delete at the platform level and there is no recycle bin.

## Gotchas

- D1 REST API rate limits apply per account, not per database. Migrating thousands of tenant databases in parallel will hit the `429` ceiling quickly; implement exponential back-off and honour `Retry-After` headers.
- `ALTER TABLE … ADD COLUMN` in SQLite cannot add a column with a `NOT NULL` constraint unless a `DEFAULT` value is also specified. Tenant schemas drifted by bad migrations accumulate silently — always validate the target schema after migration using `PRAGMA table_info(table_name)`.
- Cloudflare imposes a maximum number of D1 databases per account (currently 50,000 on paid plans). Plan for database archival or consolidation if you expect to exceed this limit.

## Verification

```bash
# List all tenant databases via Wrangler CLI.
wrangler d1 list

# Check applied migrations on a specific tenant database.
wrangler d1 execute tenant-<TENANT_ID> \
  --command "SELECT version, applied_at, checksum FROM schema_migrations ORDER BY version;"

# Confirm schema shape after a migration.
wrangler d1 execute tenant-<TENANT_ID> \
  --command "PRAGMA table_info(users);"

# Count active tenants in the registry.
wrangler d1 execute registry-db \
  --command "SELECT COUNT(*) AS total, SUM(active) AS active FROM tenants;"
```

## Related

- `database/d1-row-level-security-tenant-id.md`
- `database/d1-migrations-wrangler-ci-cd.md`
- `database/d1-schema-versioning-wrangler-migrations.md`
- `database/multi-tenant-postgres-strategies.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/d1/platform/client-api/
- https://developers.cloudflare.com/d1/platform/limits/
- https://developers.cloudflare.com/workers/configuration/bindings/
