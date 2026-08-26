# feature-multi-tenant-detail

**Issue:** Multi-tenant patterns — isolation, performance, cost
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a SaaS. 1000 tenants. Each tenant has 1000
users. Your DB is huge. One tenant's data is slow. Another
tenant's data is fast. The slow tenant is affecting the
fast ones.

## Root cause
**Multi-tenant has many gotchas.** Without good patterns,
one tenant's data affects another's.

**Source:** AWS — Multi-tenant SaaS:
https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-fundamentals/

## The 3 isolation strategies

### Shared DB, shared schema
- **What:** All tenants in one DB, one schema
- **Pros:** Cheap, easy to scale
- **Cons:** Bugs = cross-tenant data leak

```sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  email TEXT NOT NULL,
  UNIQUE (tenant_id, email)
);
```

### Shared DB, separate schema
- **What:** Each tenant has its own schema
- **Pros:** Some isolation
- **Cons:** More complex; schema migrations are N× work

### Separate DB per tenant
- **What:** Each tenant has its own DB
- **Pros:** Strongest isolation
- **Cons:** Expensive; hard to scale

For most SaaS, **shared DB, shared schema** is the right
answer.

## The "tenant_id in every query" rule

Every query MUST include `tenant_id`:
```ts
// ❌ Bad: no tenant_id
const user = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();

// ✅ Good: tenant_id included
const user = await env.DB!.prepare(`SELECT * FROM users WHERE id = ? AND tenant_id = ?`).bind(id, ctx.tenant.id).first();
```

## The "tenant from session" rule

The `tenant_id` MUST come from the session, not the user
input:
```ts
// ❌ Bad: tenant_id from user input
const tenantId = new URL(request.url).searchParams.get('tenant_id');
const users = await env.DB!.prepare(`SELECT * FROM users WHERE tenant_id = ?`).bind(tenantId).all();

// ✅ Good: tenant_id from session
const users = await env.DB!.prepare(`SELECT * FROM users WHERE tenant_id = ?`).bind(ctx.tenant.id).all();
```

## The "noisy neighbor" problem

One tenant's heavy load affects others.

### Solutions

1. **Rate limiting per tenant:**
```ts
const limit = planLimits[ctx.tenant.plan] ?? planLimits.free;
const allowed = await checkTenantRateLimit(ctx.tenant.id, limit, env);
if (!allowed) return new Response('Rate limited', { status: 429 });
```

2. **Tenant-aware query timeouts:**
```ts
const result = await withTimeout(
  env.DB!.prepare(`...`).bind(...).first(),
  5000,
);
```

3. **Sharding (separate DB per tenant):**
For very large tenants, move to a separate DB.

## The "tenant data" pattern

For per-tenant data, store the tenant context:
```ts
interface McContext {
  tenant: {
    id: string;
    name: string;
    plan: 'free' | 'pro' | 'enterprise';
    region: string;
  };
  user: {
    id: string;
    email: string;
    role: 'viewer' | 'admin' | 'owner';
  };
}
```

The context is built once per request; every query uses it.

## The "tenant routing" pattern

For multi-region tenants, route to the right region:
```ts
function getDbForTenant(tenant: Tenant, env: Env): D1Database {
  if (tenant.region === 'us') return env.DB_US;
  if (tenant.region === 'eu') return env.DB_EU;
  return env.DB;  // Default
}
```

Each tenant's data is in the right region.

## The "tenant settings" pattern

For per-tenant configuration, store in a settings table:
```sql
CREATE TABLE tenant_settings (
  tenant_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (tenant_id, key)
);
```

```ts
async function getTenantSetting(tenantId: string, key: string, env: Env): Promise<string | null> {
  const row = await env.DB!.prepare(
    `SELECT value FROM tenant_settings WHERE tenant_id = ? AND key = ?`
  ).bind(tenantId, key).first<{ value: string }>();
  return row?.value ?? null;
}
```

Settings are per-tenant; defaults are fallback.

## The "tenant onboarding" pattern

For new tenant signup, create the tenant + initial data:
```ts
async function onboardTenant(input: TenantInput, env: Env): Promise<Tenant> {
  const tenantId = crypto.randomUUID();

  // 1. Create the tenant
  await env.DB!.prepare(
    `INSERT INTO tenants (id, name, plan, region) VALUES (?, ?, ?, ?)`
  ).bind(tenantId, input.name, 'free', input.region).run();

  // 2. Create default settings
  await env.DB!.prepare(
    `INSERT INTO tenant_settings (tenant_id, key, value) VALUES (?, ?, ?)`
  ).bind(tenantId, 'theme', 'light').run();

  // 3. Create the owner user
  const userId = crypto.randomUUID();
  await env.DB!.prepare(
    `INSERT INTO users (id, tenant_id, email, role) VALUES (?, ?, ?, ?)`
  ).bind(userId, tenantId, input.email, 'owner').run();

  return { id: tenantId, ...input };
}
```

