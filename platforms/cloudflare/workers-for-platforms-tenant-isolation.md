# Workers for Platforms Tenant Isolation Patterns

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You're running a SaaS product on Workers for Platforms (WfP) and need to guarantee that one tenant's user-deployed Worker cannot read, write to, or even observe the existence of another tenant's data — including KV namespaces, D1 databases, R2 buckets, Durable Objects, and secrets. Default WfP dispatch gives each tenant a separate Worker script, but binding assignment, CORS policy, and error message leakage require explicit patterns.

## Context

Workers for Platforms lets your platform customers deploy their own Worker scripts via the User Workers API. Each user Worker runs in its own V8 isolate and cannot directly call another. The risk surface is in the **bindings** your dispatch Worker hands to each user Worker, the **CORS headers** the user Worker can emit, and **error responses** that might leak internal structure. Tenant isolation is a binding-assignment problem, not a runtime sandbox problem — V8 isolation is already guaranteed; your job is to ensure the wrong bindings are never passed.

---

## Namespace-per-Tenant Binding Assignment

Every tenant must receive bindings scoped exclusively to their account. Resolve tenant identity in the dispatch Worker before calling `dispatchNamespace.get()`:

```typescript
// dispatch-worker/src/index.ts
interface Env {
  DISPATCH: DispatchNamespace;
  DB: D1Database; // platform metadata DB
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const tenantId = await resolveTenant(req, env);
    if (!tenantId) return new Response('Unauthorized', { status: 401 });

    // Pull per-tenant binding config from D1 — never from the request
    const tenant = await env.DB.prepare(
      `SELECT kv_namespace_id, r2_bucket, do_namespace FROM tenants WHERE id = ?`
    ).bind(tenantId).first<TenantRow>();

    if (!tenant) return new Response('Not found', { status: 404 });

    const userWorker = env.DISPATCH.get(tenantId, {
      outbound: {
        // Inject only this tenant's bindings as environment variables
        // Real bindings are passed via wrangler.toml dispatch configuration
      },
    });

    return userWorker.fetch(req);
  },
};
```

Never derive `tenantId` from a query parameter or header that the end user controls — always from a verified credential (JWT, mTLS cert, Cloudflare Access token).

---

## Outbound Worker: Intercepting Binding Calls

Use an outbound Worker to audit or block binding calls before they reach the platform's infrastructure. The outbound Worker fires for every `fetch()` the user Worker makes to a bound service:

```typescript
// outbound-worker/src/index.ts
interface OutboundEnv {
  TENANT_ID: string; // injected by dispatch worker via params
}

export default {
  async fetch(req: Request, env: OutboundEnv): Promise<Response> {
    const url = new URL(req.url);

    // Block SSRF to internal RFC-1918 ranges
    if (isPrivateIP(url.hostname)) {
      return new Response('Forbidden', { status: 403 });
    }

    // Enforce tenant-scoped path prefix on internal APIs
    if (url.hostname === 'internal.platform.example') {
      const expected = `/tenant/${env.TENANT_ID}/`;
      if (!url.pathname.startsWith(expected)) {
        return new Response('Tenant path violation', { status: 403 });
      }
    }

    return fetch(req); // pass through
  },
};

function isPrivateIP(host: string): boolean {
  return /^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|::1$|fc|fd)/.test(host);
}
```

---

## CORS Isolation: Preventing Cross-Tenant Credential Leakage

User Workers can emit arbitrary `Access-Control-Allow-Origin` headers, which could allow a malicious tenant to harvest cookies from another tenant's subdomain. Enforce CORS at the dispatch layer via a response wrapper:

```typescript
// dispatch-worker — strip and rewrite CORS on every user-Worker response
function enforceCors(res: Response, tenantOrigin: string): Response {
  const headers = new Headers(res.headers);

  // Remove any CORS header the user Worker set
  headers.delete('Access-Control-Allow-Origin');
  headers.delete('Access-Control-Allow-Credentials');

  // Set the platform-approved origin only
  headers.set('Access-Control-Allow-Origin', tenantOrigin);
  headers.set('Vary', 'Origin');

  return new Response(res.body, { status: res.status, headers });
}
```

`tenantOrigin` comes from your platform database, not from the `Origin` request header.

---

## Durable Object Namespace Partitioning

Each tenant should access only Durable Objects within their own namespace. Use a namespaced ID prefix derived from `tenantId` so that even if a user Worker constructs an arbitrary DO ID, it cannot reach another tenant's object:

