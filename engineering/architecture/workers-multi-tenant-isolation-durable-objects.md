# Multi-Tenant Data Isolation Using Durable Objects per Tenant

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your SaaS application stores data for multiple tenants in shared tables. A query bug, misconfigured RLS rule, or accidental cross-join can expose one tenant's data to another. You need hard isolation boundaries that are enforced by the runtime, not by SQL predicates that developers might accidentally omit.

## Context

Cloudflare Durable Objects (DOs) provide a single-threaded execution context with private, consistent storage. Each DO instance is uniquely identified and owns its own KV-like storage, completely inaccessible from other DO instances. By assigning one DO instance per tenant, you get:

- **Storage isolation** — no shared tables; each tenant's DO has its own private storage namespace.
- **Concurrency isolation** — one DO = one actor; no cross-tenant lock contention.
- **Rate-limit isolation** — per-tenant DO can enforce its own rate limits without affecting other tenants.

Tenant metadata (plan, billing, provisioning status) lives in a shared D1 table and is the source of truth for DO provisioning.

## Solution

### 1. DO ID derivation from tenant ID

```typescript
// src/tenant/tenant-do.ts
export class TenantDO implements DurableObject {
  private storage: DurableObjectStorage;
  private tenantId: string | null = null;

  constructor(state: DurableObjectState, env: Env) {
    this.storage = state.storage;
    // Initialise tenant context from storage on first access
    state.blockConcurrencyWhile(async () => {
      this.tenantId = (await this.storage.get<string>('meta:tenantId')) ?? null;
    });
  }

  async fetch(request: Request): Promise<Response> {
    const url  = new URL(request.url);
    const path = url.pathname;

    // Bootstrap: first call after provisioning sets the tenant ID
    if (request.method === 'POST' && path === '/__init') {
      const { tenantId } = await request.json<{ tenantId: string }>();
      if (this.tenantId && this.tenantId !== tenantId) {
        // Guard: a DO can only serve one tenant
        return Response.json(
          { error: 'DO already bound to a different tenant' },
          { status: 409 },
        );
      }
      this.tenantId = tenantId;
      await this.storage.put('meta:tenantId', tenantId);
      return Response.json({ ok: true });
    }

    // All subsequent calls must identify themselves
    const callerTenantId = request.headers.get('X-Tenant-Id');
    if (!callerTenantId || callerTenantId !== this.tenantId) {
      return Response.json({ error: 'Forbidden' }, { status: 403 });
    }

    return this.dispatchTenantRequest(request, path);
  }

  private async dispatchTenantRequest(request: Request, path: string): Promise<Response> {
    // Example: tenant-scoped data CRUD
    if (request.method === 'GET' && path === '/data') {
      const all  = await this.storage.list<string>({ prefix: 'data:' });
      const data = Object.fromEntries(
        [...all.entries()].map(([k, v]) => [k.replace('data:', ''), v]),
      );
      return Response.json(data);
    }

    if (request.method === 'PUT' && path.startsWith('/data/')) {
      const key   = path.replace('/data/', '');
      const body  = await request.json<{ value: string }>();
      await this.storage.put(`data:${key}`, body.value);
      return Response.json({ ok: true });
    }

    if (request.method === 'DELETE' && path.startsWith('/data/')) {
      const key = path.replace('/data/', '');
      await this.storage.delete(`data:${key}`);
      return Response.json({ ok: true });
    }

    return new Response('Not Found', { status: 404 });
  }
}
```

### 2. Per-tenant rate limiter inside the DO

