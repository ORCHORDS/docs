# Workers for Platforms: Dynamic Dispatch Worker Pattern

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You are building a multi-tenant SaaS platform where each customer needs to run their own
custom logic at the edge — user-defined webhook transformers, per-tenant request
middleware, plugin systems, or white-label edge functions. You need a way to route
incoming requests to the right customer-owned Worker script dynamically, without
pre-deploying a fixed set of Workers or maintaining a routing Worker that embeds all
tenant logic.

Workers for Platforms (WfP) Dynamic Dispatch solves this: a top-level "dispatch Worker"
inspects the request, looks up the appropriate user Worker by namespace tag or script
name, and runs it — all within a single CPU-time budget.

## Context

Workers for Platforms has two core concepts:

1. **User Workers** — tenant scripts uploaded via the WfP Upload API (not `wrangler deploy`).
   They live in a Dispatch Namespace and are addressed by a name you assign.
2. **Dispatch Worker** — the entry-point Worker you deploy normally. It has a binding to
   the Dispatch Namespace and calls `dispatchNamespace.get(scriptName)` to obtain a
   stub, then `stub.fetch(request)` to invoke the user Worker.

The dispatch Worker acts as a gatekeeper: it authenticates the request, resolves the
tenant ID to a script name, enforces resource limits, and passes a modified request or
additional bindings via `ctx.passThroughOnException()` or `env` overrides.

User Workers are uploaded with the WfP REST API using a service account API token
scoped to `Workers Scripts:Edit` on the dispatch namespace. Tenants never touch
`wrangler.toml` — the platform manages everything.

## Setting Up the Dispatch Namespace

```bash
# Create the namespace (one per environment: prod, staging)
wrangler dispatch-namespace create my-platform-prod

# Upload a tenant script (done by your platform's onboarding service, not tenants)
wrangler dispatch-namespace upload my-platform-prod \
  --name tenant-acme \
  --outdir ./tenant-scripts/acme/dist \
  -- dist/index.js

# List scripts in the namespace
wrangler dispatch-namespace list my-platform-prod
```

## Dispatch Worker Implementation

```typescript
// src/dispatch.ts
export interface Env {
  DISPATCH_NS: DispatchNamespace;
  // KV stores tenant_id → script_name mappings
  TENANT_MAP: KVNamespace;
  // Shared platform secret for HMAC validation
  PLATFORM_SECRET: string;
}

/** Resolve the tenant identifier from the request. */
async function resolveTenantScript(
  request: Request,
  env: Env
): Promise<string | null> {
  // Strategy 1: hostname-based (acme.yourplatform.com → "tenant-acme")
  const host = new URL(request.url).hostname;
  const subdomain = host.split('.')[0];
  if (subdomain && subdomain !== 'www') {
    const scriptName = await env.TENANT_MAP.get(`host:${subdomain}`);
    if (scriptName) return scriptName;
  }

  // Strategy 2: X-Tenant-ID header (for API clients)
  const tenantId = request.headers.get('x-tenant-id');
  if (tenantId) {
    const scriptName = await env.TENANT_MAP.get(`tenant:${tenantId}`);
    if (scriptName) return scriptName;
  }

  return null;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Reject oversized bodies before dispatching
    const contentLength = parseInt(request.headers.get('content-length') ?? '0', 10);
    if (contentLength > 10 * 1024 * 1024) {
      return new Response('Request too large', { status: 413 });
    }

    const scriptName = await resolveTenantScript(request, env);
    if (!scriptName) {
      return new Response(JSON.stringify({ error: 'Unknown tenant' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    let userWorker: Fetcher;
    try {
      userWorker = env.DISPATCH_NS.get(scriptName, {
        // Limit what bindings the user Worker can access
        // (omitting limits inherits the dispatch Worker's CPU/memory)
        limits: {
          cpuMs: 100,         // max CPU ms per invocation
        },
        // Inject platform context as outbound bindings available to user Worker
        // via env (only available on Paid plans with custom outbound Worker feature)
      });
    } catch (err: unknown) {
      // Script not found in namespace
      if (err instanceof Error && err.message.includes('does not exist')) {
        return new Response(JSON.stringify({ error: 'Tenant script not deployed' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      throw err;
    }

    // Strip internal headers before forwarding to tenant script
    const forwardedRequest = new Request(request);
    forwardedRequest.headers.delete('x-tenant-id');
    // Inject a read-only platform header tenant scripts can trust
    const mutableHeaders = new Headers(forwardedRequest.headers);
    mutableHeaders.set('x-platform-tenant', scriptName);

    const cleanRequest = new Request(request.url, {
      method: request.method,
      headers: mutableHeaders,
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
      redirect: 'manual',
    });

    try {
      const response = await userWorker.fetch(cleanRequest);
      // Strip any attempt by user Worker to set privileged response headers
      const safeHeaders = new Headers(response.headers);
      safeHeaders.delete('set-cookie'); // platform decides cookie policy
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: safeHeaders,
      });
    } catch (err: unknown) {
      // User Worker threw or timed out — return a safe error to the client
      console.error(`Tenant ${scriptName} error:`, err);
      return new Response(JSON.stringify({ error: 'Tenant handler failed' }), {
        status: 502,
        headers: { 'Content-Type': 'application/json' },
      });
    }
  },
};
```

## wrangler.toml for the Dispatch Worker

```toml
name               = "platform-dispatch"
main               = "src/dispatch.ts"
compatibility_date = "2025-09-01"

[[dispatch_namespaces]]
binding   = "DISPATCH_NS"
namespace = "my-platform-prod"

[[kv_namespaces]]
binding = "TENANT_MAP"
id      = "<your-kv-namespace-id>"

[vars]
PLATFORM_SECRET = "replace-with-secret-via-wrangler-secret"

[observability]
enabled = true
```

