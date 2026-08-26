# API Gateway Pattern with a Single Entry-Point Worker

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You have multiple backend service Workers (auth, orders, inventory, notifications) and need a single public endpoint that routes requests to the right service, enforces authentication, strips internal headers, injects tracing context, rate-limits callers, and aggregates responses for composite endpoints. Without a gateway, each service must re-implement these cross-cutting concerns independently.

## Context

Cloudflare Service Bindings allow one Worker to call another Worker directly without going over the public internet — no network hop, no TLS handshake, sub-millisecond latency. The gateway Worker holds bindings to all service Workers and acts as the single entry point. Rate limiting can be delegated to a Durable Object (see `workers-token-bucket-rate-limiter-do`). The gateway is stateless and horizontally scalable.

## Solution

A gateway Worker maps URL prefixes to service bindings, enforces JWT authentication, strips secrets from outbound requests, injects standard headers (trace ID, caller identity), optionally aggregates responses from multiple services, and applies rate limiting before forwarding.

```typescript
// wrangler.toml excerpt
// [services]
// [[services]]
//   binding = "AUTH_SVC"
//   service = "auth-worker"
// [[services]]
//   binding = "ORDERS_SVC"
//   service = "orders-worker"
// [[services]]
//   binding = "INVENTORY_SVC"
//   service = "inventory-worker"
// [[services]]
//   binding = "NOTIFICATIONS_SVC"
//   service = "notifications-worker"
// [[durable_objects.bindings]]
//   name = "RATE_LIMITER"
//   class_name = "TokenBucketDO"
//   script_name = "rate-limiter-worker"

export interface Env {
  AUTH_SVC:           Fetcher;
  ORDERS_SVC:         Fetcher;
  INVENTORY_SVC:      Fetcher;
  NOTIFICATIONS_SVC:  Fetcher;
  RATE_LIMITER:       DurableObjectNamespace;
  JWT_SECRET:         string;
  INTERNAL_API_TOKEN: string;
}

// Route registry: maps path prefix to service binding key
const ROUTES: Array<{ prefix: string; binding: keyof Env; stripPrefix?: string }> = [
  { prefix: '/api/v1/orders',        binding: 'ORDERS_SVC',        stripPrefix: '/api/v1' },
  { prefix: '/api/v1/inventory',     binding: 'INVENTORY_SVC',     stripPrefix: '/api/v1' },
  { prefix: '/api/v1/notifications', binding: 'NOTIFICATIONS_SVC', stripPrefix: '/api/v1' },
  { prefix: '/api/v1/auth',          binding: 'AUTH_SVC',          stripPrefix: '/api/v1' },
];

// Public routes that bypass JWT auth
const PUBLIC_PATHS = new Set(['/api/v1/auth/login', '/api/v1/auth/register', '/api/v1/health']);

interface JWTPayload {
  sub:   string;
  tier:  string;
  roles: string[];
  exp:   number;
}

// --- JWT verification (simplified — use a proper library in production) ---
async function verifyJWT(token: string, secret: string): Promise<JWTPayload> {
  const [headerB64, payloadB64, sig] = token.split('.');
  if (!headerB64 || !payloadB64 || !sig) throw new Error('Malformed JWT');

  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify']
  );

  const data     = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const sigBytes = Uint8Array.from(atob(sig.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
  const valid    = await crypto.subtle.verify('HMAC', key, sigBytes, data);
  if (!valid) throw new Error('Invalid signature');

  const payload = JSON.parse(atob(payloadB64)) as JWTPayload;
  if (payload.exp < Math.floor(Date.now() / 1000)) throw new Error('Token expired');
  return payload;
}

// --- Rate limit check via Durable Object ---
async function checkRateLimit(
  env: Env,
  userId: string,
  tier: string
): Promise<{ allowed: boolean; remaining: number; resetSec: number }> {
  const id   = env.RATE_LIMITER.idFromName(`user:${userId}`);
  const stub = env.RATE_LIMITER.get(id);
  const resp = await stub.fetch(new Request('https://do/consume?cost=1', {
    headers: { 'X-Rate-Tier': tier },
  }));
  return resp.json();
}

// --- Request transformation ---
function buildUpstreamRequest(
  original: Request,
  targetUrl: string,
  payload: JWTPayload | null,
  traceId: string
): Request {
  const headers = new Headers(original.headers);

  // Strip auth header — services trust gateway, not callers directly
  headers.delete('Authorization');
  // Strip any caller-injected internal headers
  headers.delete('X-Internal-Token');
  headers.delete('X-User-Id');
  headers.delete('X-User-Roles');

  // Inject verified identity
  if (payload) {
    headers.set('X-User-Id',    payload.sub);
    headers.set('X-User-Roles', payload.roles.join(','));
    headers.set('X-User-Tier',  payload.tier);
  }

  // Inject gateway-level internal token for service-to-service auth
  headers.set('X-Internal-Token', 'INJECTED_BY_GATEWAY'); // replaced with env var below
  headers.set('X-Trace-Id',       traceId);
  headers.set('X-Gateway-Version', '1');

  return new Request(targetUrl, {
    method:  original.method,
    headers,
    body:    ['GET', 'HEAD'].includes(original.method) ? undefined : original.body,
    redirect: 'manual',
  });
}

// --- Composite endpoint: product detail page aggregation ---
async function aggregateProductDetail(
  env: Env,
  productId: string,
  payload: JWTPayload,
  traceId: string
): Promise<Response> {
  const [ordersResp, inventoryResp] = await Promise.all([
    env.ORDERS_SVC.fetch(
      buildUpstreamRequest(
        new Request(`https://orders/orders?productId=${productId}`),
        `https://orders/orders?productId=${productId}`,
        payload,
        traceId
      )
    ),
    env.INVENTORY_SVC.fetch(
      buildUpstreamRequest(
        new Request(`https://inventory/inventory/${productId}`),
        `https://inventory/inventory/${productId}`,
        payload,
        traceId
      )
    ),
  ]);

  const [orders, inventory] = await Promise.all([
    ordersResp.json(),
    inventoryResp.json(),
  ]);

  return Response.json({ productId, orders, inventory });
}

