# Workers for Platforms: Dispatch Namespace Setup and Per-Tenant Routing

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are building a multi-tenant SaaS on Cloudflare Workers and need each customer to run their own isolated Worker logic without managing separate Cloudflare accounts. Workers for Platforms lets you upload per-tenant scripts into a dispatch namespace and route requests through a gateway Worker that calls `dispatcher.get(tenantId)`.

## Context

- Cloudflare Workers for Platforms (enterprise feature, account-level activation required)
- Gateway Worker acts as the entry point; tenant Workers live inside a dispatch namespace
- Tenant scripts are uploaded via the Cloudflare REST API (not `wrangler deploy`)
- Billing: usage-model is `bundled` or `unbound` per uploaded tenant Worker
- Stack: TypeScript Workers, Wrangler v3, REST API, `wrangler.toml`

---

## Section 1: Create and Bind a Dispatch Namespace

```bash
# Create the dispatch namespace (one-time, account-level)
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/dispatch/namespaces" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name": "tenants"}' | jq .

# Verify
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/dispatch/namespaces" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | .name'
```

Bind the namespace in your gateway Worker's `wrangler.toml`:

```toml
# wrangler.toml (gateway Worker)
name = "gateway-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[dispatch_namespaces]]
binding = "DISPATCHER"
namespace = "tenants"
```

---

## Section 2: Upload a Tenant Worker via REST API

```typescript
// scripts/upload-tenant-worker.ts
// Run with: npx ts-node scripts/upload-tenant-worker.ts

const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;
const NAMESPACE = "tenants";

async function uploadTenantWorker(tenantId: string, scriptContent: string) {
  const url = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/dispatch/namespaces/${NAMESPACE}/scripts/${tenantId}`;

  // Metadata part
  const metadata = JSON.stringify({
    main_module: "worker.js",
    compatibility_date: "2024-09-23",
    usage_model: "bundled", // or "unbound" for CPU-heavy tenants
    bindings: [
      // Optional: per-tenant KV, secrets, etc.
    ],
  });

  const form = new FormData();
  form.append("metadata", new Blob([metadata], { type: "application/json" }), "metadata.json");
  form.append(
    "worker.js",
    new Blob([scriptContent], { type: "application/javascript+module" }),
    "worker.js"
  );

  const res = await fetch(url, {
    method: "PUT",
    headers: { Authorization: `Bearer ${CF_API_TOKEN}` },
    body: form,
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Upload failed for tenant ${tenantId}: ${err}`);
  }

  const data = await res.json() as { result: { id: string } };
  console.log(`Uploaded tenant Worker: ${tenantId} -> script id: ${data.result.id}`);
  return data.result;
}

// Example tenant script (TypeScript compiled to JS before upload)
const tenantScript = `
export default {
  async fetch(request, env, ctx) {
    return new Response('Hello from tenant worker!', { status: 200 });
  }
};
`;

uploadTenantWorker("tenant-abc123", tenantScript).catch(console.error);
```

---

## Section 3: Gateway Worker with `dispatcher.get(tenantId)`

```typescript
// src/index.ts — Gateway Worker

export interface Env {
  DISPATCHER: DispatchNamespace;
}

// Type definition for dispatch namespace (not in default Workers types yet)
interface DispatchNamespace {
  get(
    scriptName: string,
    args?: { outbound?: { service: string } }
  ): Fetcher;
}

interface Fetcher {
  fetch(request: Request): Promise<Response>;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Extract tenant ID from subdomain or path prefix
    // Pattern: <tenantId>.platform.example.com  OR  /t/<tenantId>/...
    const tenantId = extractTenantId(url, request.headers.get("host") ?? "");

    if (!tenantId) {
      return new Response("Missing tenant identifier", { status: 400 });
    }

    let tenantWorker: Fetcher;
    try {
      // Resolve the per-tenant script from the dispatch namespace
      tenantWorker = env.DISPATCHER.get(tenantId);
    } catch (e) {
      // Script does not exist in namespace
      return new Response(`Tenant not found: ${tenantId}`, { status: 404 });
    }

    // Forward the original request to the tenant Worker
    // Strip the tenant path prefix if routing via /t/<tenantId>/
    const forwardUrl = new URL(request.url);
    if (forwardUrl.pathname.startsWith(`/t/${tenantId}`)) {
      forwardUrl.pathname = forwardUrl.pathname.slice(`/t/${tenantId}`.length) || "/";
    }

    const forwardRequest = new Request(forwardUrl.toString(), {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });

    return tenantWorker.fetch(forwardRequest);
  },
};

function extractTenantId(url: URL, host: string): string | null {
  // Option A: subdomain routing — tenant-abc123.platform.example.com
  const subdomainMatch = host.match(/^([a-z0-9-]+)\.platform\./);
  if (subdomainMatch) return subdomainMatch[1];

  // Option B: path prefix routing — /t/<tenantId>/...
  const pathMatch = url.pathname.match(/^\/t\/([a-z0-9-]+)/);
  if (pathMatch) return pathMatch[1];

  return null;
}
```

---

## Section 4: Usage Model Billing Notes

```typescript
// scripts/set-usage-model.ts
// Switch a tenant Worker between bundled and unbound

async function setUsageModel(
  tenantId: string,
  model: "bundled" | "unbound"
) {
  // Usage model is set via the metadata field at upload time.
  // To change it post-upload you must re-PUT the script with updated metadata.
  // There is no standalone PATCH endpoint for usage_model.

  // bundled  = Workers Bundled plan (10ms CPU soft cap, cheaper)
  // unbound  = Workers Unbound plan (no CPU cap, billed per CPU-ms)
  console.log(`Set usage model for ${tenantId} to ${model} via re-upload.`);
}

// Pricing reference (2024):
// bundled: $0.50 / 1M requests (after free tier)
// unbound: $0.02 / 1M requests + $0.02 / 1M GB-s CPU time
```

---

## Anti-patterns

- Do not store tenant scripts as raw strings in KV and `eval()` them — use the dispatch namespace API for proper isolation.
- Do not use a single Workers account secret for all tenants; scope bindings per-tenant at upload time.
- Do not skip the `main_module` field in metadata — without it the upload will be treated as a service-worker-format script and ESM imports will fail.
- Do not create one dispatch namespace per tenant — namespaces are containers for many tenant scripts, not per-tenant.

## Gotchas

- `dispatcher.get()` throws synchronously if the script name doesn't exist in the namespace; wrap in try/catch.
- Tenant script names must be valid JavaScript identifiers / DNS-safe strings; avoid special characters.
- Cold-start latency for infrequently-used tenant Workers can be higher than a single always-hot Worker.
- The `DispatchNamespace` type is not yet in `@cloudflare/workers-types`; declare it manually or cast.
- Workers for Platforms requires enterprise enablement; test in a dedicated account, not production.

## Verification

```bash
# List all scripts in the namespace
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/dispatch/namespaces/tenants/scripts" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | .id'

# Invoke the gateway Worker (subdomain routing)
curl -v https://tenant-abc123.platform.example.com/hello

# Invoke via path prefix routing
curl -v https://platform.example.com/t/tenant-abc123/hello

# Delete a tenant Worker
curl -s -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/dispatch/namespaces/tenants/scripts/tenant-abc123" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq .
```

## Related

- `documentation/categories/infra/workers-pages-custom-build-output-config.md`
- `documentation/categories/infra/cloudflare-ddos-managed-ruleset-workers-api.md`

## Sources

- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/reference/how-workers-for-platforms-works/
- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/get-started/configuration/
- https://developers.cloudflare.com/workers/platform/pricing/
