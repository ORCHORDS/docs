# Dynamic Router — Workers Service Bindings

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A single API gateway Worker receives requests that must be dispatched to one of several backend Workers at runtime — not determined by URL path alone, but by content-based criteria such as tenant tier, feature flags, or message type embedded in the request body.

## Context
Cloudflare Workers Service Bindings allow one Worker to call another with zero network egress, sub-millisecond latency, and no extra request charge within the same account. The Dynamic Router pattern keeps routing logic centralised in a gateway Worker that reads routing rules from KV at boot time (or with a short TTL cache) and uses a `dispatchTable` to select the correct service binding at runtime. This avoids hard-wiring routes in `wrangler.toml` and permits hot-updating routing tables without redeployment.

---

## Architecture / Setup

```typescript
// gateway/src/index.ts
export interface Env {
  // All possible backend Workers declared as service bindings in wrangler.toml
  // [[services]] binding = "WORKER_STANDARD", service = "order-worker-standard"
  // [[services]] binding = "WORKER_PREMIUM",  service = "order-worker-premium"
  // [[services]] binding = "WORKER_ENTERPRISE", service = "order-worker-enterprise"
  // [[services]] binding = "WORKER_BETA",     service = "order-worker-beta"
  WORKER_STANDARD: Fetcher;
  WORKER_PREMIUM: Fetcher;
  WORKER_ENTERPRISE: Fetcher;
  WORKER_BETA: Fetcher;

  ROUTING_TABLE: KVNamespace;  // maps routing keys -> binding names
}

type BindingKey = 'WORKER_STANDARD' | 'WORKER_PREMIUM' | 'WORKER_ENTERPRISE' | 'WORKER_BETA';

interface RoutingRule {
  bindingKey: BindingKey;
  weight?: number;           // future: weighted routing
  shadowBinding?: BindingKey; // future: traffic mirroring
}

// In-memory cache; refreshed per isolate lifecycle (typically minutes)
let routingCache: Map<string, RoutingRule> | null = null;
let cacheBuiltAt = 0;
const CACHE_TTL_MS = 30_000;
```

## Routing Table Loader

```typescript
async function loadRoutingTable(env: Env): Promise<Map<string, RoutingRule>> {
  const now = Date.now();
  if (routingCache && now - cacheBuiltAt < CACHE_TTL_MS) {
    return routingCache;
  }

  // KV list pattern: keys prefixed with "route:"
  const listed = await env.ROUTING_TABLE.list({ prefix: 'route:' });

  const table = new Map<string, RoutingRule>();
  await Promise.all(
    listed.keys.map(async ({ name }) => {
      const rule = await env.ROUTING_TABLE.get<RoutingRule>(name, 'json');
      if (rule) {
        const routeKey = name.replace('route:', '');
        table.set(routeKey, rule);
      }
    }),
  );

  routingCache = table;
  cacheBuiltAt = now;
  return table;
}
```

## Content-Based Route Resolution

```typescript
interface RouteContext {
  tenantTier: string;     // "standard" | "premium" | "enterprise"
  betaEnrolled: boolean;
  messageType: string;
}

function resolveRouteKey(ctx: RouteContext): string {
  // Beta always wins
  if (ctx.betaEnrolled) return `beta:${ctx.messageType}`;
  return `${ctx.tenantTier}:${ctx.messageType}`;
}

async function extractRouteContext(req: Request): Promise<RouteContext> {
  const tier = req.headers.get('X-Tenant-Tier') ?? 'standard';
  const beta = req.headers.get('X-Beta-Enrolled') === 'true';

  // Content-based: peek at body for messageType
  const clone = req.clone();
  let messageType = 'default';
  try {
    const body = await clone.json<{ type?: string }>();
    messageType = body.type ?? 'default';
  } catch {
    // Non-JSON body — use default
  }

  return { tenantTier: tier, betaEnrolled: beta, messageType };
}

function selectBinding(
  env: Env,
  rule: RoutingRule,
): Fetcher {
  const dispatch: Record<BindingKey, Fetcher> = {
    WORKER_STANDARD: env.WORKER_STANDARD,
    WORKER_PREMIUM: env.WORKER_PREMIUM,
    WORKER_ENTERPRISE: env.WORKER_ENTERPRISE,
    WORKER_BETA: env.WORKER_BETA,
  };

  const binding = dispatch[rule.bindingKey];
  if (!binding) {
    throw new Error(`No binding registered for key: ${rule.bindingKey}`);
  }
  return binding;
}
```

