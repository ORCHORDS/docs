# typescript-route-handler

**Issue:** Type-safe Cloudflare Workers route handler — full lifecycle pattern
**Date:** 2026-08-11
**Status:** documented

## Symptom

Workers API handlers accumulate ad-hoc patterns: some check auth before body parse, some after;
some return raw `new Response(...)`, some use helpers; some forget audit logging; some leak
data across tenants. No consistent structure.

## The 6-step lifecycle

Every mutating handler should follow this order. Deviation is a bug waiting to happen.

```
1. Auth gate        → authenticate() returns McContext | null
2. Role check       → roleAtLeast(ctx.user.role, 'required_role')
3. Body parse       → request.json() with typed interface
4. Validation       → required fields, format, enum membership
5. DB + business    → always scope to ctx.tenant.id
6. Audit + respond  → writeAudit(), then jsonOk/jsonCreated
```

## Full typed handler template

```typescript
import {
  authenticate, jsonCreated, jsonError, jsonOk,
  roleAtLeast, writeAudit, type Env,
} from '../../../_lib/auth';

// Body interface — narrow, no 'any'
interface CreateWidgetBody {
  name?: string;
  kind?: string;
  config?: Record<string, unknown>;
}

const VALID_KINDS = ['a', 'b', 'c'] as const;
type WidgetKind = typeof VALID_KINDS[number];

export async function createWidget(request: Request, env: Env): Promise<Response> {
  // 1. Auth gate
  const ctx = await authenticate(request, env);
  if (!ctx) return jsonError(401, 'unauthorized', undefined, undefined);

  // 2. Role check
  if (!roleAtLeast(ctx.user.role, 'admin')) {
    return jsonError(403, 'forbidden', 'admin role required', ctx.request_id);
  }

  // 3. Body parse — try/catch for malformed JSON
  let body: CreateWidgetBody;
  try {
    body = await request.json() as CreateWidgetBody;
  } catch {
    return jsonError(400, 'invalid_json', 'Request body must be valid JSON', ctx.request_id);
  }

  // 4. Validation
  if (!body.name?.trim()) {
    return jsonError(400, 'invalid_request', 'name is required', ctx.request_id);
  }
  if (body.kind && !VALID_KINDS.includes(body.kind as WidgetKind)) {
    return jsonError(400, 'invalid_kind', `kind must be one of: ${VALID_KINDS.join(', ')}`, ctx.request_id);
  }

  // 5. DB — always bind ctx.tenant.id
  const id = `wgt_${crypto.randomUUID().replace(/-/g, '').slice(0, 20)}`;
  const now = Math.floor(Date.now() / 1000);
  await env.DB!.prepare(
    `INSERT INTO widgets (id, tenant_id, name, kind, config, created_by, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    id, ctx.tenant.id, body.name.trim(),
    body.kind ?? 'a',
    body.config ? JSON.stringify(body.config) : null,
    ctx.user.id, now, now,
  ).run();

  // 6a. Audit (after successful write)
  await writeAudit(env, ctx, {
    action: 'widget.created',
    resource_kind: 'widget',
    resource_id: id,
    metadata: { name: body.name, kind: body.kind },
  });

  // 6b. Respond
  return jsonCreated({ id, name: body.name.trim(), kind: body.kind ?? 'a' });
}
```

## Read handler pattern (simpler — no audit required)

```typescript
export async function listWidgets(request: Request, env: Env): Promise<Response> {
  const ctx = await authenticate(request, env);
  if (!ctx) return jsonError(401, 'unauthorized', undefined, undefined);

  const url = new URL(request.url);
  const kind = url.searchParams.get('kind');
  const limit = Math.min(Number(url.searchParams.get('limit') ?? 50), 200);

  let sql = `SELECT * FROM widgets WHERE tenant_id = ?`;
  const params: (string | number)[] = [ctx.tenant.id];
  if (kind) { sql += ` AND kind = ?`; params.push(kind); }
  sql += ` ORDER BY created_at DESC LIMIT ?`;
  params.push(limit);

  const rows = await env.DB!.prepare(sql).bind(...params).all<Record<string, unknown>>();
  return jsonOk({ widgets: rows.results, count: rows.results.length }, ctx.request_id);
}
```

## Body parse patterns

### Optional body (body may be empty)
```typescript
let body: Body = {};
try { body = await request.json() as Body; } catch { /* empty body OK */ }
```

### Typed destructuring with defaults
```typescript
const {
  page = 1,
  per_page = 50,
  status,
} = await request.json() as { page?: number; per_page?: number; status?: string };
```

### Dynamic field update (PATCH)
```typescript
const PATCHABLE = ['name', 'kind', 'config'] as const;
const fields: string[] = [];
const values: unknown[] = [];
for (const k of PATCHABLE) {
  if ((body as Record<string, unknown>)[k] !== undefined) {
    fields.push(`${k} = ?`);
    values.push((body as Record<string, unknown>)[k]);
  }
}
if (!fields.length) return jsonError(400, 'no_updates', 'No fields to update', ctx.request_id);
values.push(now, id, ctx.tenant.id);
await env.DB!.prepare(
  `UPDATE widgets SET ${fields.join(', ')}, updated_at = ? WHERE id = ? AND tenant_id = ?`
).bind(...values).run();
```

## jsonOk / jsonCreated

```typescript
// jsonOk → 200
return jsonOk({ data }, ctx.request_id);

// jsonCreated → 201 (use for POST that creates a resource)
return jsonCreated({ id, name });  // no request_id arg
```

Common mistake: `jsonOk({ ... }, 201)` — the second arg to jsonOk is `request_id: string`, not status code.
Use `jsonCreated` for 201 responses.

## Gotchas

- **Body parse before auth**: Auth gate MUST come first. Never parse request body before authenticating.
- **Missing tenant scope**: Every DB query must include `AND tenant_id = ?` bound to `ctx.tenant.id`. A single missing clause is a data leak across tenants.
- **Swallowed audit errors**: Wrap `writeAudit` in try/catch only if the audit failure is truly non-critical. For compliance-sensitive events (delete, export), let audit failures surface.
- **`as Record<string, unknown>` cast for dynamic access**: TypeScript won't let you index a typed object by string key even if the key is in the type. Cast the body for PATCH loops.
- **`for...of` with mixed-type tuples**: `for (const [i, st] of [[0, 'a'], [1, 'b']])` — TS infers `(number | string)[]`, making `i + 1` error. Type the array: `as Array<[number, string]>`.

## Related

- `mccontext-gate-pattern.md`
- `d1-best-practices.md`
- `audit-log-mandatory.md`
- `api-design-best-practices.md`
- `workers-types-migration.md`
