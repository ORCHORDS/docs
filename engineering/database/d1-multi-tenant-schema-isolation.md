# D1 Multi-Tenant Schema Isolation Patterns

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You are building a SaaS application on Cloudflare Workers + D1 and need to serve
multiple tenants from the same database. Tenants must not see each other's data.
You want to avoid the complexity and cost of provisioning one D1 database per
tenant while still maintaining strong isolation guarantees.

## Context

D1 is SQLite under the hood. It does not support PostgreSQL-style schemas
(`CREATE SCHEMA tenant_a`) or row-level security (RLS) policies enforced by the
engine. All isolation must be enforced at the application layer.

There are three common patterns, each with different trade-offs:

| Pattern | Isolation level | Complexity | D1 cost |
|---------|----------------|------------|---------|
| Shared table, tenant_id column | Row-level (app-enforced) | Low | Low |
| Table-per-tenant prefix | Table-level | Medium | Low |
| Database-per-tenant | Database-level | High | Per-database billing |

Most production SaaS products on D1 use the **shared table + tenant_id** approach
with strict query discipline, combined with middleware that injects and verifies the
tenant context on every request.

## Pattern 1 — Shared Tables with tenant_id

Every table carries a `tenant_id` column. All queries include a WHERE clause that
filters by the resolved tenant ID. The Worker resolves the tenant from the JWT or
subdomain before touching the database.

```sql
-- Schema definition
CREATE TABLE tenants (
  id        TEXT PRIMARY KEY,          -- e.g. UUID v7
  slug      TEXT UNIQUE NOT NULL,
  plan      TEXT NOT NULL DEFAULT 'free',
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE projects (
  id         TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Composite index: always filter by tenant first
CREATE INDEX idx_projects_tenant ON projects(tenant_id, created_at DESC);

CREATE TABLE documents (
  id         TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title      TEXT NOT NULL,
  body       TEXT,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_documents_tenant_project ON documents(tenant_id, project_id, created_at DESC);
```

```typescript
// src/middleware/tenant.ts
import { Context, Next } from 'hono';
import { D1Database } from '@cloudflare/workers-types';

export interface TenantContext {
  tenantId: string;
  slug: string;
  plan: string;
}

/**
 * Resolves tenant from the host header (subdomain strategy) or JWT claim.
 * Attaches resolved tenant to Hono context variables.
 */
export async function tenantMiddleware(c: Context, next: Next) {
  const host = c.req.header('host') ?? '';
  const subdomain = host.split('.')[0];

  const db: D1Database = c.env.DB;

  const tenant = await db
    .prepare('SELECT id, slug, plan FROM tenants WHERE slug = ? LIMIT 1')
    .bind(subdomain)
    .first<TenantContext>();

  if (!tenant) {
    return c.json({ error: 'Unknown tenant' }, 404);
  }

  c.set('tenant', tenant);
  await next();
}
```

```typescript
// src/services/project-service.ts
import { D1Database } from '@cloudflare/workers-types';
import { TenantContext } from '../middleware/tenant';

export class ProjectService {
  constructor(
    private db: D1Database,
    private tenant: TenantContext,
  ) {}

  /**
   * Always binds tenant_id as the FIRST parameter so the composite index fires.
   * Never accept tenantId from the caller — always use the middleware-resolved value.
   */
  async list(limit = 20, afterCursor?: string) {
    const cursorClause = afterCursor
      ? 'AND created_at < (SELECT created_at FROM projects WHERE id = ? AND tenant_id = ?)'
      : '';
    const params = afterCursor
      ? [this.tenant.tenantId, afterCursor, this.tenant.tenantId, limit]
      : [this.tenant.tenantId, limit];

    const sql = `
      SELECT id, name, created_at
      FROM projects
      WHERE tenant_id = ?
      ${cursorClause}
      ORDER BY created_at DESC
      LIMIT ?
    `;
    const rows = await this.db.prepare(sql).bind(...params).all();
    return rows.results;
  }

  async create(name: string) {
    const id = crypto.randomUUID();
    await this.db
      .prepare('INSERT INTO projects (id, tenant_id, name, created_at) VALUES (?, ?, ?, ?)')
      .bind(id, this.tenant.tenantId, name, Math.floor(Date.now() / 1000))
      .run();
    return { id, name };
  }

  /** Reads a project only if it belongs to the current tenant — prevents IDOR. */
  async get(projectId: string) {
    return this.db
      .prepare('SELECT * FROM projects WHERE id = ? AND tenant_id = ?')
      .bind(projectId, this.tenant.tenantId)
      .first();
  }
}
```

