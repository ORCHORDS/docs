# Workers for Platforms Tenant Isolation Deploy

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
A SaaS platform using Cloudflare Workers for Platforms needs to deploy tenant-authored scripts into isolated namespaces, ensuring one tenant's code cannot access another tenant's data, cannot exhaust the platform's rate limits on behalf of other tenants, and can be individually rolled back or suspended without affecting other tenants.

## Context
Workers for Platforms (WfP) provides a dispatch namespace where each tenant script is deployed as a named Worker under the platform owner's account. Tenant isolation is enforced by restricting bindings (KV namespaces, D1 databases, R2 buckets) to per-tenant resources—never shared resources—and by using outbound Workers to intercept and validate all subrequests made by tenant scripts. The deployment pipeline must create per-tenant namespaced resources, upload the tenant script with tenant-scoped bindings, and validate isolation before activating the script for production traffic.

## Platform Architecture

```
                                          ┌─────────────────────────────┐
                                          │   Dispatch Namespace         │
                                          │   (workers-for-platforms)    │
User Request → Platform Worker ──────────▶│   tenant-abc  (script)       │
                                          │   tenant-xyz  (script)       │
                                          │   tenant-def  (script)       │
                                          └─────────────────────────────┘
                    │
                    ▼ (outbound Worker)
         Validates & audits all
         subrequests from tenant scripts
```

## Tenant Resource Provisioning Script

```typescript
// scripts/provision-tenant.ts
// Run once when a new tenant is onboarded — creates isolated bindings.

interface TenantProvisionConfig {
  tenantId: string;           // e.g. "tenant-abc"
  accountId: string;
  apiToken: string;
  kvNamespacePrefix: string;  // e.g. "tenant-kv"
  r2BucketPrefix: string;     // e.g. "tenant-r2"
}

interface ProvisionedResources {
  kvNamespaceId: string;
  r2BucketName: string;
  dispatchNamespace: string;
}

async function cfApi<T>(
  path: string,
  options: { method?: string; body?: unknown; apiToken: string }
): Promise<T> {
  const res = await fetch(`https://api.cloudflare.com/client/v4${path}`, {
    method: options.method ?? "GET",
    headers: {
      Authorization: `Bearer ${options.apiToken}`,
      "Content-Type": "application/json",
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  const json = (await res.json()) as { success: boolean; result: T; errors?: unknown[] };
  if (!json.success) {
    throw new Error(`API error at ${path}: ${JSON.stringify(json.errors)}`);
  }
  return json.result;
}

async function provisionTenant(
  config: TenantProvisionConfig
): Promise<ProvisionedResources> {
  const { tenantId, accountId, apiToken } = config;

  console.log(`Provisioning isolated resources for tenant: ${tenantId}`);

  // 1. Create tenant-scoped KV namespace
  const kvName = `${config.kvNamespacePrefix}-${tenantId}`;
  const kv = await cfApi<{ id: string }>(
    `/accounts/${accountId}/storage/kv/namespaces`,
    { method: "POST", body: { title: kvName }, apiToken }
  );
  console.log(`  KV namespace created: ${kv.id}`);

  // 2. Create tenant-scoped R2 bucket
  const r2Name = `${config.r2BucketPrefix}-${tenantId}`;
  await cfApi(`/accounts/${accountId}/r2/buckets`, {
    method: "POST",
    body: { name: r2Name },
    apiToken,
  });
  console.log(`  R2 bucket created: ${r2Name}`);

  return {
    kvNamespaceId: kv.id,
    r2BucketName: r2Name,
    dispatchNamespace: "platform-dispatch",
  };
}

// CLI entrypoint
const config: TenantProvisionConfig = {
  tenantId: process.argv[2]!,
  accountId: process.env.CF_ACCOUNT_ID!,
  apiToken: process.env.CF_API_TOKEN!,
  kvNamespacePrefix: process.env.KV_PREFIX ?? "tenant-kv",
  r2BucketPrefix: process.env.R2_PREFIX ?? "tenant-r2",
};

const resources = await provisionTenant(config);
console.log("\nProvisioned resources:");
console.log(JSON.stringify(resources, null, 2));
```

## Tenant Script Upload with Isolated Bindings

```typescript
// scripts/deploy-tenant-script.ts
// Upload a tenant's Worker script into the dispatch namespace with tenant-only bindings.

