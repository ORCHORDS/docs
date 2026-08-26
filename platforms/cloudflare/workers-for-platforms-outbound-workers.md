# Workers for Platforms — Outbound Worker Patterns for Egress Policy Enforcement

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You run a multi-tenant Workers for Platforms deployment and need to intercept every `fetch()` call that customer Workers make to the public internet — to enforce allow-lists, inject per-tenant auth headers, rate-limit egress, audit outbound URLs, or rewrite destinations. Without Outbound Workers, customer Workers can call any URL without the platform layer seeing the request.

## Context

Workers for Platforms lets platform operators configure an **Outbound Worker** on each dispatch namespace binding. When a user (customer) Worker calls `fetch()`, the runtime routes that subrequest through the Outbound Worker first. The Outbound Worker receives the original request plus a `props` object set by the dispatcher, can modify or reject it, and then dispatches it to the internet or returns a synthetic response. The Outbound Worker itself is a regular Worker deployed to the same account.

## 1 — Dispatch Namespace Binding with Outbound Worker

```toml
# wrangler.toml for the platform's gateway Worker
[[dispatch_namespaces]]
binding = "DISPATCH"
namespace = "customer-workers"

[dispatch_namespaces.outbound]
service = "platform-outbound-worker"
parameters = ["tenant_id", "plan_tier"]
```

```typescript
// Platform gateway Worker — dispatches to the customer Worker
interface Env {
  DISPATCH: DispatchNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const tenantId = request.headers.get('X-Tenant-ID') ?? 'unknown';
    const planTier = request.headers.get('X-Plan-Tier') ?? 'free';

    const userWorker = env.DISPATCH.get(tenantId, {
      outbound: {
        // These props are forwarded to the Outbound Worker on every egress fetch()
        tenant_id: tenantId,
        plan_tier: planTier,
      },
    });

    return userWorker.fetch(request);
  },
};
```

## 2 — Outbound Worker — Basic Structure

```typescript
// src/outbound.ts — deployed as "platform-outbound-worker"
interface OutboundEnv {
  EGRESS_AUDIT_LOG: Queue;
  TENANT_ALLOWLIST: KVNamespace;
}

interface Props {
  tenant_id: string;
  plan_tier: 'free' | 'pro' | 'enterprise';
}

export default {
  async fetch(
    request: Request,
    env: OutboundEnv,
    ctx: ExecutionContext & { props: Props },
  ): Promise<Response> {
    const { tenant_id, plan_tier } = ctx.props;
    const url = new URL(request.url);

    // Gate egress by plan tier
    if (plan_tier === 'free' && url.hostname !== 'api.example.com') {
      return new Response('Egress to external hosts requires Pro plan', { status: 403 });
    }

    // Inject platform auth header for trusted backends
    const headers = new Headers(request.headers);
    headers.set('X-Platform-Tenant', tenant_id);

    // Audit log (non-blocking)
    ctx.waitUntil(
      env.EGRESS_AUDIT_LOG.send({ tenant_id, url: request.url, ts: Date.now() }),
    );

    return fetch(new Request(request, { headers }));
  },
};
```

## 3 — Allow-List Enforcement

```typescript
async function checkAllowList(
  kv: KVNamespace,
  tenantId: string,
  hostname: string,
): Promise<boolean> {
  const raw = await kv.get(`allowlist:${tenantId}`, 'json') as string[] | null;
  if (!raw) return false; // No allowlist configured — deny all external hosts
  return raw.includes(hostname);
}

export default {
  async fetch(
    request: Request,
    env: OutboundEnv,
    ctx: ExecutionContext & { props: Props },
  ): Promise<Response> {
    const url = new URL(request.url);
    const allowed = await checkAllowList(env.TENANT_ALLOWLIST, ctx.props.tenant_id, url.hostname);

    if (!allowed) {
      return new Response(
        JSON.stringify({ error: 'Host not in tenant egress allow-list', host: url.hostname }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      );
    }

    return fetch(request);
  },
};
```

## 4 — Per-Tenant Rate Limiting via Durable Objects