```typescript
// Platform helper passed to user Workers via service binding
export class TenantDoGateway implements DurableObject {
  constructor(private state: DurableObjectState, private env: GatewayEnv) {}

  async fetch(req: Request): Promise<Response> {
    const { tenantId, objectName } = await req.json<{ tenantId: string; objectName: string }>();

    // Force-prefix the ID — tenant cannot escape their own partition
    const scopedName = `${tenantId}::${objectName}`;
    const id = this.env.USER_DO.idFromName(scopedName);
    const stub = this.env.USER_DO.get(id);

    return stub.fetch(req);
  }
}
```

Never expose the raw `DurableObjectNamespace` binding to user Workers — always mediate through a gateway that enforces the prefix.

---

## Secret Isolation: Per-Tenant Secrets Store

Avoid injecting a blanket `PLATFORM_SECRET` into every user Worker. Use the Secrets Store with per-tenant secret names and inject only what a tenant is authorised to see:

```typescript
// In wrangler.toml for the dispatch worker (conceptual — actual binding
// assignment uses the Workers for Platforms API)
// Each tenant has secrets named: tenant_{id}_api_key, tenant_{id}_db_pass

// Dispatch worker — fetch and inject as opaque env vars
async function getTenantSecrets(tenantId: string, env: Env): Promise<Record<string, string>> {
  // Platform manages a secrets map in D1; actual secret values live in
  // Cloudflare Secrets Store bound to the platform Worker only
  const allowed = await env.DB.prepare(
    `SELECT secret_name FROM tenant_secret_grants WHERE tenant_id = ?`
  ).bind(tenantId).all<{ secret_name: string }>();

  // Build the permitted env subset — user Worker never sees the full env
  return Object.fromEntries(
    allowed.results.map(({ secret_name }) => [
      secret_name,
      (env as Record<string, string>)[`TENANT_${tenantId.toUpperCase()}_${secret_name}`] ?? '',
    ])
  );
}
```

---

## Error Message Sanitisation

Stack traces from user Workers must not be forwarded raw to end users — they may leak internal hostnames, binding names, or path structures from other tenants:

```typescript
async function safeDispatch(worker: Fetcher, req: Request): Promise<Response> {
  try {
    const res = await worker.fetch(req);
    return res;
  } catch (err) {
    // Log full error to Tail Worker for platform ops
    console.error('[tenant-error]', err);

    // Return opaque error to caller
    return new Response(
      JSON.stringify({ error: 'Internal Worker error', code: 'WFP_500' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
```

---

## Anti-patterns

- **Passing all platform bindings to every user Worker** — a user Worker with your main D1 binding can query any tenant's data.
- **Trusting `X-Tenant-ID` headers from end users** — trivially spoofed; derive tenant identity from tokens only.
- **Using the same KV namespace for all tenants with a key prefix** — KV `list()` with a crafted prefix can enumerate other tenants' keys if the user Worker has that binding.
- **Forwarding raw `5xx` error bodies from user Workers** — leaks internal infrastructure details.

---

## Gotchas

- Workers for Platforms does not automatically scope bindings to a tenant; you must assign bindings through the `workers-for-platforms` API per user Worker deployment.
- Outbound Workers add one extra hop (and ~1–2 ms); keep outbound logic minimal.
- `dispatchNamespace.get(scriptName)` accepts the script name verbatim — if `scriptName` is tenant-controlled, validate it against a D1 allowlist before calling.
- `Access-Control-Allow-Credentials: true` combined with a wildcard `*` origin is rejected by browsers, but the risk is still present when the user Worker sets a specific other tenant's origin.

---

## Verification

```bash
# Confirm user Worker cannot list sibling tenant keys
curl -X POST https://platform.example/tenant-a/run \
  -H "Authorization: Bearer $TENANT_A_TOKEN" \
  -d '{"action":"kv-list","prefix":"tenant-b:"}'
# Expected: 403 Tenant path violation

# Confirm CORS header rewrite
curl -I https://platform.example/tenant-a/api \
  -H "Origin: https://tenant-b.platform.example"
# Expected: Access-Control-Allow-Origin: https://tenant-a.platform.example
```

---

## Related

- `workers-for-platforms-dynamic-dispatch.md`
- `workers-for-platforms-multitenant.md`
- `workers-for-platforms-outbound-workers.md`
- `cloudflare-workers-for-platforms-custom-domains.md`
- `workers-rpc-service-binding-patterns.md`
- `cloudflare-access-zero-trust-service-tokens.md`

---

## Sources

- Cloudflare Workers for Platforms documentation: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- Outbound Workers: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/configuration/outbound-workers/
- Secrets Store: https://developers.cloudflare.com/workers/runtime-apis/secrets-store/
- Workers for Platforms API: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/reference/workers-for-platforms-api/