## Pattern 2 — Table-per-Tenant with Prefix

Each tenant gets its own set of tables: `t_<tenantId>_projects`, `t_<tenantId>_documents`.
Schema is identical across tenants. Useful when tenants need independent migrations
or when cross-tenant analytics are never required.

```typescript
// src/services/tenant-provisioner.ts
export async function provisionTenant(db: D1Database, tenantId: string) {
  const prefix = `t_${tenantId.replace(/-/g, '_')}`;

  // Execute DDL for every table in the tenant's schema
  await db.batch([
    db.prepare(`
      CREATE TABLE IF NOT EXISTS ${prefix}_projects (
        id         TEXT PRIMARY KEY,
        name       TEXT NOT NULL,
        created_at INTEGER NOT NULL DEFAULT (unixepoch())
      )
    `),
    db.prepare(`
      CREATE TABLE IF NOT EXISTS ${prefix}_documents (
        id         TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        title      TEXT NOT NULL,
        body       TEXT,
        created_at INTEGER NOT NULL DEFAULT (unixepoch()),
        FOREIGN KEY (project_id) REFERENCES ${prefix}_projects(id) ON DELETE CASCADE
      )
    `),
    db.prepare(`
      CREATE INDEX IF NOT EXISTS ${prefix}_docs_project
        ON ${prefix}_documents(project_id, created_at DESC)
    `),
  ]);
}

/** Build a query against the correct tenant-prefixed table. */
function tenantTable(tenantId: string, table: string): string {
  return `t_${tenantId.replace(/-/g, '_')}_${table}`;
}

export async function listProjects(db: D1Database, tenantId: string) {
  const tbl = tenantTable(tenantId, 'projects');
  // Table names cannot be parameterized — validate tenantId format strictly
  if (!/^[0-9a-f-]{36}$/.test(tenantId)) throw new Error('Invalid tenant ID');
  return db.prepare(`SELECT * FROM ${tbl} ORDER BY created_at DESC`).all();
}
```

**Trade-off**: SQLite has a limit of roughly 2 billion tables by name but D1 has
practical limits. With 1 000 tenants × 10 tables = 10 000 tables in `sqlite_master`,
query planning overhead increases. Prefer this pattern only for low tenant counts
(< 500) or when schema divergence per tenant is expected.

## Pattern 3 — Database-per-Tenant

Each tenant maps to its own D1 database binding. The Worker looks up the database
ID from a control-plane store and constructs the binding dynamically.

```typescript
// wrangler.toml — static bindings for known tenants (dev/staging)
// [[d1_databases]]
// binding = "DB_TENANT_A"
// database_name = "tenant-a"
// database_id = "..."

// In production: use the D1 REST API to provision databases dynamically,
// then store the database_id in a control-plane KV or DO.

interface Env {
  CONTROL_DB: D1Database;   // stores tenant → database_id mapping
  // Dynamic bindings resolved at runtime via env object

}

export async function getTenantDB(env: Env, tenantId: string): Promise<D1Database> {
  const record = await (env.CONTROL_DB as D1Database)
    .prepare('SELECT db_binding_name FROM tenant_databases WHERE tenant_id = ?')
    .bind(tenantId)
    .first<{ db_binding_name: string }>();

  if (!record) throw new Error(`No database registered for tenant ${tenantId}`);

  const db = (env as Record<string, unknown>)[record.db_binding_name] as D1Database;
  if (!db) throw new Error(`Binding ${record.db_binding_name} not found in Worker env`);

  return db;
}
```

This is the strongest isolation but requires separate billing, migrations, and
monitoring per tenant. Reserve it for enterprise customers with compliance
requirements (SOC 2, HIPAA).

## Enforcing Tenant Boundaries in Batch Operations

D1 `.batch()` executes multiple statements atomically. When batching cross-tenant
writes (e.g. an admin action), ensure every statement includes a `tenant_id` binding:

```typescript
async function batchDeleteTenant(db: D1Database, tenantId: string) {
  // Delete in dependency order (children before parents)
  await db.batch([
    db.prepare('DELETE FROM documents WHERE tenant_id = ?').bind(tenantId),
    db.prepare('DELETE FROM projects  WHERE tenant_id = ?').bind(tenantId),
    db.prepare('DELETE FROM tenants   WHERE id = ?').bind(tenantId),
  ]);
}
```

