# Backends for Frontends (BFF) Pattern with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A single API serves a React web app, an iOS/Android mobile app, and third-party integrations. The web app needs deeply nested, aggregated data in one call. Mobile needs lean payloads to save bandwidth. Third-party partners need stable, versioned contracts. Every change negotiation takes three teams. Response shapes are cluttered with `null` fields for clients that do not use them. Auth mechanisms differ per client but are tangled in one service.

## Context

Sam Newman's Backends for Frontends pattern (2015) addresses this by giving each consumer type its own thin backend service. Each BFF:
- Speaks the language of its frontend (response shape, auth scheme, versioning cadence).
- Aggregates calls to downstream services on behalf of its frontend.
- Is owned by the frontend team, removing cross-team coordination overhead.

Cloudflare Workers are an ideal BFF runtime:
- Deploy in ~30 ms globally, collocated with users.
- Service Bindings allow BFFs to call shared internal Workers with zero network overhead.
- Fine-grained secrets and KV namespaces per Worker isolate auth credentials.
- Worker routes (`/api/web/*`, `/api/mobile/*`) map cleanly to client entry points.

## Solution

### 1. Shared Internal Services (downstream from all BFFs)

```typescript
// services/orders-service/src/index.ts
// Internal Worker — not exposed publicly, only via Service Binding
export interface OrdersEnv {
  DB: D1Database;
}

export interface Order {
  id: string;
  tenantId: string;
  customerId: string;
  status: string;
  lineItems: { sku: string; qty: number; unitPrice: number }[];
  shippingAddress: { line1: string; city: string; country: string };
  createdAt: string;
  updatedAt: string;
}

export default {
  async fetch(request: Request, env: OrdersEnv): Promise<Response> {
    const url = new URL(request.url);
    const tenantId = request.headers.get('X-Tenant-Id') ?? '';

    if (url.pathname === '/orders') {
      const { results } = await env.DB.prepare(
        'SELECT * FROM orders WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 100'
      ).bind(tenantId).all<Order>();
      return Response.json(results);
    }

    const idMatch = url.pathname.match(/^\/orders\/([^/]+)$/);
    if (idMatch) {
      const order = await env.DB.prepare(
        'SELECT * FROM orders WHERE id = ? AND tenant_id = ?'
      ).bind(idMatch[1], tenantId).first<Order>();
      return order ? Response.json(order) : new Response('Not found', { status: 404 });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

### 2. Web BFF — rich aggregated payloads, cookie-based auth

```typescript
// bff/web/src/index.ts
import { verifySessionCookie } from './auth';

export interface WebBffEnv {
  ORDERS_SERVICE: Fetcher;
  CUSTOMERS_SERVICE: Fetcher;
  SESSION_SECRET: string;
  CACHE: KVNamespace;
}

export default {
  async fetch(request: Request, env: WebBffEnv, ctx: ExecutionContext): Promise<Response> {
    // Web auth: session cookie
    const session = await verifySessionCookie(request, env.SESSION_SECRET);
    if (!session) return new Response('Unauthorized', { status: 401 });

    const url = new URL(request.url);

    if (url.pathname === '/api/web/dashboard') {
      return handleWebDashboard(request, session, env, ctx);
    }

    return new Response('Not found', { status: 404 });
  },
};

interface Session { tenantId: string; userId: string; }

async function handleWebDashboard(
  _req: Request,
  session: Session,
  env: WebBffEnv,
  ctx: ExecutionContext
): Promise<Response> {
  // Cache dashboard aggregation for 30 seconds per tenant
  const cacheKey = `web:dashboard:${session.tenantId}`;
  const cached = await env.CACHE.get(cacheKey, 'json') as DashboardPayload | null;
  if (cached) return Response.json(cached);

  const internalHeaders = { 'X-Tenant-Id': session.tenantId };

  // Parallel fetch from internal services
  const [ordersRes, customersRes] = await Promise.all([
    env.ORDERS_SERVICE.fetch(new Request('https://orders/orders', { headers: internalHeaders })),
    env.CUSTOMERS_SERVICE.fetch(new Request('https://customers/customers', { headers: internalHeaders })),
  ]);

  const [orders, customers] = await Promise.all([
    ordersRes.json<Order[]>(),
    customersRes.json<Customer[]>(),
  ]);

  // Web-specific aggregation: enrich orders with customer names
  const customerMap = Object.fromEntries(customers.map((c) => [c.id, c]));
  const payload: DashboardPayload = {
    orders: orders.map((o) => ({
      ...o,
      customerName: customerMap[o.customerId]?.name ?? 'Unknown',
      // Web includes full line items and shipping address
    })),
    summary: {
      totalOrders: orders.length,
      pendingCount: orders.filter((o) => o.status === 'pending').length,
      totalRevenue: orders.flatMap((o) => o.lineItems)
        .reduce((sum, li) => sum + li.qty * li.unitPrice, 0),
    },
  };

  ctx.waitUntil(env.CACHE.put(cacheKey, JSON.stringify(payload), { expirationTtl: 30 }));
  return Response.json(payload);
}

