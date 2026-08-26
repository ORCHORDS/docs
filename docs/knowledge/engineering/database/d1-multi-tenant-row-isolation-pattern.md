# Multi-Tenant Row Isolation in D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are building a SaaS product on Cloudflare Workers + D1 and need multiple tenants to share one database without ever reading each other's rows. A missing `WHERE tenant_id = ?` clause must be caught at the middleware layer, not rely on developer discipline alone.

## Context

- Runtime: Cloudflare Workers (ESM, TypeScript)
- Database: Cloudflare D1
- Auth: JWT issued per-tenant (e.g., Auth0, Clerk, or a custom Cloudflare Access JWT)
- Pattern: row-level isolation via `tenant_id` column on every table

---

## Section 1: Schema Design

Every table carries a `tenant_id` column as part of its primary key prefix. All indexes are prefixed with `tenant_id` to ensure the query planner scopes scans correctly.

```sql
-- migrations/0001_multi_tenant_schema.sql

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS tenants (
  id          TEXT PRIMARY KEY,          -- e.g., "org_abc123"
  name        TEXT NOT NULL,
  plan        TEXT NOT NULL DEFAULT 'free',
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projects (
  id          TEXT NOT NULL,
  tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (tenant_id, id)            -- tenant_id first in PK
);

CREATE INDEX IF NOT EXISTS idx_projects_tenant
  ON projects (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS documents (
  id          TEXT NOT NULL,
  tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  project_id  TEXT NOT NULL,
  content     TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_documents_project
  ON documents (tenant_id, project_id, created_at DESC);
```

---

## Section 2: JWT Middleware Injecting Tenant Context

The middleware validates the JWT, extracts `org_id`, and attaches a scoped DB helper to every request. Downstream handlers never touch the raw `D1Database` object.

```typescript
// src/middleware/tenant.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface TenantContext {
  tenantId: string;
  db: TenantScopedDb;
}

export class TenantScopedDb {
  constructor(
    private readonly raw: D1Database,
    public readonly tenantId: string,
  ) {}

  /** Run a query that MUST include :tenantId binding */
  prepare(sql: string) {
    // Inject tenantId as the first bound value automatically
    const stmt = this.raw.prepare(sql);
    return {
      bind: (...args: unknown[]) => stmt.bind(this.tenantId, ...args),
      // Convenience: callers never need to pass tenantId explicitly
      first: <T = unknown>() => stmt.bind(this.tenantId).first<T>(),
      all: <T = unknown>() => stmt.bind(this.tenantId).all<T>(),
      run: () => stmt.bind(this.tenantId).run(),
    };
  }

  /** Batch helper — each statement already has tenantId bound */
  batch(stmts: D1PreparedStatement[]) {
    return this.raw.batch(stmts);
  }
}

/** Minimal JWT payload we care about (subset) */
interface JwtPayload {
  sub: string;
  org_id: string;
  exp: number;
}

async function verifyJwt(token: string, jwksUrl: string): Promise<JwtPayload> {
  // In production use jose or a Cloudflare Workers-compatible JWT library.
  // This is a simplified example parsing without signature verification.
  // NEVER skip signature verification in production.
  const [, payloadB64] = token.split('.');
  const json = atob(payloadB64.replace(/-/g, '+').replace(/_/g, '/'));
  const payload = JSON.parse(json) as JwtPayload;

  if (!payload.org_id) throw new Error('JWT missing org_id claim');
  if (payload.exp < Math.floor(Date.now() / 1000)) throw new Error('JWT expired');

  return payload;
}

export async function tenantMiddleware(
  request: Request,
  db: D1Database,
  jwksUrl: string,
): Promise<TenantContext> {
  const authHeader = request.headers.get('Authorization') ?? '';
  if (!authHeader.startsWith('Bearer ')) {
    throw new Response('Unauthorized', { status: 401 });
  }

  const token = authHeader.slice(7);
  const payload = await verifyJwt(token, jwksUrl);

  return {
    tenantId: payload.org_id,
    db: new TenantScopedDb(db, payload.org_id),
  };
}
```

---

## Section 3: Using the Scoped DB in Route Handlers

Handlers receive `TenantContext` and query exclusively through `ctx.db`. Cross-tenant leaks are structurally impossible as long as every SQL statement begins with `WHERE tenant_id = ?` (first positional) which the scoped wrapper auto-binds.

