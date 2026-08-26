# Multi-Tenancy Isolation Patterns

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A cross-tenant data leak is discovered in production: a query
returns rows belonging to another tenant because the tenant
filter was omitted in a code path. Alternatively, the
platform cannot onboard a compliance-sensitive customer
because it cannot prove data never commingles.

## Context

Multi-tenancy is the pattern of serving multiple independent
customers (tenants) from shared infrastructure without data
leakage between them. On this stack, the primary options are
shared D1 (pool model with row-level security), schema-per-
tenant (D1 database-per-tenant), or Durable Objects scoped
to each tenant. Anonymous platforms have additional
constraints: tenant identity must be derivable without
user authentication, typically via an API key or subdomain.

## Isolation Models Compared

| Model               | Isolation | Cost/tenant | Notes             |
|---------------------|-----------|-------------|-------------------|
| Shared DB + RLS     | Logical   | Very low    | Simplest to run   |
| Schema-per-tenant   | Logical   | Low         | D1 lacks schemas  |
| DB-per-tenant       | Physical  | Higher      | Strong boundary   |
| DO-per-tenant       | Compute   | Per-request | Ordered, stateful |

D1 does not support PostgreSQL-style schemas. The practical
choice is either a `tenant_id` column on every table (pool)
or a separate D1 database per tenant.

## Row-Level Security in D1

D1 does not enforce RLS at the database engine level (SQLite
has no `CREATE POLICY`). Enforce RLS at the query layer by
injecting `tenant_id` on every statement.

```typescript
// Shared query helper — always binds tenant_id
export async function tenantQuery<T>(
  db: D1Database,
  tenantId: string,
  sql: string,
  bindings: unknown[] = [],
): Promise<T[]> {
  const stmt = db
    .prepare(sql)
    .bind(tenantId, ...bindings);
  const { results } = await stmt.all<T>();
  return results;
}

// Usage — tenant_id is always first binding
const posts = await tenantQuery<Post>(
  env.DB,
  ctx.tenantId,
  "SELECT * FROM posts WHERE tenant_id = ? AND id = ?",
  [postId],
);
```

Add a D1 constraint to make the column non-nullable and add
an index for query performance:

```sql
CREATE TABLE posts (
  id          TEXT    PRIMARY KEY,
  tenant_id   TEXT    NOT NULL,
  content     TEXT    NOT NULL,
  created_at  INTEGER NOT NULL
);
CREATE INDEX idx_posts_tenant ON posts (tenant_id);
```

## Tenant Context Propagation in Workers

The tenant context (tenant ID, plan, feature flags) must be
resolved early and carried through the entire request
lifecycle without re-querying on every function call.

```typescript
// Middleware: resolve tenant from API key header
async function resolveTenant(
  req: Request,
  env: Env,
): Promise<TenantContext> {
  const apiKey = <redacted-secret>"X-API-Key");
  if (!apiKey) throw new HttpError(401, "Missing API key");

  const cached = await env.KV.get<TenantContext>(
    `tenant:${apiKey}`,
    "json",
  );
  if (cached) return cached;

  const row = await env.DB.prepare(
    "SELECT id, plan FROM tenants WHERE api_key = ?",
  )
    .bind(apiKey)
    .first<{ id: string; plan: string }>();
  if (!row) throw new HttpError(403, "Invalid API key");

  const ctx: TenantContext = { tenantId: row.id,
    plan: row.plan };
  await env.KV.put(`tenant:${apiKey}`, JSON.stringify(ctx),
    { expirationTtl: 300 });
  return ctx;
}
```

Pass `TenantContext` as an explicit parameter through service
functions; never store it in a global or module-level
variable (Workers isolates are shared between requests).

## Durable Objects as Tenant-Scoped Compute

For features requiring ordered state per tenant (rate limit
counters, real-time presence, per-tenant queues), use a
Durable Object keyed on `tenantId`. Each DO instance is
physically isolated: its storage is never shared.

```typescript
// DO keyed per tenant — natural isolation boundary
const id = env.TENANT_DO.idFromName(ctx.tenantId);
const stub = env.TENANT_DO.get(id);
const remaining = await stub.fetch(
  new Request("https://do/rate-check"),
);
```

This pattern gives strong isolation guarantees suitable for
compliance conversations: tenant A's DO cannot access
tenant B's storage by construction.

## Anti-patterns

- Filtering by `tenant_id` only in the application layer
  without a NOT NULL constraint; a bug that omits the
  filter reads all tenants' rows.
- Caching query results without including `tenant_id` in
  the cache key; a cache hit for tenant A may serve data
  to tenant B.
- Using sequential integer tenant IDs that are easy to
  enumerate; prefer UUIDs or opaque tokens.
- Storing the active tenant in a closure or module-level
  variable in a Worker — the isolate is reused across
  requests, leaking the previous tenant's context.

## Gotchas

- D1 `batch()` executes multiple statements atomically;
  all statements in a batch must include the tenant filter
  or the atomicity benefit is undermined by a data leak.
- KV caching of tenant context must be invalidated when
  API keys are rotated or tenant plans change; use a short
  TTL (≤ 5 min) and an explicit cache purge on update.
- Durable Object IDs derived from `idFromName(tenantId)`
  are deterministic and cannot be revoked; deleting a
  tenant requires explicitly clearing the DO storage.

## Verification

- Write a test that creates two tenants, inserts rows for
  each, and asserts that querying as tenant A never returns
  tenant B's rows, even when `tenant_id` binding is removed.
- Add a SQLite trigger or D1 check constraint to reject
  inserts with a NULL `tenant_id`.
- Audit all query sites with `grep -r "FROM posts"` and
  confirm every site calls `tenantQuery` or equivalent.

## Related

- architecture/data-isolation-strategies.md
- architecture/multi-tenancy-architecture.md
- architecture/tenant-routing-patterns.md
- architecture/row-level-security-patterns.md
- architecture/rate-limiting-architecture.md

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/workers/runtime-apis/\
bindings/
- https://cheatsheetseries.owasp.org/cheatsheets/\
Multitenant_Security_Cheat_Sheet.html
