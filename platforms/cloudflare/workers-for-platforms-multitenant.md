# Workers for Platforms — Multi-Tenant Script Isolation

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You are building a SaaS product where each customer (tenant) needs to run their own
JavaScript logic at the edge — custom webhooks, transformation rules, pricing hooks, or
personalization logic — without any tenant being able to read or interfere with another
tenant's data or code.  Deploying a monolithic Worker that branches on a tenant ID is
fragile, leaks surface area, and does not scale past a few hundred tenants before config
complexity dominates.  Workers for Platforms (WfP) solves this: each tenant gets their own
isolated Worker script, dispatched through a single privileged "dispatch" Worker you own.

## Context

Workers for Platforms is an enterprise-tier add-on that provides:

- **Dispatch namespaces** — a named registry of user-uploaded scripts addressable by tag.
- **Dynamic dispatch** — your dispatch Worker calls `env.DISPATCH_NAMESPACE.get(tag)` to
  obtain a stub, then invokes the tenant script like any service binding.
- **Script-level isolation** — each tenant script runs in its own V8 isolate; no shared
  memory, no prototype pollution across tenants.
- **Outbound Workers** — optional choke-point Workers that intercept every `fetch()` made
  by tenant scripts, letting you enforce allow-lists or inject auth headers.
- **Limits** — tenant scripts inherit the same CPU/memory limits as ordinary Workers but
  can be further capped; the dispatch Worker itself has a 50 ms CPU budget separate from
  each dispatched script's budget.

Platform compatibility date: `2023-03-01` or later required for dispatch namespace
bindings.

## Wrangler / Dashboard Setup

### 1. Create the dispatch namespace

```bash
npx wrangler dispatch-namespace create my-platform-ns
```

List namespaces:

```bash
npx wrangler dispatch-namespace list
```

### 2. Dispatch Worker — wrangler.toml

```toml
name        = "platform-dispatch"
main        = "src/dispatch.ts"
compatibility_date = "2024-09-23"

[[dispatch_namespaces]]
binding = "DISPATCH"
namespace = "my-platform-ns"
# optional: chain every tenant fetch() through your outbound Worker
outbound = { service = "platform-outbound", environment = "production" }
```

### 3. Dispatch Worker — src/dispatch.ts

```typescript
interface Env {
  DISPATCH: DispatchNamespace;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Extract tenant identifier — from subdomain, JWT, or URL prefix
    const tenantId = getTenantFromRequest(request);
    if (!tenantId) {
      return new Response("Missing tenant", { status: 400 });
    }

    // Fetch a callable stub for this tenant's script
    const tenantScript = env.DISPATCH.get(tenantId, {
      // Pass arbitrary parameters visible to the tenant script via env
      parameters: {
        TENANT_ID: tenantId,
        PLAN: "pro",          // injected from your DB, not from the tenant
      },
      // Optional: override limits per tenant
      limits: { cpuMs: 10 },
    });

    try {
      return await tenantScript.fetch(request);
    } catch (e: unknown) {
      const err = e as Error;
      if (err.name === "WorkerNotFoundError") {
        return new Response("Tenant script not found", { status: 404 });
      }
      console.error(`Dispatch error for tenant ${tenantId}:`, err.message);
      return new Response("Internal error", { status: 500 });
    }
  },
};

function getTenantFromRequest(request: Request): string | null {
  const url = new URL(request.url);
  // Pattern: platform.example.com/t/{tenantId}/...
  const match = url.pathname.match(/^\/t\/([^/]+)\//);
  return match ? match[1] : null;
}
```

### 4. Upload a tenant script via the REST API

Wrangler does not yet have a first-class `wrangler deploy --dispatch-namespace` flag for
tenant scripts (check release notes — it may land post-2025).  Use the REST API directly:

```bash
ACCOUNT_ID="your-account-id"
NAMESPACE="my-platform-ns"
TENANT_TAG="tenant-abc123"
CF_API_TOKEN="your-token"

curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/dispatch/namespaces/${NAMESPACE}/scripts/${TENANT_TAG}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/javascript" \
  --data-binary @tenant-script.js
```

For ESM-format scripts with multiple modules, use `multipart/form-data`:

```bash
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/dispatch/namespaces/${NAMESPACE}/scripts/${TENANT_TAG}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -F 'metadata={"main_module":"main.js","compatibility_date":"2024-09-23"};type=application/json' \
  -F 'main.js=@./dist/tenant.js;type=application/javascript+module'
```

### 5. Delete a tenant script

```bash
curl -X DELETE \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/dispatch/namespaces/${NAMESPACE}/scripts/${TENANT_TAG}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}"
```

## Outbound Worker Pattern

When tenants need to call external APIs, you almost always want to intercept those calls to
prevent SSRF, add your own auth, or enforce allow-lists.

### src/outbound.ts

```typescript
interface Env {
  // Passed from the dispatch Worker's outbound binding
  TENANT_ID: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Block private IP ranges
    if (isPrivateHost(url.hostname)) {
      return new Response("Forbidden: private network access blocked", { status: 403 });
    }

    // Enforce allow-list from your config store
    const allowed = ALLOWED_DOMAINS[env.TENANT_ID] ?? [];
    if (allowed.length > 0 && !allowed.includes(url.hostname)) {
      return new Response(`Forbidden: ${url.hostname} not in tenant allow-list`, {
        status: 403,
      });
    }

    // Add platform-level headers for downstream tracing
    const outHeaders = new Headers(request.headers);
    outHeaders.set("X-Platform-Tenant", env.TENANT_ID);
    outHeaders.delete("Authorization"); // strip tenant's own auth before reuse

    return fetch(new Request(request, { headers: outHeaders }));
  },
};

const ALLOWED_DOMAINS: Record<string, string[]> = {
  "tenant-abc123": ["api.stripe.com", "hooks.slack.com"],
};

function isPrivateHost(host: string): boolean {
  return (
    host === "localhost" ||
    /^127\./.test(host) ||
    /^10\./.test(host) ||
    /^192\.168\./.test(host) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(host)
  );
}
```