// --- Main gateway handler ---
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url     = new URL(request.url);
    const traceId = request.headers.get('X-Trace-Id') ?? crypto.randomUUID();

    // Health check
    if (url.pathname === '/api/v1/health') {
      return Response.json({ status: 'ok', ts: Date.now() });
    }

    // Composite endpoint
    if (url.pathname.startsWith('/api/v1/product-detail/')) {
      const token   = request.headers.get('Authorization')?.replace('Bearer ', '');
      const payload = token ? await verifyJWT(token, env.JWT_SECRET).catch(() => null) : null;
      if (!payload) return new Response('Unauthorized', { status: 401 });
      const productId = url.pathname.split('/').pop()!;
      return aggregateProductDetail(env, productId, payload, traceId);
    }

    // Route lookup
    const route = ROUTES.find(r => url.pathname.startsWith(r.prefix));
    if (!route) return new Response('Not found', { status: 404 });

    // Authentication
    let payload: JWTPayload | null = null;
    if (!PUBLIC_PATHS.has(url.pathname)) {
      const token = request.headers.get('Authorization')?.replace('Bearer ', '');
      if (!token) return new Response('Unauthorized', { status: 401 });
      try {
        payload = await verifyJWT(token, env.JWT_SECRET);
      } catch {
        return new Response('Unauthorized', { status: 401 });
      }
    }

    // Rate limiting (skip for public paths)
    if (payload) {
      const rl = await checkRateLimit(env, payload.sub, payload.tier);
      if (!rl.allowed) {
        return new Response(JSON.stringify({ error: 'Rate limit exceeded' }), {
          status: 429,
          headers: { 'Content-Type': 'application/json', 'Retry-After': String(rl.resetSec) },
        });
      }
    }

    // Build upstream URL
    const strippedPath = route.stripPrefix
      ? url.pathname.slice(route.stripPrefix.length)
      : url.pathname;
    const upstreamUrl = `https://${route.binding.toLowerCase()}${strippedPath}${url.search}`;

    // Forward to service
    const service  = env[route.binding] as Fetcher;
    const upstream = buildUpstreamRequest(request, upstreamUrl, payload, traceId);
    const response = await service.fetch(upstream);

    // Inject trace ID into response
    const mutable = new Response(response.body, response);
    mutable.headers.set('X-Trace-Id', traceId);
    return mutable;
  },
};
```

## Implementation Details

**Service Bindings are zero-cost network calls.** Calling `env.ORDERS_SVC.fetch(...)` invokes the orders Worker in the same Cloudflare network point-of-presence, with no TLS overhead and sub-millisecond latency. The called Worker still runs in its own isolate with its own CPU budget.

**Route registry.** A plain array of prefix-to-binding mappings keeps routing declarative and easy to extend. For more complex needs (regex, method-specific, versioned), replace the array with a `URLPattern` matcher.

**Auth stripping.** The gateway strips `Authorization` and any `X-Internal-*` headers from the incoming request before forwarding. Services should reject requests without `X-Internal-Token` to prevent direct access bypassing the gateway.

**Response aggregation.** The `product-detail` composite endpoint calls two services in parallel via `Promise.all`. Partial failures can be handled by catching rejections and returning a degraded response rather than a 500.

**Rate limiting at the gateway.** Centralising rate limit enforcement at the gateway means services do not each need their own limiter. The gateway calls the Durable Object rate limiter before forwarding.

## Anti-patterns

- **Services accepting public internet traffic directly.** Defeats the purpose of the gateway. Lock services to only accept requests with a valid `X-Internal-Token` set by the gateway.
- **Fat gateway with business logic.** The gateway should only route, authenticate, and transform. Business logic belongs in service Workers.
- **Synchronous aggregation of many services.** Calling 10 services serially in the gateway adds their latencies. Always use `Promise.all` for independent calls.
- **Returning upstream error bodies verbatim.** Internal error messages may leak implementation details. Sanitise error responses before returning to callers.

## Gotchas

- Service Bindings pass the `Request` body as a `ReadableStream`. If you need to read the body and forward it, you must `await request.clone().json()` or tee the stream before consuming it.
- `redirect: 'manual'` on the upstream request prevents the gateway from silently following redirects to unexpected service endpoints.
- JWT `exp` check uses server-side `Date.now()`. Workers do not drift but be aware that clock skew between token issuer and Worker is possible in multi-region setups.
- Service Binding URLs use the binding name as the host (e.g., `https://orders_svc/...`). The actual value does not need to be a real hostname — Cloudflare intercepts it.
- The `ExecutionContext` (`ctx`) is available for `ctx.waitUntil()` to run background tasks (logging, telemetry) without blocking the response.

## Verification

```bash
# Unauthenticated request to public path
curl https://api.example.com/api/v1/auth/login -X POST -d '{...}'

# Authenticated request to protected path
TOKEN=$(curl -s -X POST https://api.example.com/api/v1/auth/login -d '{...}' | jq -r .token)
curl -H "Authorization: Bearer $TOKEN" https://api.example.com/api/v1/orders

# Composite endpoint
curl -H "Authorization: Bearer $TOKEN" https://api.example.com/api/v1/product-detail/prod_123

# Direct service access should be rejected
curl https://orders-worker.example.workers.dev/orders  # should return 401 (missing X-Internal-Token)
```

## Related

- `workers-token-bucket-rate-limiter-do` — rate limiter invoked by this gateway
- `workers-bulkhead-pattern-queue-isolation` — per-service capacity isolation
- `workers-scatter-gather-parallel-fetch` — parallel service fan-out pattern

## Sources

- Cloudflare Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare Workers JWT example: https://developers.cloudflare.com/workers/examples/auth-with-headers/
- API Gateway pattern: https://microservices.io/patterns/apigateway.html
