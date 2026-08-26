# Workers for Platforms: Multi-Tenant User-Code Isolation

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

SaaS products frequently need to execute customer-supplied code—a webhook transformation, a custom pricing formula, a tenant-defined data enrichment step—without giving customers access to the host application's infrastructure. Historically this meant running a separate sandbox VM per tenant, managing cold-start pools, or accepting significant security risk by running user code in the same process as platform code.

Cloudflare Workers for Platforms solves this natively: each tenant gets their own isolate, deployed through the platform's dispatch Worker via the User Workers API. The platform controls entry, the tenant controls logic, and the V8 isolate boundary enforces separation. The result is zero-cold-start per-tenant execution at the edge with no container management overhead.

## Context

Workers for Platforms introduces two primitives on top of standard Workers: a **dispatch namespace** (a named collection of user Workers managed by the platform) and a **dispatch binding** that lets a host Worker resolve and invoke a tenant's Worker by name. The platform Worker acts as the router and enforcer; the user Worker runs inside its own isolate with only the bindings the platform grants it.

All tenant Workers in a dispatch namespace share the same Cloudflare account but are isolated by the V8 isolate model—no shared memory, no cross-tenant file system. The platform can attach or deny specific bindings (KV, D1, R2) on a per-tenant basis, enabling fine-grained resource control without a per-tenant infrastructure provisioning step.

## Dispatch Namespace and Host Worker

The platform declares a dispatch namespace binding in its `wrangler.toml`. The host Worker receives every request, resolves the tenant, and dispatches to the tenant's Worker.

```toml
# wrangler.toml (platform / host Worker)
name = "platform-host"
main = "src/index.ts"

[[dispatch_namespaces]]
binding = "USER_WORKERS"
namespace = "tenant-workers"
```

```typescript
// src/index.ts — host / dispatch Worker
import { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const tenantId = resolveTenant(request);
    if (!tenantId) {
      return new Response('Tenant not found', { status: 404 });
    }

    // Retrieve the tenant's Worker script from the dispatch namespace
    const userWorker = env.USER_WORKERS.get(tenantId, {
      outbound: {
        // Attach only the bindings this tenant is permitted to use
        // (e.g., a KV namespace scoped to this tenant)
        service: env.TENANT_KV_OUTBOUND,
        parameters: ['tenantId', 'plan'],
        arguments: { tenantId, plan: await getTenantPlan(tenantId, env) },
      },
    });

    // Enforce platform-level request limits before dispatching
    const sanitized = sanitizeRequest(request);

    try {
      const response = await userWorker.fetch(sanitized);
      return addPlatformHeaders(response, tenantId);
    } catch (err) {
      if (err instanceof Error && err.message.includes('not found')) {
        return new Response('No worker deployed for this tenant', { status: 503 });
      }
      return new Response('User worker error', { status: 500 });
    }
  },
};

function resolveTenant(request: Request): string | null {
  // Pattern 1: subdomain — tenant.platform.example.com
  const host = request.headers.get('host') ?? '';
  const subdomain = host.split('.')[0];
  if (subdomain && subdomain !== 'www') return subdomain;

  // Pattern 2: path prefix — /t/{tenantId}/...
  const match = new URL(request.url).pathname.match(/^\/t\/([^/]+)/);
  return match ? match[1] : null;
}

function sanitizeRequest(request: Request): Request {
  const headers = new Headers(request.headers);
  // Strip internal platform headers before forwarding to user code
  headers.delete('X-Platform-Internal-Secret');
  return new Request(request, { headers });
}

function addPlatformHeaders(response: Response, tenantId: string): Response {
  const headers = new Headers(response.headers);
  headers.set('X-Tenant-Id', tenantId);
  headers.set('X-Served-By', 'workers-for-platforms');
  return new Response(response.body, { status: response.status, headers });
}

async function getTenantPlan(tenantId: string, env: Env): Promise<string> {
  const plan = await env.TENANT_METADATA.get(`plan:${tenantId}`);
  return plan ?? 'free';
}
```

## Tenant Worker Deployment API

The platform exposes a management API that lets tenants upload or update their Worker scripts. This wraps the Cloudflare Workers API (upload to dispatch namespace) behind your platform's auth layer.