## Gateway Fetch Handler

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const table = await loadRoutingTable(env);
    const ctx = await extractRouteContext(req);
    const routeKey = resolveRouteKey(ctx);

    const rule = table.get(routeKey) ?? table.get('default:default');

    if (!rule) {
      return new Response(
        JSON.stringify({ error: 'no_route', routeKey }),
        { status: 502, headers: { 'Content-Type': 'application/json' } },
      );
    }

    const target = selectBinding(env, rule);

    // Forward request verbatim to the selected Worker
    const upstream = await target.fetch(req.clone());

    // Optionally shadow to a beta worker in parallel
    if (rule.shadowBinding) {
      const shadow = selectBinding(env, { bindingKey: rule.shadowBinding });
      // Fire-and-forget — don't await, don't affect response
      shadow.fetch(req.clone()).catch((err) => {
        console.error('shadow_failed', { routeKey, err });
      });
    }

    return upstream;
  },
} satisfies ExportedHandler<Env>;
```

## Routing Table Administration API

```typescript
// admin/src/index.ts — secured behind Cloudflare Access
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (req.method === 'PUT' && url.pathname.startsWith('/routes/')) {
      const key = url.pathname.replace('/routes/', '');
      const rule = await req.json<RoutingRule>();
      await env.ROUTING_TABLE.put(`route:${key}`, JSON.stringify(rule));
      return Response.json({ ok: true, key });
    }

    if (req.method === 'DELETE' && url.pathname.startsWith('/routes/')) {
      const key = url.pathname.replace('/routes/', '');
      await env.ROUTING_TABLE.delete(`route:${key}`);
      return Response.json({ ok: true });
    }

    if (req.method === 'GET' && url.pathname === '/routes') {
      const listed = await env.ROUTING_TABLE.list({ prefix: 'route:' });
      const rules = await Promise.all(
        listed.keys.map(async ({ name }) => ({
          key: name.replace('route:', ''),
          rule: await env.ROUTING_TABLE.get<RoutingRule>(name, 'json'),
        })),
      );
      return Response.json(rules);
    }

    return new Response('Not Found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns
- Storing routing rules in module-level constants and redeploying to change them — KV enables live updates without deployment downtime
- Using `fetch()` with HTTP URLs to call backend Workers — service bindings bypass the network entirely and should be used when the target is a Worker in the same account
- Allowing arbitrary binding names from request headers — always resolve binding keys from the trusted routing table, never from untrusted input
- Skipping the fallback `default:default` rule — without a fallback, unknown content types return 502 rather than a sensible default

## Gotchas
- KV `list()` returns at most 1 000 keys per call with `prefix`; paginate with `cursor` for large routing tables
- The in-memory cache (`routingCache`) is per-isolate — different Cloudflare PoPs may have different cached versions for up to `CACHE_TTL_MS`; tolerable for routing but not for security-critical gating
- Service binding calls count against the called Worker's CPU and memory limits, not the gateway's — profile each backend independently
- `req.clone()` buffers the body in memory; for large streamed payloads, parse route context from headers only

## Verification
```bash
# Add a routing rule via admin API
curl -X PUT https://admin.example.com/routes/premium:order.place \
  -H 'Content-Type: application/json' \
  -d '{"bindingKey":"WORKER_PREMIUM"}'

# Verify live routing
curl -X POST https://gateway.example.com/api/orders \
  -H 'X-Tenant-Tier: premium' \
  -H 'Content-Type: application/json' \
  -d '{"type":"order.place","orderId":"ORD-99"}'

# List all routing rules
curl https://admin.example.com/routes
```

## Related
- `api-gateway-pattern-cloudflare-workers.md`
- `worker-to-worker-rpc-service-bindings.md`
- `feature-flag-cloudflare-workers-kv.md`
- `content-negotiation-edge-workers-format-routing.md`
- `dark-launch-traffic-shadowing-workers.md`

## Sources
- https://www.enterpriseintegrationpatterns.com/patterns/messaging/DynamicRouter.html
- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/workers/configuration/bindings/
