# D1 Multi-Tenant Connection Routing in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You operate multiple D1 databases — one (or more) per tenant — and need to route each request to the correct database without hard-coding bindings. Tenant A's data must never touch Tenant B's database, and adding a new tenant should not require a Worker redeployment.

## Context

Cloudflare Workers can hold multiple D1 bindings in `wrangler.toml`, but bindings are static. For true database-per-tenant isolation beyond what schema isolation or row-level filtering provides, the routing layer must map an incoming tenant identifier to a D1 binding at runtime. The pattern here uses a control-plane KV namespace to store the `binding_name → D1DatabaseId` map and resolves the correct `env` binding dynamically, making tenant provisioning a KV write rather than a deploy.

---

## Control Plane: Tenant Registry in KV

```typescript
// tenant-registry.ts
export interface TenantRecord {
  tenantId: string;
  dbBinding: string; // matches a key in env, e.g. "DB_TENANT_001"
  plan: 'free' | 'pro' | 'enterprise';
}

const REGISTRY_PREFIX = 'tenant:';

export async function resolveTenant(
  kv: KVNamespace,
  tenantId: string
): Promise<TenantRecord | null> {
  return kv.get<TenantRecord>(`${REGISTRY_PREFIX}${tenantId}`, 'json');
}

export async function registerTenant(
  kv: KVNamespace,
  record: TenantRecord
): Promise<void> {
  await kv.put(`${REGISTRY_PREFIX}${record.tenantId}`, JSON.stringify(record));
}
```

---

## Wrangler Configuration

```toml
# wrangler.toml
name = "api"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "TENANT_REGISTRY"
id     = "abc123..."

# One binding per provisioned database
[[d1_databases]]
binding  = "DB_TENANT_001"
database_name = "tenant-001"
database_id   = "uuid-for-tenant-001"

[[d1_databases]]
binding  = "DB_TENANT_002"
database_name = "tenant-002"
database_id   = "uuid-for-tenant-002"
```

---

## Dynamic Binding Resolution

```typescript
// db-router.ts
import { resolveTenant } from './tenant-registry';

export interface Env {
  TENANT_REGISTRY: KVNamespace;
 // dynamic bindings
}

export async function getDb(env: Env, tenantId: string): Promise<D1Database> {
  const record = await resolveTenant(env.TENANT_REGISTRY, tenantId);
  if (!record) throw new Response('Unknown tenant', { status: 404 }) as never;

  const db = env[record.dbBinding] as D1Database | undefined;
  if (!db) {
    // Binding exists in registry but not in env — needs deploy
    throw new Response(`Database binding '${record.dbBinding}' not available`, { status: 503 }) as never;
  }
  return db;
}
```

---

## Request Handler

```typescript
// worker.ts
import { getDb, Env } from './db-router';

function extractTenantId(request: Request): string | null {
  // Strategy 1: subdomain — tenant.example.com
  const host = new URL(request.url).hostname;
  const sub = host.split('.')[0];
  if (sub && sub !== 'www') return sub;

  // Strategy 2: header — X-Tenant-Id: acme
  return request.headers.get('X-Tenant-Id');
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const tenantId = extractTenantId(request);
    if (!tenantId) return new Response('Missing tenant', { status: 400 });

    const db = await getDb(env, tenantId);

    const row = await db
      .prepare('SELECT COUNT(*) AS count FROM orders WHERE status = ?')
      .bind('pending')
      .first<{ count: number }>();

    return Response.json({ tenant: tenantId, pendingOrders: row?.count ?? 0 });
  },
};
```

---

## Tenant Provisioning Flow

```typescript
// provision.ts — called from an admin Worker or CI pipeline
export async function provisionTenant(
  env: Env,
  tenantId: string,
  dbBinding: string
): Promise<void> {
  const { registerTenant } = await import('./tenant-registry');

  // 1. Register mapping in KV
  await registerTenant(env.TENANT_REGISTRY, { tenantId, dbBinding, plan: 'pro' });

  // 2. Run schema migrations on the new database
  const db = env[dbBinding] as D1Database;
  await db.batch([
    db.prepare(`CREATE TABLE IF NOT EXISTS orders (
      id      INTEGER PRIMARY KEY,
      status  TEXT    NOT NULL,
      created TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )`),
    db.prepare(`CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status)`),
  ]);
}
```

---

## Caching the Registry Lookup

KV reads add ~1 ms; cache the resolved binding name per tenant in a `Map` scoped to the Worker isolate for the lifetime of the request burst.

```typescript
// isolate-cache.ts
const cache = new Map<string, string>(); // tenantId → dbBinding

export async function resolveDbCached(
  env: Env,
  tenantId: string
): Promise<D1Database> {
  let binding = cache.get(tenantId);
  if (!binding) {
    const { resolveTenant } = await import('./tenant-registry');
    const record = await resolveTenant(env.TENANT_REGISTRY, tenantId);
    if (!record) throw new Error(`Unknown tenant: ${tenantId}`);
    binding = record.dbBinding;
    cache.set(tenantId, binding);
  }
  const db = env[binding] as D1Database | undefined;
  if (!db) throw new Error(`Binding not deployed: ${binding}`);
  return db;
}
```

---

## Anti-patterns

- **Using a single D1 database with a `tenant_id` column** — does not provide true isolation; a misconfigured query can cross tenant boundaries. Use this routing pattern when isolation is a hard requirement.
- **Hardcoding tenant-to-binding mapping in TypeScript** — adding a tenant requires a code change and redeploy; keep the map in KV.
- **Forgetting to run migrations on newly provisioned databases** — always call the schema init batch immediately after registration.
- **Allowing `env[binding]` without a type guard** — an undeployed binding silently resolves to `undefined`; always guard with an `instanceof` check or an explicit undefined check.

## Gotchas

- Workers `env` is typed as a plain interface; TypeScript cannot statically verify dynamic binding keys — cast carefully and add runtime guards.
- D1 binding names in `wrangler.toml` must be valid JavaScript identifiers (`DB_TENANT_001` is fine; `db-tenant-001` is not).
- The isolate cache survives across requests within the same isolate but is evicted on cold start; do not treat it as durable.
- Maximum D1 bindings per Worker: currently 50 per `wrangler.toml`; for more tenants, fan out to multiple Workers or use Hyperdrive with external databases.
- New bindings added to `wrangler.toml` require a deploy before `env[binding]` resolves; provision the binding *before* writing the KV record to avoid a 503 window.

## Verification

```typescript
async function smokeTest(env: Env): Promise<void> {
  const { registerTenant } = await import('./tenant-registry');
  const { getDb } = await import('./db-router');

  await registerTenant(env.TENANT_REGISTRY, {
    tenantId: 'acme',
    dbBinding: 'DB_TENANT_001',
    plan: 'pro',
  });

  const db = await getDb(env, 'acme');
  const result = await db.prepare('SELECT 1 AS ok').first<{ ok: number }>();
  console.assert(result?.ok === 1, 'Routed correctly to DB_TENANT_001');
}
```

## Related

- `d1-multi-tenant-schema-isolation.md`
- `d1-multi-tenant-schema-per-tenant-isolation.md`
- `d1-hash-partitioned-tenant-sharding-workers.md`
- `d1-row-level-security-tenant-id.md`
- `d1-service-binding-access-isolation-workers.md`
- `kv-ttl-stale-while-revalidate-cache-workers.md`

## Sources

- Cloudflare D1 bindings: https://developers.cloudflare.com/d1/get-started/
- Cloudflare KV: https://developers.cloudflare.com/kv/
- Multi-tenancy design patterns: https://developers.cloudflare.com/d1/tutorials/
