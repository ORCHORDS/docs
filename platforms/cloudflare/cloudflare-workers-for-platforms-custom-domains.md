# Cloudflare Workers for Platforms — Custom Domains per Tenant

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You run a SaaS platform where each customer brings their own domain (e.g. `shop.customer.com`) and you need that domain to route into a per-tenant Worker **without** requiring customers to create their own Cloudflare account. Workers for Platforms (WfP) Dynamic Dispatch combined with Cloudflare for SaaS Custom Hostnames gives you this: a single platform account that owns the SSL certificate issuance pipeline and routes each inbound hostname to the correct tenant Worker.

---

## Context

Workers for Platforms introduces two new primitives beyond standard Workers:

| Primitive | Purpose |
|-----------|---------|
| **Dispatch namespace** | A registry of named Workers your platform manages on behalf of tenants |
| **Dispatch Worker** (outbound) | Your platform's front-door Worker that receives all requests and routes them by hostname to a tenant Worker in the namespace |

Custom Domains per tenant are enabled via **Cloudflare for SaaS** Custom Hostnames API. Each tenant adds a CNAME from their domain to your platform's `*.customers.example.com` fallback origin, Cloudflare issues the cert, and the Dispatch Worker receives the request with the original `Host` header intact.

Flow:
```
customer.example.com (CNAME → platform.example.com)
  → Cloudflare edge (SNI, cert issued via CF for SaaS)
  → Dispatch Worker (reads Host header, looks up tenant ID in KV)
  → Dynamic Dispatch → tenant Worker in namespace
```

---

## Wrangler Configuration

```toml
# wrangler.toml — Dispatch (front-door) Worker
name = "platform-dispatch"
main = "src/dispatch.ts"
compatibility_date = "2026-01-01"

[[dispatch_namespaces]]
binding = "TENANT_NAMESPACE"
namespace = "saas-tenants"

[[kv_namespaces]]
binding = "HOSTNAME_MAP"
id = "abc123"
```

---

## Provisioning a Tenant Worker via REST API

```typescript
// scripts/provision-tenant.ts — run from CI / admin backend
interface ProvisionOptions {
  accountId: string;
  apiToken: string;
  namespaceName: string;
  tenantId: string;
  workerScript: string; // raw ES module Worker source
  customHostname: string; // e.g. "shop.customer.com"
  fallbackOrigin: string; // e.g. "customers.example.com"
}

async function provisionTenant(opts: ProvisionOptions): Promise<void> {
  const {
    accountId, apiToken, namespaceName,
    tenantId, workerScript, customHostname, fallbackOrigin,
  } = opts;

  const baseUrl = `https://api.cloudflare.com/client/v4/accounts/${accountId}`;
  const headers = {
    Authorization: `Bearer ${apiToken}`,
    "Content-Type": "application/json",
  };

  // 1. Upload tenant Worker into the dispatch namespace
  const formData = new FormData();
  formData.append(
    "metadata",
    new Blob(
      [JSON.stringify({ main_module: "worker.mjs", compatibility_date: "2026-01-01" })],
      { type: "application/json" }
    ),
    "metadata.json"
  );
  formData.append(
    "worker.mjs",
    new Blob([workerScript], { type: "application/javascript+module" }),
    "worker.mjs"
  );

  const uploadRes = await fetch(
    `${baseUrl}/workers/dispatch/namespaces/${namespaceName}/scripts/${tenantId}`,
    { method: "PUT", headers: { Authorization: `Bearer ${apiToken}` }, body: formData }
  );
  if (!uploadRes.ok) throw new Error(`Upload failed: ${await uploadRes.text()}`);

  // 2. Create Custom Hostname (CF for SaaS) so the customer domain routes here
  const chRes = await fetch(`${baseUrl}/custom_hostnames`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      hostname: customHostname,
      ssl: { method: "http", type: "dv", settings: { min_tls_version: "1.2" } },
      custom_origin_server: fallbackOrigin,
    }),
  });
  const chBody = await chRes.json() as { result: { id: string } };
  const customHostnameId = chBody.result.id;

  console.log(`Provisioned tenant ${tenantId}: hostname ${customHostname} (id ${customHostnameId})`);
}
```

---

## Dispatch Worker — Routing by Hostname

```typescript
// src/dispatch.ts
interface Env {
  TENANT_NAMESPACE: DispatchNamespace;
  HOSTNAME_MAP: KVNamespace; // hostname → tenantId
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const hostname = request.headers.get("host") ?? "";

    // Strip port if present (local dev)
    const host = hostname.split(":")[0];

    const tenantId = await env.HOSTNAME_MAP.get(host);

    if (!tenantId) {
      return new Response("Unknown host", { status: 404 });
    }

    // Dispatch to the named Worker in the namespace
    let tenantWorker: Fetcher;
    try {
      tenantWorker = env.TENANT_NAMESPACE.get(tenantId, {
        // Optionally pass per-tenant env overrides as outbound worker params
        outbound: {
          params: { tenantId, plan: "pro" },
        },
      });
    } catch (err) {
      return new Response("Tenant worker not found", { status: 502 });
    }

