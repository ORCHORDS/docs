# role-based-access-control

**Issue:** Consistent role checks in multi-tenant API — roleAtLeast(), role hierarchy
**Date:** 2026-08-11
**Status:** documented

## Role hierarchy

Roles are ordered from least to most privileged:

```
viewer < member < admin < owner < superadmin
```

`roleAtLeast(actual, required)` returns true if `actual` is at least as privileged as `required`.

## Implementation

```typescript
const ROLE_RANK: Record<string, number> = {
  viewer: 1,
  member: 2,
  admin: 3,
  owner: 4,
  superadmin: 5,
};

export function roleAtLeast(actual: string, required: string): boolean {
  return (ROLE_RANK[actual] ?? 0) >= (ROLE_RANK[required] ?? 999);
}
```

## Usage in handlers

```typescript
// Viewer+ can read:
export async function listControls(request: Request, env: Env): Promise<Response> {
  const ctx = await authenticate(request, env);
  if (!ctx) return jsonError(401, 'unauthorized', undefined, undefined);
  // No role check — all authenticated users can read
  ...
}

// Admin+ can create:
export async function createControl(request: Request, env: Env): Promise<Response> {
  const ctx = await authenticate(request, env);
  if (!ctx) return jsonError(401, 'unauthorized', undefined, undefined);
  if (!roleAtLeast(ctx.user.role, 'admin')) {
    return jsonError(403, 'forbidden', 'Admin role required', ctx.request_id);
  }
  ...
}

// Owner only:
export async function deleteTenant(request: Request, env: Env): Promise<Response> {
  const ctx = await authenticate(request, env);
  if (!ctx) return jsonError(401, 'unauthorized', undefined, undefined);
  if (!roleAtLeast(ctx.user.role, 'owner')) {
    return jsonError(403, 'forbidden', 'Owner role required', ctx.request_id);
  }
  ...
}

// Superadmin only — cross-tenant operations:
export async function impersonateTenant(request: Request, env: Env): Promise<Response> {
  const ctx = await authenticate(request, env);
  if (!ctx) return jsonError(401, 'unauthorized', undefined, undefined);
  if (ctx.user.role !== 'superadmin') {
    return jsonError(403, 'forbidden', undefined, ctx.request_id);
  }
  ...
}
```

## Which role for which operation

| Operation | Minimum role |
|-----------|-------------|
| Read any resource | `viewer` (authenticated) |
| Create / update a resource | `member` or `admin` (depends on resource) |
| Manage users, invite | `admin` |
| Change billing, delete tenant | `owner` |
| Cross-tenant access, impersonate | `superadmin` |

Specific thresholds depend on the product. Document your choices in `access-control-matrix.md`.

## Returning the right error

- `401` — not authenticated (no session, expired token)
- `403` — authenticated but wrong role

Never return `404` for a role check failure on an endpoint that exists — that leaks endpoint existence.
Exception: If the user doesn't have access to see whether a RESOURCE exists (e.g. another tenant's
control), return `404` (see `multi-tenant-data-isolation.md`).

## Self-access exception

Users can always read/update their own profile regardless of role:

```typescript
if (targetUserId !== ctx.user.id && !roleAtLeast(ctx.user.role, 'admin')) {
  return jsonError(403, 'forbidden', undefined, ctx.request_id);
}
```

## SCIM provisioned users

SCIM users are provisioned with the role from the IdP's `roles[0].value`. Validate the
role on creation:

```typescript
const role = String((body.roles as Array<{value?: string}>)?.[0]?.value ?? 'viewer');
if (!ROLE_RANK[role]) {
  return scimError(400, 'invalidValue', `Invalid role: ${role}. Must be one of: ${Object.keys(ROLE_RANK).join(', ')}`);
}
```

## Audit — log role changes

Role elevation is high-value for security audit:

```typescript
await writeAudit(env, ctx, {
  action: 'user.role_changed',
  resource_kind: 'user',
  resource_id: targetUserId,
  before_state: { role: existing.role },
  after_state: { role: newRole },
});
```

## Gotchas

- **`ROLE_RANK[actual] ?? 0`**: If a user has an unknown role (e.g. DB data corruption), rank defaults to 0 — they get no access. Safe default.
- **`roleAtLeast` not `role === 'admin'`**: Never compare roles with `===` for access checks — it won't work when a higher role (owner, superadmin) tries to do an admin-level action.
- **Superadmin is not a tenant role**: Superadmin should be granted by the platform, not by tenant owners. Store separately or check product_type if needed.
- **Role in session vs DB**: Sessions cache the role at login time. If a role changes while a session is active, the change takes effect at next login (or on session refresh). For immediate enforcement, check role from DB in sensitive handlers.

## Related

- `mccontext-gate-pattern.md`
- `typescript-route-handler.md`
- `multi-tenant-data-isolation.md`
- `audit-without-user-context.md`
- `error-codes-and-responses.md`