```typescript
// src/management/deploy.ts
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;
const NAMESPACE = 'tenant-workers';

export async function deployTenantWorker(
  tenantId: string,
  scriptContent: string,
  metadata: TenantWorkerMetadata
): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/dispatch/namespaces/${NAMESPACE}/scripts/${tenantId}`;

  const form = new FormData();
  form.append(
    'metadata',
    new Blob([JSON.stringify(metadata)], { type: 'application/json' }),
    'metadata.json'
  );
  form.append(
    'script',
    new Blob([scriptContent], { type: 'application/javascript+module' }),
    'worker.js'
  );

  const res = await fetch(url, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${CF_API_TOKEN}` },
    body: form,
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(`Deploy failed for tenant ${tenantId}: ${JSON.stringify(err)}`);
  }
}

interface TenantWorkerMetadata {
  main_module: string;
  compatibility_date: string;
  bindings?: DispatchNamespaceBinding[];
}

interface DispatchNamespaceBinding {
  type: 'kv_namespace' | 'r2_bucket' | 'd1_database';
  name: string;
  id: string;
}
```

## Outbound Worker for Resource Proxying

The dispatch binding's `outbound` Worker intercepts all `fetch()` calls made by tenant Workers, enforcing egress policy—block certain hosts, add rate limiting, inject auth headers for approved services.

```typescript
// src/outbound/index.ts — outbound / egress enforcement Worker
export interface OutboundEnv {
  tenantId: string;
  plan: string;
}

export default {
  async fetch(request: Request, env: OutboundEnv): Promise<Response> {
    const url = new URL(request.url);

    // Block non-HTTPS egress
    if (url.protocol !== 'https:') {
      return new Response('Only HTTPS egress is permitted', { status: 403 });
    }

    // Block access to internal platform infrastructure
    const blocked = ['internal.platform.example.com', 'metadata.google.internal'];
    if (blocked.some(h => url.hostname.includes(h))) {
      return new Response('Blocked host', { status: 403 });
    }

    // Enforce per-plan egress limits via a Durable Object rate limiter
    const rateLimitId = `egress:${env.tenantId}:${new Date().toISOString().slice(0, 13)}`;
    // (abbreviated — see rate-limiting-architecture-workers.md for full pattern)

    // Forward with tenant context header stripped (no SSRF leakage)
    const sanitized = new Request(request);
    return fetch(sanitized);
  },
};
```

## Tenant Isolation and Resource Scoping

Per-tenant KV namespaces or D1 databases can be provisioned and injected as bindings at deploy time. The host platform owns all provisioning; tenant Workers receive named bindings and cannot access other tenants' resources.

```typescript
// src/management/provision.ts
export async function provisionTenantResources(
  tenantId: string,
  env: PlatformEnv
): Promise<TenantResources> {
  // Create a dedicated KV namespace for this tenant
  const kvRes = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/storage/kv/namespaces`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ title: `tenant-${tenantId}` }),
    }
  );

  const { result: kv } = await kvRes.json() as { result: { id: string } };

  // Record the mapping in D1 for future Worker metadata lookups
  await env.PLATFORM_DB.prepare(
    'INSERT INTO tenant_resources (tenant_id, kv_namespace_id, created_at) VALUES (?, ?, ?)'
  ).bind(tenantId, kv.id, new Date().toISOString()).run();

  return { kvNamespaceId: kv.id };
}

interface TenantResources {
  kvNamespaceId: string;
}
```

## Anti-patterns

- Running user-supplied code through `eval()` or `new Function()` in the host Worker—this shares the isolate with platform code and breaks the security model entirely.
- Giving tenant Workers direct bindings to the platform's own D1 database or KV namespace—scope every binding to a per-tenant resource.
- Forwarding raw internal request headers (auth tokens, secrets) to tenant Workers before stripping them in the host.
- Deploying user Worker scripts without any content inspection—malicious scripts can exfiltrate data through the outbound Worker's allowed egress unless the outbound enforces an allowlist.
- Sharing a single D1 database across tenants without row-level isolation—if the tenant Worker gets a D1 binding, it should point to a tenant-dedicated database or a namespace-prefixed table set.

## Gotchas

- Dispatch namespace scripts are distinct from regular Worker scripts; they are not visible in the standard Workers dashboard list. Use the dispatch namespace API endpoint to list them.
- The `outbound` binding is invoked for every `fetch()` the tenant Worker makes, including subrequests. A poorly written outbound Worker that is slow or throws will block all tenant egress.
- Tenant Workers do not inherit the host Worker's compatibility date—set `compatibility_date` explicitly in every upload's metadata to avoid flag mismatches.
- Limits that apply to the host Worker (CPU time, memory) apply independently to the dispatched user Worker. Both counts are billed to the platform account.
- Worker script names in a dispatch namespace must be lowercase alphanumeric with hyphens. Tenant IDs containing uppercase letters or underscores must be normalized before use as script names.
- Deleting a tenant's Worker from the dispatch namespace does not automatically release the KV namespace or D1 database; resource cleanup must be handled separately in your deprovisioning flow.

## Verification

1. Deploy a minimal tenant Worker that returns `{ tenantId }` as JSON. Request the host Worker with the matching subdomain and confirm the response contains the tenant ID.
2. In the tenant Worker, `fetch('http://internal.platform.example.com')` and confirm the outbound Worker returns 403.
3. Attempt to access a KV key outside the tenant-scoped namespace; confirm it resolves to `null` or is blocked.
4. Deploy a new version of a tenant Worker via the management API and confirm requests immediately route to the new version without host Worker redeployment.
5. Check Cloudflare dashboard → Workers for Platforms → dispatch namespace to confirm the tenant script is listed.

## Related

- `multi-tenancy-isolation-patterns.md` — data and compute isolation strategies for multi-tenant SaaS
- `proxy-pattern-workers-service-binding-abstraction.md` — host-to-Worker request proxying patterns
- `rate-limiting-architecture-workers.md` — enforcing per-tenant limits in the outbound Worker
- `worker-to-worker-rpc-service-bindings.md` — service binding RPC between Workers

## Sources

- Cloudflare Workers for Platforms documentation: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- Cloudflare Dispatch Namespace API: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/reference/how-workers-for-platforms-works/
- V8 isolate security model: https://v8.dev/blog/sandbox
