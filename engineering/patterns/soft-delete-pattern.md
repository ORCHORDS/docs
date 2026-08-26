# soft-delete-pattern

**Issue:** Hard-deleting rows breaks audit logs, foreign keys, and SCIM/IdP state
**Date:** 2026-08-11
**Status:** documented

## Symptom

DELETE endpoint removes a row from the database. Later:
- Audit log entries reference a non-existent `resource_id`
- JOIN queries return NULL for previously-audited resources
- SCIM IdP reconciliation re-provisions the "deleted" user
- Foreign key violations on tables referencing the deleted row

## The rule

**Never hard-delete rows in tenant-facing tables.** Use soft delete: set a `deleted_at` timestamp
and `status = 'deleted'` (or `status = 'disabled'` for users).

The only exceptions are:
- Internal temp/staging tables with no audit trail
- GDPR erasure requests (separate, explicit, audited erasure flow)

## Schema

```sql
CREATE TABLE controls (
  id          TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL REFERENCES tenants(id),
  name        TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'open',   -- 'open', 'closed', 'deleted'
  deleted_at  INTEGER,                         -- NULL = not deleted
  deleted_by  TEXT REFERENCES users(id),
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);

-- Index includes soft-delete filter for fast active-only queries:
CREATE INDEX controls_active_idx ON controls(tenant_id, status, created_at DESC)
  WHERE deleted_at IS NULL;
```

## Delete handler

```typescript
export async function deleteControl(request: Request, env: Env, id: string): Promise<Response> {
  const ctx = await authenticate(request, env);
  if (!ctx) return jsonError(401, 'unauthorized', undefined, undefined);
  if (!roleAtLeast(ctx.user.role, 'admin')) return jsonError(403, 'forbidden', undefined, ctx.request_id);

  const now = Math.floor(Date.now() / 1000);
  const result = await env.DB!.prepare(
    `UPDATE controls SET status = 'deleted', deleted_at = ?, deleted_by = ?, updated_at = ?
     WHERE id = ? AND tenant_id = ? AND deleted_at IS NULL`
  ).bind(now, ctx.user.id, now, id, ctx.tenant.id).run();

  if (result.meta.changes === 0) {
    return jsonError(404, 'not_found', 'Control not found', ctx.request_id);
  }

  await writeAudit(env, ctx, {
    action: 'control.deleted',
    resource_kind: 'control',
    resource_id: id,
  });

  return new Response(null, { status: 204 });
}
```

## List handler — exclude soft-deleted

```typescript
const rows = await env.DB!.prepare(
  `SELECT * FROM controls WHERE tenant_id = ? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT ?`
).bind(ctx.tenant.id, 100).all<Control>();
```

## Get-by-ID handler — respect soft delete

```typescript
const row = await env.DB!.prepare(
  `SELECT * FROM controls WHERE id = ? AND tenant_id = ? AND deleted_at IS NULL`
).bind(id, ctx.tenant.id).first<Control>();
if (!row) return jsonError(404, 'not_found', 'Control not found', ctx.request_id);
```

Return 404 for soft-deleted rows — same as not found. Never return 410 Gone for individual resources
(leaks existence info to unauthorized callers).

## SCIM delete

SCIM spec requires responding 204 on delete. Since IdPs re-provision on reconciliation, soft delete
is mandatory:

```typescript
// SCIM DELETE → soft delete (status = 'disabled')
await env.DB!.prepare(
  `UPDATE users SET status = 'disabled', deleted_at = ?, updated_at = ?
   WHERE id = ? AND tenant_id = ?`
).bind(now, now, id, ctx.tenant.id).run();
return new Response(null, { status: 204 });
```

When the IdP later runs reconciliation and finds the user missing from its active list, it re-sends
a DELETE. The response is still 204 (idempotent). The `AND deleted_at IS NULL` guard can be omitted
for SCIM to make it idempotent:

```typescript
await env.DB!.prepare(
  `UPDATE users SET status = 'disabled', deleted_at = COALESCE(deleted_at, ?), updated_at = ?
   WHERE id = ? AND tenant_id = ?`
).bind(now, now, id, ctx.tenant.id).run();
```

## GDPR erasure

Erasure is a separate, explicit flow — not delete:

1. Set `status = 'erased'`, `deleted_at = now`
2. Null out PII columns: `email = NULL, display_name = NULL, ...`
3. Preserve the row for audit trail integrity (keep `id`, `tenant_id`, `created_at`, audit references)
4. Log an `user.gdpr_erased` audit event with the requesting user and timestamp

## Gotchas

- **Missing `AND deleted_at IS NULL` in WHERE**: The most common soft-delete bug. Deleted rows appear in list responses.
- **Partial index**: `WHERE deleted_at IS NULL` in the index definition makes it smaller and faster — only active rows are indexed.
- **`meta.changes === 0` after delete**: Distinguish "not found" from "already deleted" only if required by the API contract. For most cases, return 404 either way.
- **Cascade soft-delete**: When a parent is soft-deleted (e.g. a tenant), child rows are NOT automatically soft-deleted. Either cascade explicitly in the handler or filter children with `EXISTS (SELECT 1 FROM tenants WHERE id = child.tenant_id AND deleted_at IS NULL)`.

## Related

- `multi-tenant-data-isolation.md`
- `d1-typescript-patterns.md`
- `scim-bearer-token-auth.md`
- `audit-without-user-context.md`
- `typescript-route-handler.md`