```typescript
// Inside TenantDO.fetch(), before dispatchTenantRequest()

private async checkRateLimit(): Promise<boolean> {
  const windowKey = `rate:${Math.floor(Date.now() / 60_000)}`; // 1-minute window
  const current = (await this.storage.get<number>(windowKey)) ?? 0;

  const plan   = (await this.storage.get<string>('meta:plan')) ?? 'free';
  const limits: Record<string, number> = { free: 60, pro: 600, enterprise: 6000 };
  const limit  = limits[plan] ?? 60;

  if (current >= limit) return false;

  await this.storage.put(windowKey, current + 1);
  // Auto-expire the key after 2 minutes (no TTL in DO storage — use alarm)
  this.storage.deleteAlarm();
  await this.storage.setAlarm(Date.now() + 120_000);
  return true;
}

async alarm(): Promise<void> {
  // Clean up expired rate-limit windows
  const expiredBefore = Math.floor(Date.now() / 60_000) - 1;
  const keys = await this.storage.list<number>({ prefix: 'rate:' });
  const toDelete: string[] = [];
  for (const [k] of keys) {
    const window = parseInt(k.replace('rate:', ''), 10);
    if (window < expiredBefore) toDelete.push(k);
  }
  if (toDelete.length) await this.storage.delete(toDelete);
}
```

### 3. Worker: resolving the correct DO for a request

```typescript
// src/worker.ts
import type { TenantDO } from './tenant/tenant-do';

export interface Env {
  TENANT_DO: DurableObjectNamespace;
  DB: D1Database;          // shared metadata
  AUTH_SECRET: string;     // JWT / API-key secret
}

export { TenantDO };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // 1. Authenticate and extract tenant ID from token
    const tenantId = await extractTenantId(request, env.AUTH_SECRET);
    if (!tenantId) return Response.json({ error: 'Unauthorised' }, { status: 401 });

    // 2. Check tenant is provisioned in D1
    const tenant = await env.DB
      .prepare('SELECT id, plan, status FROM tenants WHERE id = ?')
      .bind(tenantId)
      .first<{ id: string; plan: string; status: string }>();

    if (!tenant) return Response.json({ error: 'Tenant not found' }, { status: 404 });
    if (tenant.status !== 'active') {
      return Response.json({ error: 'Tenant suspended' }, { status: 403 });
    }

    // 3. Derive deterministic DO ID from tenant ID
    // Using idFromName() guarantees the same tenant always maps to the same DO instance.
    const doId  = env.TENANT_DO.idFromName(tenantId);
    const stub  = env.TENANT_DO.get(doId);

    // 4. Forward request to the tenant DO, injecting X-Tenant-Id header
    const doRequest = new Request(request.url, {
      method:  request.method,
      headers: new Headers({ ...Object.fromEntries(request.headers), 'X-Tenant-Id': tenantId }),
      body:    ['GET', 'HEAD'].includes(request.method) ? null : request.body,
    });

    return stub.fetch(doRequest);
  },
};

async function extractTenantId(request: Request, secret: string): Promise<string | null> {
  const auth  = request.headers.get('Authorization') ?? '';
  const token = auth.replace('Bearer ', '');
  if (!token) return null;
  // Minimal JWT decode (replace with a proper JWKS/HMAC verify in production)
  try {
    const [, payload] = token.split('.');
    const decoded = JSON.parse(atob(payload));
    return decoded.tenant_id ?? null;
  } catch {
    return null;
  }
}
```

### 4. Tenant provisioning and deprovisioning

```typescript
// src/admin/provisioning.ts

export interface Env {
  TENANT_DO: DurableObjectNamespace;
  DB: D1Database;
}

export async function provisionTenant(
  tenantId: string,
  plan: 'free' | 'pro' | 'enterprise',
  env: Env,
): Promise<void> {
  // 1. Insert metadata into shared D1
  await env.DB
    .prepare(
      `INSERT INTO tenants (id, plan, status, created_at)
       VALUES (?, ?, 'active', ?)
       ON CONFLICT(id) DO NOTHING`,
    )
    .bind(tenantId, plan, Date.now())
    .run();

  // 2. Initialise the DO (sets its tenantId binding)
  const doId = env.TENANT_DO.idFromName(tenantId);
  const stub = env.TENANT_DO.get(doId);
  const resp = await stub.fetch('https://internal/__init', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tenantId, plan }),
  });

  if (!resp.ok) throw new Error(`DO init failed: ${await resp.text()}`);
}

export async function deprovisionTenant(tenantId: string, env: Env): Promise<void> {
  // 1. Mark as inactive in D1 (blocks future requests at the Worker level)
  await env.DB
    .prepare(`UPDATE tenants SET status = 'deprovisioned' WHERE id = ?`)
    .bind(tenantId)
    .run();

  // 2. Wipe all DO storage for the tenant
  const doId = env.TENANT_DO.idFromName(tenantId);
  const stub = env.TENANT_DO.get(doId);
  await stub.fetch('https://internal/__wipe', { method: 'POST' });
  // Note: DO instances cannot be deleted via API; they become dormant after storage is cleared.
}
```