```typescript
import { DurableObject } from 'cloudflare:workers';

export class TenantEgressLimiter extends DurableObject {
  private count = 0;
  private windowStart = Date.now();
  private readonly LIMIT = 1000;
  private readonly WINDOW_MS = 60_000;

  async checkAndIncrement(): Promise<{ allowed: boolean; remaining: number }> {
    const now = Date.now();
    if (now - this.windowStart > this.WINDOW_MS) {
      this.count = 0;
      this.windowStart = now;
    }
    if (this.count >= this.LIMIT) return { allowed: false, remaining: 0 };
    this.count++;
    return { allowed: true, remaining: this.LIMIT - this.count };
  }

  async fetch(request: Request): Promise<Response> {
    const result = await this.checkAndIncrement();
    return Response.json(result);
  }
}

// In the Outbound Worker:
async function checkRateLimit(
  limiterNs: DurableObjectNamespace,
  tenantId: string,
): Promise<boolean> {
  const id = limiterNs.idFromName(tenantId);
  const stub = limiterNs.get(id);
  const res = await stub.fetch('https://internal/check');
  const { allowed } = await res.json<{ allowed: boolean }>();
  return allowed;
}
```

## 5 — URL Rewriting and Destination Override

```typescript
// Rewrite specific API endpoints to a tenant-specific mirror
const ENDPOINT_MAP: Record<string, string> = {
  'api.thirdparty.com': 'mirror-us.thirdparty.com',
};

export default {
  async fetch(
    request: Request,
    _env: OutboundEnv,
    ctx: ExecutionContext & { props: Props },
  ): Promise<Response> {
    const url = new URL(request.url);
    const overrideHost = ENDPOINT_MAP[url.hostname];

    if (overrideHost) {
      url.hostname = overrideHost;
      return fetch(new Request(url.toString(), request));
    }

    return fetch(request);
  },
};
```

## 6 — Propagating Outbound Errors Back to the Customer Worker

```typescript
export default {
  async fetch(
    request: Request,
    env: OutboundEnv,
    ctx: ExecutionContext & { props: Props },
  ): Promise<Response> {
    try {
      const response = await fetch(request);
      // Add platform observability header without mutating customer response
      const proxied = new Response(response.body, response);
      proxied.headers.set('X-Platform-Egress', 'proxied');
      return proxied;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      // Return a structured error so the customer Worker can handle it
      return Response.json(
        { error: 'Egress failed', reason: message },
        { status: 502 },
      );
    }
  },
};
```

## Anti-patterns

- **Skipping Outbound Workers and embedding egress policy inside each customer Worker template** — any customer who has code execution can bypass it; enforcement must be at the platform layer.
- **Calling `env.DISPATCH.get(...)` inside the Outbound Worker itself** — Outbound Workers cannot re-dispatch into the same namespace; this causes a runtime error.
- **Setting `outbound` parameters to include request secrets** — props are passed as plain JSON and are visible to the customer Worker in error messages; pass only opaque identifiers, not tokens.
- **Returning a non-2xx status from the Outbound Worker without a body** — the customer Worker's `fetch()` call will throw an opaque network error instead of a structured one.

## Gotchas

- Props defined in `wrangler.toml` `parameters` are the only keys the Outbound Worker receives; extra keys passed in `dispatchFetch` options are silently ignored.
- The Outbound Worker does not have access to the dispatch namespace binding (`env.DISPATCH`) — it cannot itself dispatch to customer Workers.
- Outbound Workers are billed against the **platform operator's** account, not the customer's.
- There is exactly **one** Outbound Worker per dispatch namespace binding; you cannot chain multiple.
- `ctx.props` typing requires a manual cast — the Workers runtime does not yet inject the generic type automatically.

## Verification

```typescript
// Smoke test: verify the Outbound Worker blocks a disallowed host
const testRequest = new Request('https://forbidden.example.net/data');
const response = await outboundWorkerFetch(testRequest, env, {
  props: { tenant_id: 'acme', plan_tier: 'free' },
});
console.assert(response.status === 403, 'Expected 403 for disallowed egress');
```

## Related

- `workers-for-platforms-multitenant.md`
- `workers-rpc-service-binding-patterns.md`
- `durable-objects-rate-limiter-pattern.md`
- `workers-service-bindings-advanced.md`

## Sources

- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/configuration/outbound-workers/
- https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/dispatch-namespace/