## Tenant Script Template (what your tenants upload)

Tenant scripts must export a `fetch` handler.  They cannot use Durable Objects, KV, R2, or
any binding from the *platform* namespace — only the `parameters` you inject.

```typescript
// tenant-script.js — what a tenant developer writes
export default {
  async fetch(request, env) {
    // env.TENANT_ID and env.PLAN are injected by the dispatch Worker
    const data = await request.json();

    // Tenant custom logic: enrich the request
    const enriched = {
      ...data,
      processed_by: env.TENANT_ID,
      plan: env.PLAN,
      timestamp: Date.now(),
    };

    return Response.json(enriched);
  },
};
```

## Mobile vs Desktop Considerations

- Mobile clients may send smaller payloads over HTTP/2 connections; tenant scripts that
  buffer the full request body before processing will add noticeable latency.  Encourage
  tenants to stream responses.
- The outbound Worker intercepts tenant `fetch()` calls regardless of client platform.
  SSRF risk exists equally for all clients; enforce the block unconditionally.
- If tenants generate image transforms, ensure they read `CF-Device-Type` from the
  forwarded request headers to serve appropriately-sized assets to mobile browsers.  Your
  dispatch Worker should forward original CF headers rather than stripping them.

## Limits and Pricing (as of 2026)

| Resource | Limit |
|---|---|
| Scripts per namespace | 10,000 (extendable) |
| Script size | 10 MB (compressed) |
| CPU per dispatched script invocation | 30 s (default), configurable down via `limits.cpuMs` |
| Dispatch Worker CPU | 50 ms (separate budget) |
| Namespaces per account | Contact Cloudflare |

Billing: dispatch namespace invocations count as ordinary Worker requests against your
account's usage plan.  The tenant scripts' CPU time is billed against the platform account,
not the tenant.

## Anti-patterns

- **Sharing KV/R2 bindings with tenant scripts via parameters** — parameters are strings
  only; you cannot pass binding stubs.  If tenants need storage, give them a dedicated KV
  namespace and proxy access through your dispatch or outbound Worker.
- **Trusting `env.TENANT_ID` inside the tenant script** — the dispatch Worker injects this,
  so a malicious tenant cannot spoof it.  But do not let the tenant script use it as an
  auth credential downstream without re-validation.
- **Uploading tenant scripts synchronously in the request path** — script deployment takes
  hundreds of milliseconds and should be queued (Cloudflare Queues or your own job system),
  not done inline during tenant signup.
- **Using `eval()` inside tenant scripts** — Workers block `eval()` at the isolate level;
  tenant scripts that rely on it will throw at runtime.

## Gotchas

- **WorkerNotFoundError vs WorkerNotAllowedError** — the first means the script tag does
  not exist; the second means the dispatch Worker's namespace binding is misconfigured.
  Both are catchable as named errors from the `dispatch.fetch()` promise.
- **Compatibility date per tenant** — each tenant script can carry its own compatibility
  date in its metadata.  Old uploads default to the namespace's compatibility date; this
  can cause behavior divergence across tenants.  Pin all uploads to the same date unless
  a specific tenant requires newer APIs.
- **Cold starts** — tenant scripts that have not been invoked recently may cold-start.
  This is particularly noticeable when a new tenant's first request triggers both a
  namespace lookup and an isolate initialization.  Warm-up pings from your dispatch Worker
  can mitigate this for high-value tenants.
- **No `cron` triggers for tenant scripts** — only the dispatch Worker can have scheduled
  events.  If tenants need cron-like behavior, model it as dispatch calls from your own
  scheduled Worker.

## Verification

```bash
# 1. Confirm namespace exists
npx wrangler dispatch-namespace list

# 2. Check a specific tenant script exists
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/dispatch/namespaces/${NAMESPACE}/scripts/${TENANT_TAG}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result.id'

# 3. Tail dispatch Worker logs during a test invocation
npx wrangler tail platform-dispatch --format=pretty

# 4. Send a test request
curl -X POST https://platform.example.com/t/tenant-abc123/hook \
  -H "Content-Type: application/json" \
  -d '{"event":"purchase","amount":99}'

# 5. Verify outbound Worker blocks private IPs
# Deploy a tenant script that tries to fetch http://169.254.169.254/
# and confirm the outbound Worker returns 403.
```

## Related

- `cloudflare-sandbox-sdk-untrusted-code.md` — Cloudflare Sandbox SDK for untrusted code evaluation
- `dynamic-workers-capability-and-cost-boundaries.md` — CPU and cost limits for dynamic Workers
- `workers-service-bindings-advanced.md` — service binding patterns
- `workers-rpc.md` — RPC over service bindings
- `queues-batch-processing.md` — async script upload queue patterns

## Sources

- Cloudflare Workers for Platforms docs: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- Dispatch namespace API reference: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/reference/how-workers-for-platforms-works/
- Outbound Workers: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/configuration/outbound-workers/
- Script upload API: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/get-started/dynamic-dispatch/