interface Order { id: string; customerId: string; status: string;
  lineItems: { sku: string; qty: number; unitPrice: number }[];
  shippingAddress: object; createdAt: string; }
interface Customer { id: string; name: string; }
interface DashboardPayload { orders: unknown[]; summary: Record<string, number>; }
```

### 3. Mobile BFF — lean payloads, JWT bearer auth, pagination

```typescript
// bff/mobile/src/index.ts
import { verifyJwt } from './auth';

export interface MobileBffEnv {
  ORDERS_SERVICE: Fetcher;
  MOBILE_JWT_SECRET: string; // Different secret from web!
}

export default {
  async fetch(request: Request, env: MobileBffEnv): Promise<Response> {
    // Mobile auth: JWT Bearer
    const token = request.headers.get('Authorization')?.slice(7) ?? '';
    const claims = await verifyJwt(token, env.MOBILE_JWT_SECRET).catch(() => null);
    if (!claims) return new Response('Unauthorized', { status: 401 });

    const url = new URL(request.url);
    if (url.pathname === '/api/mobile/orders') {
      return handleMobileOrders(url, claims, env);
    }
    return new Response('Not found', { status: 404 });
  },
};

async function handleMobileOrders(
  url: URL,
  claims: { tenantId: string; sub: string },
  env: MobileBffEnv
): Promise<Response> {
  const ordersRes = await env.ORDERS_SERVICE.fetch(
    new Request('https://orders/orders', { headers: { 'X-Tenant-Id': claims.tenantId } })
  );
  const orders = await ordersRes.json<Order[]>();

  // Pagination — mobile clients request pages
  const page  = parseInt(url.searchParams.get('page') ?? '1');
  const limit = Math.min(20, parseInt(url.searchParams.get('limit') ?? '10'));
  const start = (page - 1) * limit;
  const page_items = orders.slice(start, start + limit);

  // Lean payload — omit heavy fields unnecessary on mobile
  const slim = page_items.map((o) => ({
    id:        o.id,
    status:    o.status,
    itemCount: o.lineItems.length,
    createdAt: o.createdAt,
    // NO: shippingAddress, full lineItems, customerData
  }));

  return Response.json({
    data:       slim,
    pagination: { page, limit, total: orders.length, hasMore: start + limit < orders.length },
  });
}

type Order = import('../web/src/index').Order;
```

### 4. Third-Party BFF — versioned, stable, API key auth

```typescript
// bff/third-party/src/index.ts
export interface ThirdPartyBffEnv {
  ORDERS_SERVICE: Fetcher;
  API_KEYS: KVNamespace; // key => JSON{ tenantId, scopes[] }
}

export default {
  async fetch(request: Request, env: ThirdPartyBffEnv): Promise<Response> {
    const apiKey = <redacted-secret>'X-API-Key') ?? '';
    const keyData = await env.API_KEYS.get<{ tenantId: string; scopes: string[] }>(
      apiKey, 'json'
    );
    if (!keyData) return new Response('Forbidden', { status: 403 });

    const url = new URL(request.url);

    // Strict version prefix — third-party contracts do not change without a version bump
    const vMatch = url.pathname.match(/^\/v(\d+)\/(.+)$/);
    if (!vMatch) return new Response('Version prefix required', { status: 400 });

    const [, version, path] = vMatch;
    if (version !== '1') return new Response('Only v1 supported', { status: 410 });

    if (path === 'orders') return handleV1Orders(keyData, env);
    return new Response('Not found', { status: 404 });
  },
};

async function handleV1Orders(
  key: { tenantId: string; scopes: string[] },
  env: ThirdPartyBffEnv
): Promise<Response> {
  if (!key.scopes.includes('orders:read')) {
    return new Response('Insufficient scope', { status: 403 });
  }
  const res = await env.ORDERS_SERVICE.fetch(
    new Request('https://orders/orders', { headers: { 'X-Tenant-Id': key.tenantId } })
  );
  const orders = await res.json<Order[]>();

  // Stable v1 schema — only fields third-parties agreed to
  return Response.json(orders.map((o) => ({
    orderId:   o.id,
    status:    o.status,
    createdAt: o.createdAt,
  })));
}