## Onboarding API: Uploading Tenant Scripts

Your platform's onboarding service (a separate Worker or server) should call the
Cloudflare API to upload tenant scripts programmatically:

```typescript
// platform-api/src/upload-tenant.ts

interface UploadOptions {
  accountId: string;
  namespaceName: string;
  scriptName: string;    // e.g. "tenant-acme"
  scriptContent: string; // compiled ESM bundle as string
  apiToken: string;
}

export async function uploadTenantScript(opts: UploadOptions): Promise<void> {
  const form = new FormData();

  const metadata = JSON.stringify({
    main_module: 'index.js',
    compatibility_date: '2025-09-01',
    // Restrict what user Workers can access
    usage_model: 'standard',
  });

  form.append('metadata', new Blob([metadata], { type: 'application/json' }), 'metadata.json');
  form.append(
    'index.js',
    new Blob([opts.scriptContent], { type: 'application/javascript+module' }),
    'index.js'
  );

  const url = `https://api.cloudflare.com/client/v4/accounts/${opts.accountId}`
    + `/workers/dispatch/namespaces/${opts.namespaceName}/scripts/${opts.scriptName}`;

  const resp = await fetch(url, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${opts.apiToken}` },
    body: form,
  });

  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`Upload failed: ${resp.status} ${body}`);
  }
}

// Delete when tenant offboards
export async function deleteTenantScript(opts: Omit<UploadOptions, 'scriptContent'>): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${opts.accountId}`
    + `/workers/dispatch/namespaces/${opts.namespaceName}/scripts/${opts.scriptName}`;

  const resp = await fetch(url, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${opts.apiToken}` },
  });

  if (!resp.ok && resp.status !== 404) {
    throw new Error(`Delete failed: ${resp.status}`);
  }
}
```

## Anti-patterns

- **Using service bindings instead of dispatch namespaces for dynamic routing** —
  Service bindings are static and defined at deploy time; they cannot route to
  arbitrary scripts determined at runtime. Use `DispatchNamespace.get()` for dynamic
  dispatch.
- **Forwarding the raw request body stream twice** — Once you call `request.arrayBuffer()`
  or `request.json()` for validation in the dispatch Worker, the body is consumed.
  Reconstruct the `Request` object with the buffered bytes when forwarding to the user
  Worker.
- **Trusting headers injected by the user Worker** — Always strip or override response
  headers that have platform-level meaning (e.g., `Set-Cookie`, `Access-Control-Allow-Origin`)
  before returning to the client.
- **Sharing KV or D1 bindings directly with user Workers** — Pass only the data the
  tenant should see, not the binding itself. Use the Outbound Worker pattern or fetch
  your own API to gate access.

## Gotchas

- **Dispatch namespace name is global to your account** — Use `<name>-prod` /
  `<name>-staging` conventions to avoid collisions across environments.
- **`limits.cpuMs` caps CPU only, not wall-clock time** — A user Worker doing slow
  `fetch()` subrequests can still run for up to 30 s. Add a `Promise.race` with
  `AbortSignal.timeout(5000)` if you need wall-clock caps.
- **Script names must be alphanumeric with hyphens** — Tenant IDs that include dots or
  underscores must be mapped to a normalized script name stored in KV.
- **User Workers cannot be updated while serving traffic without downtime** — Cloudflare
  deploys the new script atomically, but in-flight requests to the old version complete
  normally. No blue/green split available within a dispatch namespace.
- **`DispatchNamespace.get()` does not validate script existence at bind time** — The
  error surfaces only when `.fetch()` is called. Always wrap in try/catch.
- **WfP is on the Workers Paid plan** — Dispatch namespaces require the $5/month Workers
  Paid plan. The number of unique tenant scripts is limited by account quotas; contact
  Cloudflare for enterprise limits.

## Verification

```bash
# 1. Deploy dispatch Worker
wrangler deploy

# 2. Upload a minimal tenant script
cat > /tmp/tenant-hello.js << 'EOF'
export default {
  fetch(request) {
    return new Response(`Hello from tenant! host=${new URL(request.url).hostname}`);
  }
};
EOF

wrangler dispatch-namespace upload my-platform-prod \
  --name tenant-hello \
  -- /tmp/tenant-hello.js

# 3. Add tenant mapping to KV
wrangler kv key put --binding TENANT_MAP "host:hello" "tenant-hello"

# 4. Test dispatch
curl -H "Host: hello.yourplatform.com" https://platform-dispatch.your-account.workers.dev/

# Expected: Hello from tenant! host=hello.yourplatform.com

# 5. Test unknown tenant
curl -H "x-tenant-id: unknown" https://platform-dispatch.your-account.workers.dev/
# Expected: {"error":"Unknown tenant"}  HTTP 404
```

## Related

- `workers-for-platforms-multitenant.md` — broader WfP architecture overview
- `workers-for-platforms-outbound-workers.md` — injecting platform context via outbound Workers
- `workers-rpc-service-binding-patterns.md` — static service bindings for known services
- `kv-best-practices.md` — tenant map storage and caching
- `workers-resource-limits.md` — CPU and subrequest limits reference

## Sources

- Workers for Platforms docs: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- Dispatch Namespace API: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/reference/dispatch-namespace/
- Workers Limits: https://developers.cloudflare.com/workers/platform/limits/
- Upload via API reference: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/get-started/upload-custom-worker-scripts/