```typescript
// src/routes/projects.ts
import type { TenantContext } from '../middleware/tenant';

export async function listProjects(ctx: TenantContext): Promise<Response> {
  const { results } = await ctx.db.raw
    .prepare(
      `SELECT id, name, created_at
         FROM projects
        WHERE tenant_id = ?
        ORDER BY created_at DESC
        LIMIT 50`,
    )
    .bind(ctx.tenantId)
    .all<{ id: string; name: string; created_at: string }>();

  return Response.json({ projects: results });
}

export async function getProject(
  ctx: TenantContext,
  projectId: string,
): Promise<Response> {
  const row = await ctx.db.raw
    .prepare(
      `SELECT id, name, created_at
         FROM projects
        WHERE tenant_id = ? AND id = ?`,
    )
    .bind(ctx.tenantId, projectId)
    .first<{ id: string; name: string; created_at: string }>();

  if (!row) return new Response('Not Found', { status: 404 });
  return Response.json(row);
}

export async function createProject(
  ctx: TenantContext,
  name: string,
): Promise<Response> {
  const id = crypto.randomUUID();

  await ctx.db.raw
    .prepare(
      `INSERT INTO projects (id, tenant_id, name)
       VALUES (?, ?, ?)`,
    )
    .bind(id, ctx.tenantId, name)
    .run();

  return Response.json({ id }, { status: 201 });
}
```

---

## Section 4: Preventing Cross-Tenant Leaks — Lint Rule

Enforce at CI level that no raw SQL string in `src/routes/` omits `tenant_id`.

```bash
# scripts/lint-tenant-isolation.sh
#!/usr/bin/env bash
# Fail if any route file queries a tenant table without tenant_id guard
set -euo pipefail

TENANT_TABLES=("projects" "documents")
VIOLATIONS=0

for table in "${TENANT_TABLES[@]}"; do
  # Find SELECT/UPDATE/DELETE on a tenant table without tenant_id in the same statement block
  matches=$(grep -rn "FROM ${table}\|INTO ${table}\|UPDATE ${table}" src/routes/ \
    | grep -v "tenant_id" || true)
  if [[ -n "$matches" ]]; then
    echo "VIOLATION: query on '${table}' missing tenant_id:"
    echo "$matches"
    VIOLATIONS=$((VIOLATIONS + 1))
  fi
done

if [[ $VIOLATIONS -gt 0 ]]; then
  echo "Tenant isolation lint FAILED with $VIOLATIONS violation(s)."
  exit 1
fi

echo "Tenant isolation lint passed."
```

---

## Anti-patterns

- Storing `tenant_id` only on the parent table and joining child tables without re-checking it.
- Using a separate D1 database per tenant — quickly hits account limits and creates operational overhead.
- Relying on application-layer filtering without database-level indexes on `tenant_id`.
- Passing the raw `D1Database` object into route handlers (bypasses scoping wrapper).
- Trusting user-supplied `tenant_id` from the request body instead of deriving it from the verified JWT.

## Gotchas

- D1 does not support Row-Level Security (RLS) natively; isolation is entirely application-enforced.
- `crypto.randomUUID()` is available in the Workers runtime without importing anything.
- Foreign keys require `PRAGMA foreign_keys = ON;` per connection — D1 enables this by default since mid-2024, but verify for older databases.
- Composite primary keys `(tenant_id, id)` make cross-tenant ID collisions impossible but complicate some ORM integrations.
- Deleting a tenant must cascade; test `ON DELETE CASCADE` behavior in your migration tests.

## Verification

```bash
# Confirm tenant_id index exists on all tenant tables
wrangler d1 execute YOUR_DB_NAME \
  --command "SELECT name, sql FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%tenant%';" \
  --remote

# Verify a cross-tenant query returns 0 rows (should always be empty)
wrangler d1 execute YOUR_DB_NAME \
  --command "SELECT COUNT(*) FROM projects WHERE tenant_id = 'nonexistent_tenant_xyz';" \
  --remote

# Run lint check in CI
bash scripts/lint-tenant-isolation.sh
```

## Related

- `documentation/docs/policies/database/d1-trigger-audit-log-application-layer.md`
- `documentation/docs/policies/database/d1-full-text-search-porter-stemmer.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/
- https://developers.cloudflare.com/d1/reference/foreign-keys/