    // Forward the original request; tenant Worker sees the real Host header
    return tenantWorker.fetch(request);
  },
};
```

---

## Registering the Hostname Mapping in KV

```typescript
// scripts/register-hostname.ts — run after provisionTenant()
async function registerHostname(
  kv: KVNamespace,
  hostname: string,
  tenantId: string
): Promise<void> {
  await kv.put(hostname, tenantId, {
    metadata: { registeredAt: new Date().toISOString() },
  });
}

// In a REST admin endpoint (Workers handler):
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const { hostname, tenantId } = await request.json<{
      hostname: string;
      tenantId: string;
    }>();

    await env.HOSTNAME_MAP.put(hostname, tenantId);
    return Response.json({ ok: true, hostname, tenantId });
  },
};
```

---

## Tenant Worker Template (Minimal)

Tenant Workers execute inside the dispatch namespace. They receive real requests with the original `Host` header. They can bind to their own KV, D1, R2 via namespace-level bindings configured during upload.

```typescript
// tenant-worker-template.ts — uploaded per tenant
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    return new Response(
      `<html><body><h1>Hello from tenant on ${request.headers.get("host")}</h1></body></html>`,
      {
        headers: { "Content-Type": "text/html; charset=utf-8" },
      }
    );
  },
};
```

---

## Polling Custom Hostname SSL Status

Certificate issuance is async. Poll until the hostname is active before making it live.

```typescript
async function waitForSslActive(
  accountId: string,
  apiToken: string,
  customHostnameId: string,
  maxAttempts = 30
): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/custom_hostnames/${customHostnameId}`;

  for (let i = 0; i < maxAttempts; i++) {
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${apiToken}` },
    });
    const body = await res.json() as {
      result: { ssl: { status: string }; status: string };
    };

    if (
      body.result.ssl.status === "active" &&
      body.result.status === "active"
    ) {
      console.log("Custom hostname is active and SSL provisioned");
      return;
    }

    console.log(`Attempt ${i + 1}: ssl=${body.result.ssl.status}, status=${body.result.status}`);
    await new Promise((r) => setTimeout(r, 5000));
  }

  throw new Error("Custom hostname did not become active within timeout");
}
```

---

## Anti-patterns

- **Putting tenant code in the Dispatch Worker directly**: the Dispatch Worker is shared infrastructure. Tenant code must live in the dispatch namespace so it can be updated, deleted, and isolated independently.
- **Storing hostname → tenantId mapping in the Dispatch Worker bundle**: KV is the right store; Worker bundle changes require a new deployment. Use `HOSTNAME_MAP` KV for live routing changes.
- **Skipping Custom Hostname SSL polling**: making the domain live in your UI before the cert is issued causes browser SSL errors during the provisioning window.
- **Not setting `compatibility_date` on uploaded tenant Workers**: omitting it defaults to an old compatibility date which may silently disable newer APIs the tenant's code depends on.
- **Using `env.TENANT_NAMESPACE.get()` without try/catch**: if the tenant Worker script doesn't exist (was deleted or never uploaded), `.get()` throws a `TypeError`. Always catch and return a 502.

---

## Gotchas

- Custom Hostnames require the **Cloudflare for SaaS** add-on (available on Business and Enterprise plans, or purchased separately). It is not included in standard Pro plans.
- The `DispatchNamespace` type is only available in the `@cloudflare/workers-types` package version 4.x+. Pin your types package and import from `cloudflare:workers` or use the global type declaration.
- KV reads in the Dispatch Worker add ~5-50ms globally due to eventual consistency. For ultra-low-latency routing, consider Durable Objects (authoritative reads) or Smart Placement targeting.
- Tenant Workers in a dispatch namespace are **isolated** from each other at the V8 isolate level. A bug in one tenant Worker cannot crash another tenant — but all tenants share the same Cloudflare account limits (subrequests, CPU) unless you set per-script limits via the API.
- Deleting a Custom Hostname does not delete the tenant Worker. Clean up both resources to avoid orphaned billing entries.

---

## Verification

```bash
# List tenant Workers in the namespace
curl "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/dispatch/namespaces/saas-tenants/scripts" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '[.result[].id]'

# Check Custom Hostname SSL status
curl "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/custom_hostnames?hostname=shop.customer.com" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[0] | {status, ssl_status: .ssl.status}'

# Test routing end-to-end
curl -H "Host: shop.customer.com" https://customers.example.com/
```

---

## Related

- `workers-for-platforms-dynamic-dispatch.md`
- `workers-for-platforms-multitenant.md`
- `workers-for-platforms-outbound-workers.md`
- `cloudflare-for-saas-custom-hostnames.md`
- `kv-best-practices.md`

---

## Sources

- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- https://developers.cloudflare.com/cloudflare-for-platforms/cloudflare-for-saas/domain-support/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/dispatch-namespace/
- https://developers.cloudflare.com/api/resources/workers/subresources/dispatch/subresources/namespaces/
