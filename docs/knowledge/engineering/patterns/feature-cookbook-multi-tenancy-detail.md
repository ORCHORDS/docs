# feature-cookbook-multi-tenancy-detail

**Issue:** Multi-tenancy — isolation, billing, scale
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have 100 customers in one DB. Customer A reads
Customer B's data. Customer A is on the pro plan;
Customer B is on free. They see each other's data.
You have a breach.

## Root cause
**Without tenant isolation, all data is shared.** Use
multi-tenant.

**Source:** Various SaaS guides.

## The "tenant isolation" pattern

For tenant isolation:
- **DB per tenant:** Strongest, expensive
- **Schema per tenant:** Strong, complex
- **Tenant ID column:** Cheapest, requires care

For most apps, **tenant ID column** is enough.

```ts
async function getUsers(tenantId: string, env: Env): Promise<User[]> {
  return env.DB!.prepare(
    `SELECT * FROM users WHERE tenant_id = ?`
  ).bind(tenantId).all();
}
```

The tenant ID is in every query.

## The "tenant context" pattern

For the tenant context:
```ts
async function withTenant<T>(
  tenantId: string,
  fn: (env: Env) => Promise<T>,
  env: Env,
): Promise<T> {
  // Set the tenant context
  await env.DB!.prepare(`PRAGMA tenant_id = ?`).bind(tenantId).run();
  return fn(env);
}
```

The tenant is in the context.

## The "tenant middleware" pattern

For the middleware:
```ts
async function withTenantContext(
  request: Request,
  env: Env,
  handler: (tenantId: string) => Promise<Response>,
): Promise<Response> {
  const tenantId = await getTenantFromRequest(request, env);
  if (!tenantId) {
    return new Response('Unknown tenant', { status: 400 });
  }

  return handler(tenantId);
}

async function getTenantFromRequest(request: Request, env: Env): Promise<string | null> {
  // 1. From subdomain
  const host = new URL(request.url).hostname;
  const subdomain = host.split('.')[0];

  // 2. From header
  const tenantHeader = request.headers.get('x-tenant-id');

  // 3. From JWT
  const auth = request.headers.get('authorization');

  return tenantHeader ?? subdomain ?? null;
}
```

The tenant is extracted.

## The "tenant in every table" pattern

For the schema:
```sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  email TEXT NOT NULL,
  -- ...
  INDEX idx_tenant_email (tenant_id, email)
);

CREATE TABLE posts (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  author_id TEXT NOT NULL,
  -- ...
  INDEX idx_tenant_author (tenant_id, author_id)
);
```

The tenant ID is in every table.

## The "RLS" pattern (Postgres)

For Postgres, use RLS:
```sql
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON users
  USING (tenant_id = current_setting('app.tenant_id')::text);
```

The DB enforces isolation.

## The "tenant routing" pattern

For tenant routing:
- **Subdomain:** `acme.example.com`
- **Path:** `example.com/t/acme`
- **Header:** `X-Tenant-ID: acme`
- **JWT claim:** `tenant_id: acme`

```ts
function getTenantFromHost(host: string): string | null {
  const parts = host.split('.');
  if (parts.length < 3) return null;
  return parts[0];
}
```

The tenant is routed.

## The "tenant-aware auth" pattern

For auth, the tenant is part of the user:
```ts
interface User {
  id: string;
  tenantId: string;
  email: string;
  role: Role;
}
```

The tenant is in the user model.

## The "cross-tenant data" anti-pattern

For cross-tenant data:
```ts
// ❌ Bad: returns all tenants' data
const users = await env.DB!.prepare(`SELECT * FROM users`).all();

// ✅ Good: tenant-scoped
const users = await env.DB!.prepare(
  `SELECT * FROM users WHERE tenant_id = ?`
).bind(tenantId).all();
```

The query is tenant-scoped.

## The "tenant observability" pattern

For observability:
- **Per-tenant metrics:** Usage by tenant
- **Cross-tenant alerts:** Anomalies
- **Tenant health:** Errors by tenant

```ts
metrics.increment('api.requests', { tenantId, endpoint });
```

The metrics are per tenant.

## The "tenant billing" pattern

For billing, per usage:
```ts
async function recordUsage(tenantId: string, metric: string, value: number, env: Env): Promise<void> {
  await env.DB!.prepare(
    `INSERT INTO usage (id, tenant_id, metric, value, recorded_at) VALUES (?, ?, ?, ?, ?)`
  ).bind(crypto.randomUUID(), tenantId, metric, value, new Date().toISOString()).run();
}
```

The usage is recorded.

## The "tenant quota" pattern

For quota, per tenant:
```ts
async function isOverQuota(tenantId: string, env: Env): Promise<boolean> {
  const usage = await env.DB!.prepare(
    `SELECT SUM(value) as total FROM usage WHERE tenant_id = ? AND metric = 'api_calls' AND recorded_at > ?`
  ).bind(tenantId, startOfMonth).first<{ total: number }>();

  const tenant = await getTenant(tenantId, env);
  return usage.total >= tenant.quota;
}
```

The quota is enforced.

## The "tenant lifecycle" pattern

For lifecycle:
- **Trial:** 14 days, full access
- **Active:** Paying, full access
- **Past due:** Read-only
- **Suspended:** No access
- **Deleted:** Hard delete after 30 days

```ts
async function canAccess(tenant: Tenant, action: string): Promise<boolean> {
  if (tenant.status === 'suspended' || tenant.status === 'deleted') return false;
  if (tenant.status === 'past_due' && action.startsWith('write')) return false;
  return true;
}
```

The lifecycle is enforced.

## The "tenant soft delete" pattern

For soft delete:
```sql
ALTER TABLE tenants ADD COLUMN deleted_at TEXT;
```

The tenant is soft-deleted.

## The "tenant data export" pattern

For export, per tenant (GDPR):
```ts
async function exportTenantData(tenantId: string, env: Env): Promise<Blob> {
  const users = await env.DB!.prepare(`SELECT * FROM users WHERE tenant_id = ?`).bind(tenantId).all();
  const posts = await env.DB!.prepare(`SELECT * FROM posts WHERE tenant_id = ?`).bind(tenantId).all();

  return new Blob([JSON.stringify({ users, posts }, null, 2)], { type: 'application/json' });
}
```

The data is exported.

## The "tenant anti-pattern" anti-patterns

### 1. No tenant ID
- **Issue:** Cross-tenant reads
- **Fix:** Tenant ID everywhere

### 2. Tenant ID in app code
- **Issue:** Easy to forget
- **Fix:** Middleware / RLS

### 3. Shared resources
- **Issue:** Noisy neighbor
- **Fix:** Per-tenant quotas

### 4. No quota
- **Issue:** One tenant kills the DB
- **Fix:** Quota + rate limit

### 5. No backup
- **Issue:** Lost data
- **Fix:** Per-tenant backup

### 6. No soft delete
- **Issue:** Accidental delete
- **Fix:** Soft delete + retention

## Verification
- **Test:** Tenant isolation works
- **Test:** Quota is enforced
- **Test:** Soft delete works
- **Live:** Per-tenant metrics
- **Audit:** Annual review

## Gotchas
- **The "no tenant ID" anti-pattern.** Tenant ID
  everywhere.
- **The "tenant ID in code" anti-pattern.** Middleware.
- **The "no quota" anti-pattern.** Per-tenant quota.

## Related
- `multi-tenant-data-isolation.md`
- `feature-cookbook-data-modeling.md`
- `feature-cookbook-permission-modeling.md`
- `feature-cookbook-cost-optimization.md`
- `gdpr-article-17-erasure.md`