interface TenantDeployConfig {
  tenantId: string;
  scriptPath: string;           // path to compiled tenant Worker .js
  kvNamespaceId: string;
  r2BucketName: string;
  outboundWorkerName: string;   // platform outbound Worker for subrequest auditing
  dispatchNamespace: string;
  accountId: string;
  apiToken: string;
}

async function deployTenantScript(config: TenantDeployConfig): Promise<void> {
  const { tenantId, accountId, apiToken, dispatchNamespace } = config;

  const scriptContent = await Bun.file(config.scriptPath).text();

  const metadata = {
    main_module: "worker.js",
    compatibility_date: "2026-08-01",
    bindings: [
      // Per-tenant KV — tenant cannot see other tenants' namespaces
      {
        type: "kv_namespace",
        name: "TENANT_KV",
        namespace_id: config.kvNamespaceId,
      },
      // Per-tenant R2 — tenant cannot see other tenants' buckets
      {
        type: "r2_bucket",
        name: "TENANT_STORAGE",
        bucket_name: config.r2BucketName,
      },
      // Outbound Worker binding — all fetch() calls from tenant script go through this
      {
        type: "outbound_worker",
        outbound: {
          worker: {
            service: config.outboundWorkerName,
            environment: "production",
          },
          // Forward tenant context to the outbound Worker
          params: [{ name: "tenantId" }],
        },
      },
    ],
    // Restrict what the tenant script can call
    limits: {
      cpu_ms: 50,         // 50ms CPU time max per request
    },
    // Tenant context injected as env var (not a secret — just metadata)
    vars: {
      TENANT_ID: tenantId,
      PLATFORM_VERSION: "2.0",
    },
  };

  const form = new FormData();
  form.append("metadata", JSON.stringify(metadata), {
    contentType: "application/json",
    filename: "metadata.json",
  } as never);
  form.append("worker.js", new Blob([scriptContent], { type: "application/javascript+module" }), "worker.js");

  const url =
    `https://api.cloudflare.com/client/v4/accounts/${accountId}` +
    `/workers/dispatch/namespaces/${dispatchNamespace}/scripts/${tenantId}`;

  const res = await fetch(url, {
    method: "PUT",
    headers: { Authorization: `Bearer ${apiToken}` },
    body: form,
  });

  if (!res.ok) {
    throw new Error(`Deploy failed for ${tenantId}: ${await res.text()}`);
  }

  console.log(`Tenant script deployed: ${tenantId}`);
}

await deployTenantScript({
  tenantId: process.argv[2]!,
  scriptPath: process.argv[3]!,
  kvNamespaceId: process.env.TENANT_KV_ID!,
  r2BucketName: process.env.TENANT_R2_BUCKET!,
  outboundWorkerName: process.env.OUTBOUND_WORKER_NAME!,
  dispatchNamespace: process.env.DISPATCH_NAMESPACE!,
  accountId: process.env.CF_ACCOUNT_ID!,
  apiToken: process.env.CF_API_TOKEN!,
});
```

## Outbound Worker — Subrequest Isolation Gate

```typescript
// outbound-worker/src/index.ts
// Intercepts all fetch() calls made by tenant scripts.
// Deployed as a normal Worker; referenced in tenant binding metadata.

export interface Env {
  ALLOWED_DOMAINS: string;  // comma-separated allowlist, e.g. "api.example.com,cdn.example.com"
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const tenantId = request.headers.get("X-Dispatch-Namespace-Tenant-Id") ?? "unknown";
    const targetUrl = new URL(request.url);

    const allowed = env.ALLOWED_DOMAINS.split(",").map((d) => d.trim());