type Order = { id: string; status: string; createdAt: string;
  lineItems: unknown[]; shippingAddress: unknown; customerId: string; updatedAt: string; };
```

### 5. Route Configuration (wrangler.toml)

```toml
# bff/web/wrangler.toml
name = "bff-web"
routes = [{ pattern = "api.example.com/api/web/*", zone_name = "example.com" }]

[[services]]
binding = "ORDERS_SERVICE"
service = "orders-service"

[[services]]
binding = "CUSTOMERS_SERVICE"
service = "customers-service"
```

```toml
# bff/mobile/wrangler.toml
name = "bff-mobile"
routes = [{ pattern = "api.example.com/api/mobile/*", zone_name = "example.com" }]

[[services]]
binding = "ORDERS_SERVICE"
service = "orders-service"
```

```toml
# bff/third-party/wrangler.toml
name = "bff-third-party"
routes = [{ pattern = "api.example.com/v*/*", zone_name = "example.com" }]

[[services]]
binding = "ORDERS_SERVICE"
service = "orders-service"
```

## Implementation Details

- **BFF as sole API contract per frontend**: Each frontend team owns its BFF. They may add, reshape, or remove fields without coordinating with other teams, as long as they do not change the internal service interface.
- **Internal service interface is the stable contract**: Internal Workers (`orders-service`, `customers-service`) are shared; their interface must be versioned carefully. BFFs absorb the shape differences.
- **Auth isolation**: Web, mobile, and third-party use different secrets and auth mechanisms. Each BFF only has access to its own secrets — a compromised mobile JWT key does not affect the web or partner surface.
- **Caching per BFF**: Web dashboard caches aggressively (30 s). Mobile paginates but does not cache (fresh inventory). Third-party is uncached (partners expect real-time). This per-client cache policy is only possible with separate BFFs.
- **Response compression**: Mobile BFF should enable Brotli/gzip via Cloudflare's automatic compression; third-party should return raw JSON for predictability.

## Anti-patterns

- **BFF with business logic**: The BFF aggregates and reshapes; it does not compute prices, apply discounts, or own data. Business logic belongs in internal services.
- **Shared BFF**: One BFF for all clients defeats the purpose. A "BFF for all" is just a gateway.
- **BFF calling BFF**: BFFs should only call internal services, never each other. If you find yourself doing this, the shared logic belongs in an internal service.
- **Putting auth in internal services**: Internal Workers are not publicly reachable, so auth there is redundant overhead. Auth belongs in the BFF.

## Gotchas

- Worker route specificity: `/api/web/*` must be more specific than any catch-all route on the same zone. Check for route conflicts with `wrangler routes list`.
- Service Bindings call the deployed version of an internal service, not the local dev version, unless both are running with `wrangler dev`. Coordinate local dev startup.
- Secrets in one BFF are not visible to others — intentionally. Do not share secrets across BFF Workers; create distinct secret sets.
- Adding a new BFF means a new Worker deployment pipeline. Set up CI/CD per BFF from day one.
- `Promise.all()` in the BFF aggregation will fail if any internal service returns 5xx. Add individual try/catch per service call and return partial data with error flags when appropriate.

## Verification

```bash
# Web BFF — expect enriched dashboard payload with summary
curl https://api.example.com/api/web/dashboard \
  -H 'Cookie: session=<test-session-cookie>' | jq '{orderCount: .summary.totalOrders}'

# Mobile BFF — expect slim paginated list
curl https://api.example.com/api/mobile/orders?page=1&limit=5 \
  -H 'Authorization: Bearer <mobile-jwt>' | jq '{fields: (.data[0] | keys), pagination}'

# Third-party BFF — expect versioned stable schema
curl https://api.example.com/v1/orders \
  -H 'X-API-Key: <partner-key>' | jq '.[0] | keys'
# Expected: ["createdAt", "orderId", "status"] — only v1 fields

# Confirm web BFF does NOT serve mobile route
curl https://api.example.com/api/web/dashboard \
  -H 'Authorization: Bearer <mobile-jwt>' | jq .  # Should return 401
```

## Related

- `workers-sidecar-pattern-service-binding.md`
- `workers-hexagonal-architecture-ports-adapters.md`
- `anti-corruption-layer-legacy.md`
- `workers-cqrs-command-query-separation.md`

## Sources

- Newman, S. (2015). "Pattern: Backends For Frontends". https://samnewman.io/patterns/architectural/bff/
- Richardson, C. *Microservices Patterns*. Manning, 2018.
- Cloudflare Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare Worker Routes: https://developers.cloudflare.com/workers/configuration/routing/routes/