## Anti-patterns

- **Trusting user-supplied tenant IDs**: Always derive the tenant ID from an
  authenticated JWT or the host header, never from a query parameter or request body.
- **Skipping tenant_id in joins**: A join between `projects` and `documents` that
  only filters `tenant_id` on one side still leaks data if the other table is not
  filtered. Filter both sides or rely on FOREIGN KEY CASCADE with a root-table tenant
  guard.
- **Using LIKE for table-prefix queries**: Dynamic table names must be validated
  against a strict allowlist regex before string interpolation. Never derive the
  table name from user input without validation.
- **Global sequences / auto-increment PKs**: Row IDs leak tenant row counts to
  other tenants if an IDOR vulnerability exists. Use UUIDs or opaque tokens as
  primary keys.
- **Sharing a single D1 binding for table-per-tenant at high scale**: With thousands
  of tenant-prefixed tables, `sqlite_master` scans become slow. Monitor query latency
  and migrate high-volume tenants to dedicated databases.

## Gotchas

- D1 does not enforce RLS at the engine level. A missing `WHERE tenant_id = ?`
  clause silently returns all tenants' data.
- PRAGMA `foreign_keys = ON` must be set per connection in D1; it is off by default
  in SQLite. D1 enables it by default in recent versions, but verify with
  `PRAGMA foreign_keys;` → should return `1`.
- `ON DELETE CASCADE` on `tenant_id` foreign keys requires a `REFERENCES tenants(id)`
  definition and foreign key enforcement enabled. Test cascade behavior in a staging
  D1 instance before deploying.
- When using Wrangler's `--remote` flag for migrations, all DDL runs in D1's
  production environment. Use `--env staging` bindings during development.

## Verification

```sql
-- Confirm no cross-tenant data leakage: all project rows must match their tenant
SELECT p.id, p.tenant_id, d.tenant_id AS doc_tenant
FROM projects p
JOIN documents d ON d.project_id = p.id
WHERE p.tenant_id != d.tenant_id;
-- Expected: 0 rows

-- Check composite index is being used for tenant queries
EXPLAIN QUERY PLAN
SELECT * FROM projects WHERE tenant_id = 'abc' ORDER BY created_at DESC LIMIT 10;
-- Expected: SEARCH projects USING INDEX idx_projects_tenant

-- Count tenants and their row distributions
SELECT tenant_id, COUNT(*) AS row_count
FROM projects
GROUP BY tenant_id
ORDER BY row_count DESC
LIMIT 20;
```

```typescript
// Integration test: tenant isolation smoke test
async function smokeTestTenantIsolation(db: D1Database) {
  const tenantA = 'tenant-a-id';
  const tenantB = 'tenant-b-id';

  // Insert a project for tenant A
  await db.prepare('INSERT INTO projects (id, tenant_id, name, created_at) VALUES (?, ?, ?, ?)')
    .bind('proj-1', tenantA, 'Alpha Project', Date.now() / 1000)
    .run();

  // Query as tenant B — must return 0 rows
  const result = await db.prepare('SELECT * FROM projects WHERE tenant_id = ?')
    .bind(tenantB)
    .all();

  console.assert(result.results.length === 0, 'Isolation failure: tenant B saw tenant A data');

  // Query as tenant A — must return 1 row
  const own = await db.prepare('SELECT * FROM projects WHERE tenant_id = ?')
    .bind(tenantA)
    .all();

  console.assert(own.results.length === 1, 'Tenant A cannot see its own data');
}
```

## Related

- `multi-tenant-postgres-strategies.md` — PostgreSQL RLS-based multi-tenancy
- `d1-foreign-keys-referential-integrity.md` — enabling and testing FK enforcement in D1
- `row-level-security.md` — engine-enforced RLS concepts (Postgres)
- `d1-schema-versioning-wrangler-migrations.md` — running migrations per-tenant DB
- `database-roles-least-privilege.md` — least-privilege access patterns

## Sources

- Cloudflare D1 documentation: developers.cloudflare.com/d1
- SQLite FAQ on multi-tenancy: sqlite.org/whentouse.html
- OWASP IDOR prevention guidelines: owasp.org/www-project-web-security-testing-guide
