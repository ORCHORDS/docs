# Workers for Platforms Tenant Routing with Custom Domains

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You are building a multi-tenant SaaS product where each customer can bring their own domain (e.g., `shop.customer.com`) and run isolated Worker logic customised to their account. You need to route inbound requests to the correct per-tenant Worker without deploying a new script for each tenant yourself. Unknown tenants or domains that have not been registered must receive a graceful 404 response rather than an unhandled error.

## Context

Workers for Platforms (WfP) introduces the concept of a **dispatch namespace** — a container that holds many user-uploaded Worker scripts keyed by a slug. A **Dispatcher Worker** (your infrastructure-layer Worker) receives every inbound request and calls `env.DISPATCH.get(tenantSlug)` to dynamically fetch and run the tenant's script. Custom domains are mapped to tenant Workers via the Cloudflare API after the tenant's script is uploaded. This model keeps tenant code isolated, allows each tenant to deploy independently via your API, and lets you enforce rate limits or header injection at the dispatcher layer before tenant code runs.

## Creating the Dispatch Namespace

```bash
# Create the namespace once per environment
wrangler dispatch-namespace create my-platform-prod

# Confirm creation
wrangler dispatch-namespace list
```

## Uploading a Per-tenant Worker Script via the User Workers API

```typescript
// src/platform-api/upload-tenant-worker.ts
// Called from your backend when a tenant deploys new code

export async function uploadTenantWorker(
  accountId: string,
  apiToken: string,
  namespaceName: string,
  tenantSlug: string,
  scriptContent: string
): Promise<void> {
  const url = [
    `https://api.cloudflare.com/client/v4/accounts/${accountId}`,
    `/workers/dispatch/namespaces/${namespaceName}/scripts/${tenantSlug}`,
  ].join("");

  const form = new FormData();

  // Main module part
  form.append(
    "worker.js",
    new Blob([scriptContent], { type: "application/javascript+module" }),
    "worker.js"
  );

  // Metadata part — declares module format and compatibility date
  form.append(
    "metadata",
    new Blob(
      [
        JSON.stringify({
          main_module: "worker.js",
          compatibility_date: "2026-06-01",
        }),
      ],
      { type: "application/json" }
    )
  );

  const res = await fetch(url, {
    method: "PUT",
    headers: { Authorization: `Bearer ${apiToken}` },
    body: form,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to upload tenant worker [${tenantSlug}]: ${res.status} ${body}`);
  }

  console.log(`Tenant worker uploaded: ${tenantSlug}`);
}
```

## Dispatcher Worker — Routing Inbound Requests to Tenant Scripts

```typescript
// src/dispatcher-worker.ts
export interface Env {
  DISPATCH: DispatchNamespace; // bound in wrangler.toml
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Derive the tenant slug from the first hostname label
    // e.g. "acme" from "acme.platform.example.com"
    // For custom domains, resolve slug from your own KV/D1 mapping
    const tenantSlug = await resolveTenantSlug(url.hostname, env);

    if (!tenantSlug) {
      return new Response("Tenant not found", { status: 404 });
    }

    let tenantWorker: Fetcher;
    try {
      tenantWorker = env.DISPATCH.get(tenantSlug, {
        limits: {
          cpuMs: 5000,
        },
        // Optionally pass outbound bindings here
      });
    } catch {
      // Tenant slug exists in our DB but script not yet uploaded
      return new Response("Tenant worker not deployed", { status: 503 });
    }

    // Forward the request, optionally inject headers for the tenant
    const forwardedRequest = new Request(request, {
      headers: {
        ...Object.fromEntries(request.headers),
        "X-Tenant-Slug": tenantSlug,
        "X-Platform-Request": "1",
      },
    });

    return tenantWorker.fetch(forwardedRequest);
  },
};

async function resolveTenantSlug(
  hostname: string,
  _env: Env
): Promise<string | null> {
  // Replace with a KV or D1 lookup keyed on the custom domain
  const parts = hostname.split(".");
  return parts.length >= 3 ? parts[0] : null;
}
```

## wrangler.toml — Dispatcher Worker with Namespace Binding

```toml
# wrangler.toml (dispatcher worker)
name = "platform-dispatcher"
main = "src/dispatcher-worker.ts"
compatibility_date = "2026-06-01"

[[dispatch_namespaces]]
binding = "DISPATCH"
namespace = "my-platform-prod"
```

## Associating a Custom Domain with a Tenant Worker via the Cloudflare API

```bash
# 1. The tenant's custom domain must already have its DNS CNAME
#    pointing to the dispatcher worker's *.workers.dev origin or
#    a platform-level Cloudflare zone.

# 2. Add a Custom Domain route that maps the hostname to the
#    dispatcher worker (not the tenant worker directly).
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/platform-dispatcher/domains" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"hostname": "shop.customer.com", "zone_id": "<zone-id>"}'

# 3. Store the hostname → tenantSlug mapping in KV or D1 so
#    resolveTenantSlug() can look it up at request time.
wrangler kv:key put --binding=TENANT_DOMAINS \
  "shop.customer.com" "customer-acme"
```

## Handling Fallback for Unknown Tenants

```typescript
// Fallback Worker deployed to the same dispatch namespace
// under the reserved slug "__404__"
const FALLBACK_SLUG = "__not_found__";

async function fetchWithFallback(
  request: Request,
  env: Env,
  tenantSlug: string
): Promise<Response> {
  try {
    const worker = env.DISPATCH.get(tenantSlug);
    return await worker.fetch(request);
  } catch {
    // Tenant script missing — return branded 404
    return new Response(
      JSON.stringify({ error: "tenant_not_found", slug: tenantSlug }),
      { status: 404, headers: { "Content-Type": "application/json" } }
    );
  }
}
```

## Anti-patterns

- **Putting tenant business logic in the Dispatcher Worker** — the Dispatcher should only route and inject platform-level concerns (auth tokens, rate-limit headers); tenant logic belongs in the user Worker script.
- **Hardcoding tenant slugs in wrangler.toml routes** — this defeats the purpose of WfP; all routing must be dynamic via `env.DISPATCH.get()`.
- **Skipping `limits` in `dispatch.get()`** — without CPU/memory limits a rogue tenant script can consume excessive resources; always set per-tenant limits.
- **Resolving tenant slug from a header the client can spoof** — derive it from the hostname or a signed JWT, never from `X-Tenant-Id` set by the requester.

## Gotchas

- `env.DISPATCH.get()` throws a `TypeError` if the slug does not exist in the namespace — always wrap in try/catch.
- Custom domains must be on a Cloudflare-proxied zone; you cannot attach a custom domain to a Workers for Platforms script on a non-Cloudflare zone.
- Uploading a new script version for a tenant is immediately live; there is no staging lane per tenant in WfP by default — implement blue/green by using separate namespace slugs (`acme-blue` / `acme-green`).
- `DispatchNamespace` binding type is available only in the Workers runtime; you cannot use it in Pages Functions.
- Deleting a tenant slug from the namespace does not remove associated Custom Domain mappings — clean both up together.

## Verification

```bash
# List all scripts in the namespace
wrangler dispatch-namespace list-scripts my-platform-prod

# Test that the dispatcher routes to a tenant script
curl -H "Host: acme.platform.example.com" https://platform-dispatcher.example.workers.dev/

# Verify 404 for unknown tenant
curl -si -H "Host: unknown.platform.example.com" \
  https://platform-dispatcher.example.workers.dev/ | head -5

# Tail dispatcher logs
wrangler tail platform-dispatcher --format pretty
```

## Related

- `workers-static-assets-spa-routing.md`
- `cloudflare-calls-webrtc-workers-signaling.md`

## Sources

- Workers for Platforms documentation — https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- Dispatch Namespaces API — https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/reference/how-workers-for-platforms-works/
- Custom Domains for Workers — https://developers.cloudflare.com/workers/configuration/routing/custom-domains/
