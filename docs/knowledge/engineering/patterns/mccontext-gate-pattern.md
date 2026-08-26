# mccontext-gate-pattern

**Issue:** Multi-tenant authentication gate pattern for Cloudflare Workers SaaS APIs
**Date:** 2026-08-11
**Status:** documented

## Symptom

Building a multi-tenant SaaS API on Cloudflare Pages Functions. Need consistent
auth, tenant isolation, role checks, and audit logging across hundreds of handlers.
Copy-pasting auth code produces subtle bugs (wrong tenant scope, missing role check).

## Root cause

Without a canonical auth context object, each handler independently:
- Re-implements session lookup
- Accesses tenant ID from different fields
- Forgets to check tenant isolation in DB queries
- Misses audit logging

## The McContext Pattern

### Context type

```typescript
// _lib/auth.ts
export interface McUser {
  id: string;
  tenant_id: string;
  role: string;  // 'admin' | 'compliance_officer' | 'viewer' | 'developer'
  email: string;
  display_name: string;
}

export interface McTenant {
  id: string;
  slug: string;
  name: string;
  product_type: string;
  jurisdiction: string;
  primary_locale: string | null;
  plan: string;
  status: string;
}

export interface McContext {
  user: McUser;
  tenant: McTenant;
  session: McSession;
  request_id: string;
  ip: string;
  user_agent: string;
  scopes?: string[];        // set for API key auth; undefined for session auth
  auth_method?: 'api_key' | 'session';
}

export async function authenticate(request: Request, env: Env): Promise<McContext | null> {
  // 1. Extract Bearer token or session cookie
  // 2. Look up in sessions or api_keys table
  // 3. Join with users and tenants
  // 4. Return fully-populated McContext or null
}
```

### Handler pattern (every endpoint)

```typescript
export async function createFinding(request: Request, env: Env): Promise<Response> {
  // 1. Auth gate — ALWAYS first
  const ctx = await authenticate(request, env);
  if (!ctx) return jsonError(401, 'unauthorized', undefined, undefined);

  // 2. Role check
  if (!roleAtLeast(ctx.user.role, 'compliance_officer')) {
    return jsonError(403, 'forbidden', 'compliance_officer role required', ctx.request_id);
  }

  // 3. Parse + validate body
  const body = await request.json() as { title?: string; severity?: string };
  if (!body.title) return jsonError(400, 'invalid_request', 'title required', ctx.request_id);

  // 4. DB operations — ALWAYS scope to tenant
  const id = `fnd_${crypto.randomUUID().replace(/-/g, '').slice(0, 20)}`;
  await env.DB!.prepare(
    `INSERT INTO findings (id, tenant_id, title, severity, created_by, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(id, ctx.tenant.id, body.title, body.severity ?? 'medium', ctx.user.id, Date.now()).run();

  // 5. Audit — always after successful mutation
  await writeAudit(env, ctx, {
    action: 'finding.created',
    resource_kind: 'finding',
    resource_id: id,
    metadata: { title: body.title, severity: body.severity },
  });

  // 6. Respond
  return jsonCreated({ id, title: body.title });
}
```

### Role hierarchy

```typescript
const ROLE_RANKS: Record<string, number> = {
  viewer: 1,
  developer: 2,
  compliance_officer: 3,
  admin: 4,
};

export function roleAtLeast(actual: string, required: string): boolean {
  return (ROLE_RANKS[actual] ?? 0) >= (ROLE_RANKS[required] ?? 0);
}
```

### writeAudit signature

```typescript
export async function writeAudit(
  env: Env,
  ctx: Pick<McContext, 'tenant' | 'user' | 'request_id' | 'ip' | 'user_agent'>,
  event: {
    action: string;
    resource_kind?: string;
    resource_id?: string;
    before_state?: unknown;
    after_state?: unknown;
    metadata?: unknown;
  }
): Promise<void>
```

Key: the 2nd arg is `Pick<McContext, ...>` not a full McContext — pass `ctx` directly.

### jsonError signature

```typescript
export function jsonError(
  status: number,
  code: string,
  message?: string,
  request_id?: string,   // 4th arg is string, NOT McContext
): Response
```

Common mistake: passing `ctx` as 4th arg instead of `ctx.request_id`.

## Migration from old pattern

Old pattern (flat user object):
```typescript
const user = await authenticate(request, env);
if (user instanceof Response) return user;
// user.tenant_id, user.role, user.id
```

New pattern (McContext):
```typescript
const ctx = await authenticate(request, env);
if (!ctx) return jsonError(401, 'unauthorized', undefined, undefined);
// ctx.tenant.id, ctx.user.role, ctx.user.id
```

Batch migration regex (PowerShell):
- `\buser\.tenant_id\b` → `ctx.tenant.id`
- `\buser\.role\b` → `ctx.user.role`
- `\buser\.id\b` → `ctx.user.id`
- `writeAudit\(env, user,` → `writeAudit(env, ctx,`
- `, ctx\)` → `, ctx.request_id)` (for jsonError 4th arg)

## Gotchas

- **Inline import types** `ctx: import("functions/_lib/auth").McContext` — absolute path fails in bundler. Always use a proper import statement and reference `McContext` by name.
- **Partial McTenant in writeAudit**: `{ tenant: { id: ... } }` fails TS because McTenant has required fields. Use `ctx` directly; don't reconstruct a partial.
- **`writeAudit(env, ctx, 'action_string', id)`** — old 4-argument pattern is wrong. Always use the event object: `writeAudit(env, ctx, { action: '...', resource_id: '...' })`.
- **Missing tenant scope in SQL**: Forgetting `AND tenant_id = ?` leaks data across tenants. The McContext makes `ctx.tenant.id` the canonical binding.

## Related

- `audit-without-user-context.md`
- `multi-tenant-data-isolation.md`
- `feature-cookbook-auth.md`
- `api-key-authentication.md`
- `jwt-best-practices.md`