The tenant is created with defaults; the owner can customize.

## The "tenant data export" pattern

For GDPR / data portability, export a single tenant's data:
```ts
async function exportTenantData(tenantId: string, env: Env): Promise<Blob> {
  // 1. Gather all the tenant's data
  const users = await env.DB!.prepare(`SELECT * FROM users WHERE tenant_id = ?`).bind(tenantId).all();
  const posts = await env.DB!.prepare(`SELECT * FROM posts WHERE tenant_id = ?`).bind(tenantId).all();
  // ... etc

  // 2. Format as JSON
  const data = {
    tenantId,
    users: users.results,
    posts: posts.results,
  };

  return new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
}
```

The export is per-tenant.

## The "tenant deletion" pattern

For GDPR / right to be forgotten, delete a tenant:
```ts
async function deleteTenant(tenantId: string, env: Env): Promise<void> {
  // 1. Anonymize the data (don't hard delete; may need for legal)
  await env.DB!.prepare(
    `UPDATE users SET email = 'deleted-' || id || '@deleted.local', display_name = 'Deleted User' WHERE tenant_id = ?`
  ).bind(tenantId).run();

  // 2. Soft delete the posts
  await env.DB!.prepare(
    `UPDATE posts SET deleted_at = ? WHERE tenant_id = ?`
  ).bind(new Date().toISOString(), tenantId).run();

  // 3. Mark the tenant as deleted
  await env.DB!.prepare(
    `UPDATE tenants SET status = 'deleted', deleted_at = ? WHERE id = ?`
  ).bind(new Date().toISOString(), tenantId).run();

  // 4. Audit
  await writeAudit(env, {
    action: 'tenant.deleted',
    resourceType: 'tenant',
    resourceId: tenantId,
  });
}
```

The data is gone (or anonymized).

## The "tenant limits" pattern

For per-tenant limits:
```ts
const TENANT_LIMITS = {
  free: { users: 10, storage: 100_000_000, apiCalls: 1000 },
  pro: { users: 100, storage: 10_000_000_000, apiCalls: 100_000 },
  enterprise: { users: Infinity, storage: Infinity, apiCalls: Infinity },
};

async function checkTenantLimit(tenant: Tenant, limit: keyof typeof TENANT_LIMITS.free, env: Env): Promise<boolean> {
  const limitValue = TENANT_LIMITS[tenant.plan][limit];
  // ... check current usage against the limit
}
```

The limits are per-plan; enforcement is per-action.

## The "tenant observability" pattern

For per-tenant metrics:
```ts
metrics.increment('tenant.requests_total', { tenantId: ctx.tenant.id });
metrics.histogram('tenant.request_duration_ms', duration, { tenantId: ctx.tenant.id });
```

The metrics are per-tenant; you can find the noisy tenant.

## The "tenant support" pattern

For support, look up a tenant quickly:
```sql
-- Find a tenant by domain
SELECT * FROM tenants WHERE custom_domain = ?;

-- Find a tenant by user email
SELECT t.* FROM tenants t
JOIN users u ON u.tenant_id = t.id
WHERE u.email = ?;
```

The queries are indexed; lookup is fast.

## Verification
- **Test:** Cross-tenant access is blocked
- **Test:** Tenant limits are enforced
- **Live:** Per-tenant metrics are monitored
- **Audit:** Quarterly review of tenant data

## Gotchas
- **The "tenant_id from user input" anti-pattern.** Always
  from the session.
- **The "shared connection pool" anti-pattern.** One
  tenant's slow query can starve others. Use a pool with
  per-tenant limits.
- **The "no tenant filter in JOIN" anti-pattern.** A JOIN
  without tenant_id can leak data.
- **The "tenant in URL" anti-pattern.** The tenant_id
  should never be in the URL (user-controlled).
- **The "tenant plan check missing" anti-pattern.** Every
  action that depends on the plan must check it.

## Related
- `multi-tenant-data-isolation.md`
- `feature-gating-implementation.md`
- `api-rate-limiting-detail.md`
- `feature-data-export.md`
- `audit-log-as-product.md`
- AWS: https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-fundamentals/