    // Enforce domain allowlist per tenant
    if (!allowed.includes(targetUrl.hostname)) {
      console.warn(
        `Tenant ${tenantId} blocked subrequest to unauthorized domain: ${targetUrl.hostname}`
      );
      return new Response(
        JSON.stringify({
          error: "Domain not authorized",
          domain: targetUrl.hostname,
        }),
        {
          status: 403,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Forward the request, stripping internal headers
    const sanitized = new Request(request.url, {
      method: request.method,
      headers: (() => {
        const h = new Headers(request.headers);
        h.delete("X-Dispatch-Namespace-Tenant-Id");
        h.set("X-Platform-Tenant", tenantId); // let upstream know the tenant
        return h;
      })(),
      body: request.body,
    });

    return fetch(sanitized);
  },
};
```

## Platform Worker — Dispatch Router

```typescript
// platform-worker/src/index.ts
// Routes incoming traffic to the correct tenant script.

export interface Env {
  DISPATCHER: DispatchNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Resolve tenant ID from hostname or path prefix
    // e.g. tenant-abc.platform.example.com or /tenants/tenant-abc/...
    const subdomain = url.hostname.split(".")[0];
    const tenantId = subdomain.startsWith("tenant-") ? subdomain : null;

    if (!tenantId) {
      return new Response("Tenant not found", { status: 404 });
    }

    try {
      const tenantWorker = env.DISPATCHER.get(tenantId, {
        outbound: {
          // Pass tenant context to the outbound Worker
          params: { tenantId },
        },
      });

      return await tenantWorker.fetch(request);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("Worker not found")) {
        return new Response("Tenant script not deployed", { status: 503 });
      }
      throw err;
    }
  },
};
```

## Tenant Suspension (Emergency Isolation)

```bash
#!/usr/bin/env bash
# scripts/suspend-tenant.sh
# Immediately removes a tenant script from the dispatch namespace.
set -euo pipefail

TENANT_ID=${1:?Usage: suspend-tenant.sh <tenant-id>}
NAMESPACE=${DISPATCH_NAMESPACE:?}
ACCOUNT_ID=${CF_ACCOUNT_ID:?}
API_TOKEN=${CF_API_TOKEN:?}

echo "Suspending tenant: ${TENANT_ID} from namespace: ${NAMESPACE}"

curl -sf -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/dispatch/namespaces/${NAMESPACE}/scripts/${TENANT_ID}" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  | jq '.success'

echo "Tenant ${TENANT_ID} suspended. All requests will receive 503."
```

## Anti-patterns
- Sharing a single KV namespace across tenants with a key-prefix scheme — prefix isolation has no hard enforcement at the API layer; a tenant script can scan arbitrary keys.
- Storing the platform's CF API token in a tenant script's environment — grants the tenant the ability to deploy or delete other tenant scripts.
- Allowing tenant scripts unrestricted `fetch()` without an outbound Worker — enables SSRF attacks against internal services and metadata endpoints.
- Using a single dispatch namespace for multiple isolation levels (e.g. free vs. enterprise tenants) without quota tagging — makes per-tier rate limiting impossible.
- Deploying tenant scripts synchronously during user sign-up HTTP requests — provision resources asynchronously via a queue to avoid sign-up timeouts.

## Gotchas
- Dispatch namespace scripts inherit the platform owner's account limits but count toward the owner's CPU and request quotas — implement per-tenant rate limiting at the platform Worker layer.
- The outbound Worker parameter names (`params`) must exactly match what the platform Worker passes in `get()` options; mismatch silently omits the tenant context.
- Deleting a dispatch namespace script is immediate and irreversible via API; implement a soft-suspend (replace script with a 503 stub) before hard deletion.
- `cpu_ms` limits in the script metadata are a Wrangler internal field; enforcement behavior may vary — always also test with wrangler tail to confirm.
- Platform Workers that dispatch to tenant scripts cannot currently share Workers KV read-through cache with the dispatched script.

## Verification
1. Deploy a test tenant script and confirm `curl -I https://tenant-test.platform.example.com` routes through the dispatch namespace.
2. Attempt a `fetch("https://evil.example.com")` from a tenant script and confirm the outbound Worker returns 403.
3. Try to access a different tenant's KV namespace ID from a tenant script and confirm the binding is undefined.
4. Run `suspend-tenant.sh tenant-test` and confirm subsequent requests return 503 within 1 second.
5. Confirm Analytics Engine or Tail Worker logs show `tenantId` on every dispatched request for auditability.

## Related
- `workers-for-platforms-dispatch-namespace-deploy.md`
- `deploy-cost-attribution-per-service-d1-billing.md`
- `workers-binding-version-management.md`
- `cloudflare-access-bypass-list-deploy.md`
- `multi-account-deployment-strategies.md`

## Sources
- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/configuration/outbound-workers/
- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/reference/limits/
