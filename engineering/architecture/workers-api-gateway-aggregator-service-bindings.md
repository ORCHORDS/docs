# API Gateway Aggregator Pattern with Cloudflare Workers Service Bindings

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have multiple downstream Workers (auth, inventory, pricing, recommendations) and need a single entry-point that fans out requests, aggregates responses, and returns a unified payload to the client. Without an aggregator, clients must make N parallel fetches, leaking internal service topology and inflating latency on slow connections.

## Context

- Runtime: Cloudflare Workers (ES2022 module syntax)
- Interconnect: Service Bindings (zero-latency, same-datacenter RPC — no HTTP round-trip)
- Language: TypeScript 5.x
- Storage: none required at gateway layer; downstream Workers own their data
- Deploy target: `wrangler deploy` with `[[services]]` bindings declared in `wrangler.toml`

---

## 1. wrangler.toml — Declare Service Bindings

```toml
name = "api-gateway"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[services]]
binding = "AUTH_SERVICE"
service = "auth-worker"

[[services]]
binding = "INVENTORY_SERVICE"
service = "inventory-worker"

[[services]]
binding = "PRICING_SERVICE"
service = "pricing-worker"

[[services]]
binding = "RECOMMENDATIONS_SERVICE"
service = "recommendations-worker"
```

---

## 2. Environment Interface

```typescript
// src/types.ts
export interface Env {
  AUTH_SERVICE: Fetcher;
  INVENTORY_SERVICE: Fetcher;
  PRICING_SERVICE: Fetcher;
  RECOMMENDATIONS_SERVICE: Fetcher;
}

export interface AuthResult {
  userId: string;
  roles: string[];
  valid: boolean;
}

export interface ProductPayload {
  productId: string;
  stock: number;
  price: number;
  currency: string;
  recommendations: string[];
}
```

---

## 3. Route Table

```typescript
// src/router.ts
import { Env } from "./types";

type RouteHandler = (req: Request, env: Env) => Promise<Response>;

const routes: Map<string, RouteHandler> = new Map();

export function register(pattern: string, handler: RouteHandler): void {
  routes.set(pattern, handler);
}

export function match(pathname: string): RouteHandler | undefined {
  // Exact match first, then prefix match
  if (routes.has(pathname)) return routes.get(pathname);
  for (const [pattern, handler] of routes) {
    if (pathname.startsWith(pattern)) return handler;
  }
  return undefined;
}
```

---

## 4. Aggregator Handler — Product Detail Page

```typescript
// src/handlers/product.ts
import { Env, AuthResult, ProductPayload } from "../types";

/**
 * Aggregates auth validation + inventory + pricing + recommendations
 * in parallel using service bindings.  All calls are in-process
 * (same isolate network) so latency is sub-millisecond per hop.
 */
export async function handleProductDetail(
  req: Request,
  env: Env
): Promise<Response> {
  const url = new URL(req.url);
  const productId = url.searchParams.get("id");
  if (!productId) {
    return Response.json({ error: "Missing product id" }, { status: 400 });
  }

  // 1. Authenticate — fail fast before expensive downstream calls
  const authResp = await env.AUTH_SERVICE.fetch(
    new Request("https://auth/validate", {
      method: "POST",
      headers: { authorization: req.headers.get("authorization") ?? "" },
    })
  );
  if (!authResp.ok) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }
  const auth: AuthResult = await authResp.json();

  // 2. Fan out to remaining services in parallel
  const [inventoryResp, pricingResp, recommendationsResp] = await Promise.all([
    env.INVENTORY_SERVICE.fetch(
      `https://inventory/product/${productId}`
    ),
    env.PRICING_SERVICE.fetch(
      `https://pricing/product/${productId}?currency=USD`
    ),
    env.RECOMMENDATIONS_SERVICE.fetch(
      `https://recommendations/for/${productId}?userId=${auth.userId}`
    ),
  ]);

  // 3. Merge — surface partial data on non-critical failures
  const [inventory, pricing, recommendations] = await Promise.all([
    inventoryResp.ok ? inventoryResp.json<{ stock: number }>() : { stock: -1 },
    pricingResp.ok
      ? pricingResp.json<{ price: number; currency: string }>()
      : { price: 0, currency: "USD" },
    recommendationsResp.ok
      ? recommendationsResp.json<{ ids: string[] }>()
      : { ids: [] },
  ]);

  const payload: ProductPayload = {
    productId,
    stock: (inventory as { stock: number }).stock,
    price: (pricing as { price: number; currency: string }).price,
    currency: (pricing as { price: number; currency: string }).currency,
    recommendations: (recommendations as { ids: string[] }).ids,
  };

  return Response.json(payload, {
    headers: { "cache-control": "private, max-age=30" },
  });
}
```

---

## 5. Entry-point Worker

```typescript
// src/index.ts
import { Env } from "./types";
import { match } from "./router";
import { handleProductDetail } from "./handlers/product";
import { register } from "./router";

register("/api/product", handleProductDetail);

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const { pathname } = new URL(req.url);
    const handler = match(pathname);
    if (!handler) {
      return Response.json({ error: "Not found" }, { status: 404 });
    }
    try {
      return await handler(req, env);
    } catch (err) {
      console.error("Gateway error", err);
      return Response.json({ error: "Internal server error" }, { status: 500 });
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- **Sequential downstream calls**: never `await` each service call one-by-one when calls are independent — use `Promise.all`.
- **Passing raw `Request` objects between Workers without cloning**: a consumed body cannot be re-read; clone when body is needed by multiple services.
- **Leaking internal service URLs to clients**: the gateway is the contract boundary — never forward raw upstream error bodies with internal hostnames.
- **Fat gateway with business logic**: the gateway should route and merge, not implement rules. Keep domain logic in downstream Workers.
- **Ignoring partial failure**: `Promise.allSettled` or individual `ok` checks prevent one flaky service from killing the whole response.

## Gotchas

- Service bindings use the Worker's `name` in `wrangler.toml`, not its custom domain — mismatches cause silent 503s in `wrangler dev`.
- In local dev (`wrangler dev`), bound Workers must also be running locally; use `--local` flag on each or `wrangler dev --services` multi-worker mode.
- `ctx.waitUntil` is available on the gateway's `ExecutionContext` but not propagated into bound service calls — fire-and-forget logging must happen in the gateway itself.
- Response bodies from service bindings are streaming; call `.json()` or `.text()` exactly once, or clone before reading.
- Service binding calls count toward the gateway's CPU time budget (50 ms free tier, 30 s paid), not a separate budget per downstream Worker.

## Verification

```bash
# Start all Workers locally
wrangler dev --config wrangler.auth.toml &
wrangler dev --config wrangler.inventory.toml &
wrangler dev --config wrangler.pricing.toml &
wrangler dev --config wrangler.recommendations.toml &
wrangler dev --config wrangler.gateway.toml

# Smoke test aggregated endpoint
curl -s -H 'Authorization: Bearer test-token' \
  'http://localhost:8787/api/product?id=prod_001' | jq .

# Expect: { productId, stock, price, currency, recommendations: [...] }
```

## Related

- `documentation/categories/architecture/workers-decorator-pattern-middleware-chain.md`
- `documentation/categories/architecture/workers-observer-pattern-queues-fanout.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/workers/configuration/routing/
- https://developers.cloudflare.com/workers/platform/limits/
