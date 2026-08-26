# Proxy Pattern with Workers Service Binding Abstraction

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Downstream Workers change their API surface frequently — response shapes shift, auth
schemes rotate, new rate-limit headers appear — and every caller must absorb each change
independently. Alternatively, you need to add cross-cutting concerns (auth, logging,
caching, schema validation, circuit breaking) to an internal service without modifying
it. A Proxy Worker sits between callers and the target, presenting a stable contract to
callers while encapsulating all adaptation logic in one place.

## Context

Cloudflare Service Bindings let one Worker call another over an in-process channel with
zero network latency — no TCP handshake, no TLS, no egress billing. A Proxy Worker
exploits this by exposing a stable `Request → Response` interface to upstream callers
via a service binding while itself holding a binding to the downstream service. Callers
know only the proxy's contract; the proxy knows both contracts and bridges the gap.
This maps to the classic GoF Proxy and Adapter patterns applied to the edge.

## 1. Downstream Service (Target)

```typescript
// src/downstream-worker.ts  (the "real subject")
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    // Internal v2 schema — callers should not depend on this directly
    if (url.pathname === "/internal/prices") {
      return Response.json({
        schemaVersion: 2,
        items: [{ sku: "ABC", priceMinorUnits: 1999, currency: "USD" }],
      });
    }
    return new Response("not found", { status: 404 });
  },
};
```

## 2. Proxy Worker — Contract Translation

```typescript
// src/proxy-worker.ts  (the "proxy")
interface StablePrice {
  sku: string;
  price: number;   // dollars, not minor units
  currency: string;
}

interface DownstreamV2Response {
  schemaVersion: number;
  items: Array<{ sku: string; priceMinorUnits: number; currency: string }>;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    // --- Cross-cutting: auth ---
    const apiKey = <redacted-secret>"x-api-key");
    if (apiKey !== env.EXPECTED_API_KEY) {
      return new Response("Unauthorized", { status: 401 });
    }

    // --- Route mapping: stable public path → internal path ---
    if (url.pathname === "/prices") {
      return this.getPrices(env);
    }

    return new Response("Not found", { status: 404 });
  },

  async getPrices(env: Env): Promise<Response> {
    // --- Forward to downstream via service binding ---
    const downstream = await env.DOWNSTREAM.fetch(
      new Request("https://internal/internal/prices")
    );

    if (!downstream.ok) {
      return new Response("upstream error", { status: 502 });
    }

    const raw = await downstream.json<DownstreamV2Response>();

    // --- Schema adaptation: v2 → stable public shape ---
    const prices: StablePrice[] = raw.items.map((item) => ({
      sku: item.sku,
      price: item.priceMinorUnits / 100,
      currency: item.currency,
    }));

    // --- Cross-cutting: cache headers ---
    return Response.json(prices, {
      headers: { "Cache-Control": "s-maxage=30", "X-Proxy": "prices-v1" },
    });
  },
};
```

## 3. Adding Circuit Breaker Cross-cutting Concern

```typescript
// src/proxy-worker.ts  (extended with circuit breaker via KV)
async function withCircuitBreaker(
  env: Env,
  key: string,
  fn: () => Promise<Response>
): Promise<Response> {
  const state = (await env.CB_STATE.get(key)) ?? "closed";

  if (state === "open") {
    return new Response("Service unavailable (circuit open)", { status: 503 });
  }

  try {
    const resp = await fn();
    if (!resp.ok) throw new Error(`upstream ${resp.status}`);
    // Reset failure count on success
    await env.CB_STATE.put(`${key}:failures`, "0");
    return resp;
  } catch (err) {
    const failures = Number(await env.CB_STATE.get(`${key}:failures`) ?? 0) + 1;
    await env.CB_STATE.put(`${key}:failures`, String(failures));
    if (failures >= 5) {
      // Trip the breaker for 60 seconds
      await env.CB_STATE.put(key, "open", { expirationTtl: 60 });
    }
    return new Response("upstream error", { status: 502 });
  }
}

// Usage inside getPrices:
// return withCircuitBreaker(env, "prices-cb", () => env.DOWNSTREAM.fetch(...));
```

