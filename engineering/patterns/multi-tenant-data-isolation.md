# multi-tenant-data-isolation

**Issue:** Tenant data leaking across boundaries — queries missing tenant_id scope
**Date:** 2026-08-11
**Status:** documented

## Symptom

GET /api/controls returns controls from ALL tenants. A user from tenant A can read
tenant B's data by guessing resource IDs. This is a critical security failure — not a bug.

## The rule

**Every SQL query must scope to `ctx.tenant.id`.**

No exceptions except:
- Queries run by superadmin `role = 'superadmin'` with explicit cross-tenant intent
- Internal cron jobs that explicitly enumerate all tenants (SELECT DISTINCT tenant_id)

## Pattern — every read

```typescript
// Wrong — returns all rows:
const rows = await env.DB!.prepare(`SELECT * FROM controls`).all<Control>();

// Wrong — scopes by user ID but not tenant (user could be in multiple tenants):
const rows = await env.DB!.prepare(
  `SELECT * FROM controls WHERE created_by = ?`
).bind(ctx.user.id).all<Control>();

// Correct — always include tenant_id:
const rows = await env.DB!.prepare(
  `SELECT * FROM controls WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?`
).bind(ctx.tenant.id, 100).all<Control>();
```

## Pattern — write / update / delete

```typescript
// Wrong — updates any row with matching ID:
await env.DB!.prepare(`UPDATE controls SET status = ? WHERE id = ?`).bind(status, id).run();

// Correct — include tenant_id in WHERE clause:
await env.DB!.prepare(
  `UPDATE controls SET status = ?, updated_at = ? WHERE id = ? AND tenant_id = ?`
).bind(status, now, id, ctx.tenant.id).run();
// If 0 rows affected → the control doesn't exist OR belongs to another tenant.
// Return 404 in both cases — don't leak existence info.
```

## Pattern — check rows affected

```typescript
const result = await env.DB!.prepare(
  `DELETE FROM evidence WHERE id = ? AND tenant_id = ?`
).bind(id, ctx.tenant.id).run();

if (result.meta.changes === 0) {
  return jsonError(404, 'not_found', 'Evidence not found', ctx.request_id);
}
```

`meta.changes` is 0 if the WHERE clause matched nothing (row not found OR wrong tenant).
Return 404 either way — never 403 — to avoid confirming the resource exists in another tenant.

## Pattern — JOIN across tenant-scoped tables

```typescript
// Correct — both tables scoped to the same tenant:
const rows = await env.DB!.prepare(`
  SELECT e.id, e.title, c.name AS control_name
  FROM evidence e
  JOIN controls c ON c.id = e.control_id AND c.tenant_id = e.tenant_id
  WHERE e.tenant_id = ?
  ORDER BY e.created_at DESC
`).bind(ctx.tenant.id).all<EvidenceRow>();
// The JOIN's AND c.tenant_id = e.tenant_id prevents cross-tenant evidence
// being associated with same-name controls in the requesting tenant.
```

## Superadmin bypass

Only the auth layer should grant superadmin access. In handler code, check role before
bypassing tenant scope:

```typescript
if (ctx.user.role === 'superadmin' && targetTenantId) {
  // Explicit cross-tenant access granted
  tenantId = targetTenantId;
} else {
  tenantId = ctx.tenant.id;
}
```

Never accept `tenant_id` from the request body for regular users. The tenant comes
from the authenticated context, not the payload.

## Detection

Audit every handler with:

```bash
grep -rn 'prepare(`' functions/ | grep -v tenant_id
# Review: does the query have a tenant_id WHERE clause?
```

The TypeScript compiler won't catch missing tenant_id. It's a runtime data access bug.

## Schema rule

Every multi-tenant table MUST have:
1. `tenant_id TEXT NOT NULL` column
2. `FOREIGN KEY (tenant_id) REFERENCES tenants(id)`
3. Index on `(tenant_id, ...)` — almost always needed for query performance

```sql
CREATE TABLE controls (
  id         TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL REFERENCES tenants(id),
  name       TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'open',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX controls_tenant_idx ON controls(tenant_id, created_at DESC);
```

## Related

- `typescript-route-handler.md`
- `d1-typescript-patterns.md`
- `mccontext-gate-pattern.md`
- `d1-best-practices.md`
- `api-design-best-practices.md`