### 5. D1 shared metadata schema

```sql
CREATE TABLE tenants (
  id         TEXT PRIMARY KEY,
  plan       TEXT NOT NULL DEFAULT 'free',
  status     TEXT NOT NULL DEFAULT 'active',  -- active | suspended | deprovisioned
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_tenants_status ON tenants (status);
```

### 6. wrangler.toml

```toml
[[durable_objects.bindings]]
name      = "TENANT_DO"
class_name = "TenantDO"

[[migrations]]
tag = "v1"
new_classes = ["TenantDO"]

[[d1_databases]]
binding       = "DB"
database_name = "myapp-shared"
database_id   = "<uuid>"
```

## Implementation Details

- `idFromName(tenantId)` produces a deterministic DO ID. The same string always resolves to the same DO instance in the same namespace — no lookup table required.
- A single DO instance is single-threaded. Concurrent requests from the same tenant are serialised inside the DO, preventing race conditions on tenant state.
- **Cross-tenant prevention**: the DO validates `X-Tenant-Id` against the stored `meta:tenantId` on every request. Even if the Worker routes incorrectly, the DO rejects the request.
- **Plan stored in two places**: D1 (source of truth, for billing queries) and DO storage (for fast rate-limit lookups without a D1 hit per request). Sync on plan upgrade via the admin provisioning flow.

## Anti-patterns

- **Using `idFromString()` on the raw DO hex ID** — bypass `idFromName()`; if you lose the tenant→ID mapping you cannot recover the DO. Always use `idFromName(tenantId)` so the mapping is implicit.
- **Storing cross-tenant references inside DO storage** — a DO should only ever store data belonging to its own tenant.
- **Skipping the D1 status check in the Worker** — without it, a deprovisioned tenant can still reach their DO (whose storage may still have data). Always gate on D1 status.
- **Large per-tenant DOs** — DO storage is optimised for small records. If a tenant generates gigabytes of data, offload blobs to R2 and store only references in the DO.

## Gotchas

- DO instances hibernate after inactivity. The first request after hibernation incurs a cold-start (~1-5 ms). `blockConcurrencyWhile` in the constructor handles state re-hydration safely.
- `state.storage.list()` returns at most 128 entries by default. Pass `{ limit: N }` for larger sets.
- Alarms survive hibernation. Always re-register the alarm on `alarm()` completion if you need it to recur.
- DO egress to external services (R2, D1, external fetch) counts against DO CPU time. Keep the per-request hot path lean.

## Verification

```bash
# Provision a test tenant
curl -X POST https://api.example.com/admin/tenants \
  -H 'Content-Type: application/json' \
  -d '{"tenantId":"t1","plan":"pro"}'

# Write tenant data
curl -X PUT https://api.example.com/data/foo \
  -H 'Authorization: Bearer <tenant-t1-token>' \
  -H 'Content-Type: application/json' \
  -d '{"value":"bar"}'

# Verify cross-tenant access is rejected
curl -X GET https://api.example.com/data/foo \
  -H 'Authorization: Bearer <tenant-t2-token>'
# Expected: 403 Forbidden
```

## Related

- `workers-hexagonal-architecture-ports-adapters.md`
- `workers-event-driven-webhooks-queues.md`
- `workers-strangler-fig-migration-pattern.md`

## Sources

- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare Durable Objects Storage API — https://developers.cloudflare.com/durable-objects/api/storage-api/
