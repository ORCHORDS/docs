# scim-bearer-token-auth

**Issue:** SCIM 2.0 machine-to-machine bearer token authentication in Cloudflare Workers
**Date:** 2026-08-11
**Status:** documented

## Symptom

Implementing a SCIM 2.0 endpoint that Okta/Azure AD/OneLogin calls to provision users.
SCIM doesn't use session cookies or OAuth — it uses a pre-shared bearer token per tenant.
Need to authenticate the IdP without a user McContext.

## Auth model

SCIM is machine-to-machine. Each tenant has a `scim_token` stored in the `tenants` table.
The IdP sends `Authorization: Bearer <token>` on every request.

```typescript
interface ScimCtx {
  tenant: { id: string };
  request_id: string;
  ip: string;
  user_agent: string;
  // No 'user' — SCIM has no user actor
}

async function scimAuth(request: Request, env: Env): Promise<ScimCtx | Response> {
  const auth = request.headers.get('authorization') || '';
  const m = /^Bearer\s+(\S+)$/i.exec(auth);
  if (!m) return scimError(401, 'unauthorized', 'Missing or invalid Authorization header');

  const token = m[1];

  // Step 1: DB lookup by token (fast path — SQL equality)
  const row = await env.DB!.prepare(
    `SELECT id FROM tenants WHERE scim_token IS NOT NULL AND scim_token = ? LIMIT 1`
  ).bind(token).first<{ id: string }>();
  if (!row) return scimError(401, 'unauthorized', 'Invalid SCIM token');

  // Step 2: Timing-safe re-verification (prevents timing oracle on SQL equality)
  const stored = await env.DB!.prepare(
    `SELECT scim_token FROM tenants WHERE id = ?`
  ).bind(row.id).first<{ scim_token: string }>();
  if (!stored?.scim_token || !(await timingSafeEqual(stored.scim_token, token))) {
    return scimError(401, 'unauthorized', 'Invalid SCIM token');
  }

  return {
    tenant: { id: row.id },
    request_id: crypto.randomUUID(),
    ip: request.headers.get('cf-connecting-ip') || 'unknown',
    user_agent: request.headers.get('user-agent') || 'scim-client',
  };
}
```

## Handler pattern

```typescript
export async function createUser(request: Request, env: Env): Promise<Response> {
  const ctx = await scimAuth(request, env);
  if (ctx instanceof Response) return ctx;  // auth failed — return SCIM error

  const body = await request.json() as Record<string, unknown>;
  const userName = String(body.userName ?? '').trim();
  const displayName = String(body.displayName ?? (body.name as Record<string, unknown>)?.formatted ?? userName);
  const role = String((body.roles as Array<{value?: string}>)?.[0]?.value ?? 'viewer');

  // Provision user with placeholder password hash (can't log in until reset)
  const id = `usr_${crypto.randomUUID().replace(/-/g, '').slice(0, 24)}`;
  await env.DB!.prepare(
    `INSERT INTO users (id, tenant_id, email, display_name, password_hash, role, status, external_id, created_at, updated_at)
     VALUES (?, ?, ?, ?, 'scim:no-password-set', ?, 'active', ?, ?, ?)`
  ).bind(id, ctx.tenant.id, userName, displayName, role, body.externalId ?? null, Date.now(), Date.now()).run();

  await writeAudit(env, ctx as any, {  // ScimCtx not full McContext — cast
    action: 'user.scim_created',
    resource_kind: 'user',
    resource_id: id,
    metadata: { external_id: body.externalId, role },
  });

  return scimOk(dbUserToScim(user), 201);
}
```

## SCIM delete = soft delete

SCIM DELETE must NOT hard-delete the row — preserves audit log references and session table integrity:

```typescript
export async function deleteUser(request: Request, env: Env, id: string): Promise<Response> {
  const ctx = await scimAuth(request, env);
  if (ctx instanceof Response) return ctx;

  await env.DB!.prepare(
    `UPDATE users SET status = 'disabled', updated_at = ? WHERE id = ? AND tenant_id = ?`
  ).bind(Date.now(), id, ctx.tenant.id).run();

  return new Response(null, { status: 204 });  // SCIM spec: 204 No Content on delete
}
```

## SCIM user → DB user mapping

| SCIM field | DB column |
|---|---|
| `userName` | `users.email` |
| `displayName` | `users.display_name` |
| `active: false` | `users.status = 'disabled'` |
| `externalId` | `users.external_id` |
| `roles[0].value` | `users.role` |
| `name.formatted` | fallback for `displayName` |

## body.name?.formatted typing

`body` typed as `Record<string, unknown>`, so `body.name` is `unknown`.
Access nested fields with explicit cast:

```typescript
const displayName = String(
  body.displayName
  ?? (body.name as Record<string, unknown>)?.formatted
  ?? userName
);
```

## Gotchas

- **Timing-safe compare is mandatory**: DB token lookup via SQL equality is fast but leaks timing. The two-step lookup (SQL equality + `timingSafeEqual`) is belt-and-suspenders.
- **SCIM content type**: Responses must use `application/scim+json`, not `application/json`.
- **Schema field**: Every SCIM response body needs a `schemas` array, e.g. `["urn:ietf:params:scim:schemas:core:2.0:User"]`.
- **PATCH vs PUT**: Implement PUT (full replace) first. PATCH requires a JSON-Patch parser — cover Okta/Azure with replace-op only.
- **writeAudit ctx cast**: `ScimCtx` doesn't satisfy `Pick<McContext, 'tenant' | 'user' | ...>` because it lacks `user`. Use `ctx as any` or satisfy the interface with a system actor user.
- **Password placeholder**: Provision with a sentinel hash like `'scim:no-password-set'`. User can't log in until an admin calls your reset-password endpoint. Document this clearly.
- **Error body**: SCIM errors have a specific shape — `{ schemas: ['...Error'], status: '401', scimType: 'unauthorized', detail: '...' }` — not the same as your API error format.

## Related

- `audit-without-user-context.md`
- `timing-safe-compare-pitfalls.md`
- `multi-tenant-data-isolation.md`
- `soft-delete-pattern.md`
- `scim-20-2026.md`