## 4. Request/Response Logging Cross-cutting Concern

```typescript
// src/proxy-worker.ts  (extended with structured logging)
async function loggingProxy(
  req: Request,
  env: Env,
  handler: (req: Request, env: Env) => Promise<Response>
): Promise<Response> {
  const start = Date.now();
  const requestId = crypto.randomUUID();

  let status = 0;
  try {
    const resp = await handler(req, env);
    status = resp.status;
    return resp;
  } finally {
    // Workers tail handlers pick this up for Logpush
    console.log(
      JSON.stringify({
        requestId,
        path: new URL(req.url).pathname,
        method: req.method,
        status,
        durationMs: Date.now() - start,
      })
    );
  }
}
```

## 5. Wrangler Configuration

```toml
# proxy-worker/wrangler.toml
name = "prices-proxy"

[[services]]
binding = "DOWNSTREAM"
service = "prices-downstream-worker"

[[kv_namespaces]]
binding = "CB_STATE"
id = "<KV_NAMESPACE_ID>"

[vars]
EXPECTED_API_KEY = "changeme"
```

```jsonc
// If using wrangler.jsonc instead:
{
  "name": "prices-proxy",
  "services": [{ "binding": "DOWNSTREAM", "service": "prices-downstream-worker" }],
  "kv_namespaces": [{ "binding": "CB_STATE", "id": "<KV_NAMESPACE_ID>" }]
}
```

## Anti-patterns

- **Proxy does business logic**: the proxy's sole job is contract adaptation and cross-
  cutting concerns — pricing rules, discounts, and inventory checks belong in the
  downstream or a dedicated domain Worker.
- **Passing raw downstream responses unchanged**: callers then depend on the downstream
  schema, negating the abstraction.
- **One proxy serving many unrelated services**: a mega-proxy becomes a God Worker; keep
  proxies domain-scoped (e.g. `prices-proxy`, `inventory-proxy`).
- **Bypassing the proxy with direct service bindings**: if callers can bind to the
  downstream directly, the proxy is vestigial and will drift out of sync.
- **Stateful circuit breaker in Worker memory**: state lives only for the lifetime of
  the isolate; persist circuit-breaker state in KV or a DO.

## Gotchas

- Service bindings consume the called Worker's CPU quota, not the caller's — monitor
  both Workers for quota exhaustion independently.
- `env.DOWNSTREAM.fetch()` does not follow redirects by default; if the downstream
  returns 3xx, the proxy must handle or forward it explicitly.
- Service binding requests do not go through Cloudflare's network stack — no cache, no
  Smart Routing; the proxy must add `Cache-Control` headers itself for CF caching.
- Schema adaptation is a maintenance surface: add contract tests that fail the proxy CI
  pipeline when the downstream response shape changes unexpectedly.

## Verification

```bash
# Happy path
curl -H "x-api-key: changeme" https://prices-proxy.example.com/prices
# Expected: [{"sku":"ABC","price":19.99,"currency":"USD"}]

# Auth guard
curl https://prices-proxy.example.com/prices
# Expected: 401 Unauthorized

# Circuit open: simulate 5 upstream failures, then
curl -H "x-api-key: changeme" https://prices-proxy.example.com/prices
# Expected: 503 Service unavailable (circuit open)
```

## Related

- `worker-to-worker-rpc-service-bindings.md`
- `anti-corruption-layer.md`
- `circuit-breaker-kv-state-machine.md`
- `adapter-pattern-integration.md`
- `sidecar-pattern.md`

## Sources

- Cloudflare Workers Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- GoF Design Patterns — Gamma et al., *Proxy* (p. 207) and *Adapter* (p. 139)
- Martin Fowler, *Patterns of Enterprise Application Architecture* — Remote Facade (p. 388)
- Cloudflare KV TTL for ephemeral state — https://developers.cloudflare.com/kv/api/write-key-value-pairs/
