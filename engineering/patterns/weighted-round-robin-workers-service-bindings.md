# Weighted Round-Robin Load Balancing with Workers Service Bindings

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have multiple backend Workers (or versions of the same Worker) that should receive
traffic in defined proportions — e.g., 70 % stable, 20 % canary, 10 % experimental.
Cloudflare's native Traffic Management splits traffic between Routes, but you need
programmatic control inside a single Worker that fans out to named service bindings
with arbitrary weights, sticky-session semantics, or per-request override headers.

---

## Context

Cloudflare Workers service bindings let one Worker call another via an in-process
`fetch()` that bypasses the public internet. When you hold several bindings you can
choose at runtime which backend handles each request.

Weighted round-robin is a classic load-balancing algorithm: each backend gets a
configurable weight and receives a proportional share of traffic over a sliding window
of requests. Unlike a simple random-percent split, round-robin guarantees exact
proportions over any window that is a multiple of the total weight sum.

Use cases:

- Canary / progressive rollout without touching Route weights in the dashboard.
- A/B backend testing with precise traffic splits.
- Capacity-proportional fan-out across Workers bound to different regions or D1 replicas.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Router Worker                                       │
│                                                      │
│  env.BACKEND_A  (binding to stable Worker)           │
│  env.BACKEND_B  (binding to canary Worker)           │
│  env.BACKEND_C  (binding to experimental Worker)     │
│                                                      │
│  WRR Selector ──────────────────────────────────► backend│
│  (KV counter or Durable Object counter)              │
└─────────────────────────────────────────────────────┘
```

---

## Implementation

### 1. Binding configuration (`wrangler.toml`)

```toml
name = "router"

[[services]]
binding = "BACKEND_A"
service  = "stable-api"

[[services]]
binding = "BACKEND_B"
service  = "canary-api"

[[services]]
binding = "BACKEND_C"
service  = "experimental-api"
```

### 2. Weighted Round-Robin selector (pure, stateless per-request)

A stateless approach uses a virtual position derived from a globally consistent
counter stored in a Durable Object. The selector is O(1).

```typescript
// types.ts
export interface Backend {
  name: string;
  weight: number;   // relative share, e.g. 70 | 20 | 10
  binding: Fetcher; // Workers service binding
}

// wrr.ts
export function selectBackend(backends: Backend[], counter: number): Backend {
  const total = backends.reduce((s, b) => s + b.weight, 0);
  let pos = counter % total;
  for (const b of backends) {
    if (pos < b.weight) return b;
    pos -= b.weight;
  }
  // Fallback — should never reach here if weights are positive integers
  return backends[backends.length - 1];
}
```

### 3. Durable Object — global request counter

```typescript
// RouterState.ts
export class RouterState implements DurableObject {
  private counter = 0;

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/next") {
      const val = this.counter++;
      // Persist only every N requests to reduce writes
      if (this.counter % 50 === 0) {
        await this.ctx.storage.put("counter", this.counter);
      }
      return Response.json({ counter: val });
    }

    if (url.pathname === "/init") {
      const stored = await this.ctx.storage.get<number>("counter") ?? 0;
      this.counter = stored;
      return new Response("ok");
    }

    return new Response("Not found", { status: 404 });
  }
}
```

### 4. Router Worker entry point

```typescript
// index.ts
import { selectBackend, type Backend } from "./wrr";

interface Env {
  BACKEND_A: Fetcher;
  BACKEND_B: Fetcher;
  BACKEND_C: Fetcher;
  ROUTER_STATE: DurableObjectNamespace;
}

const BACKENDS_CONFIG = [
  { name: "stable",       weight: 70 },
  { name: "canary",       weight: 20 },
  { name: "experimental", weight: 10 },
];

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Allow per-request override via header (useful for tests)
    const forceBackend = request.headers.get("X-Force-Backend");

    const bindings: Record<string, Fetcher> = {
      stable:       env.BACKEND_A,
      canary:       env.BACKEND_B,
      experimental: env.BACKEND_C,
    };

    if (forceBackend && bindings[forceBackend]) {
      return bindings[forceBackend].fetch(request);
    }

    // Resolve backends array with live bindings
    const backends: Backend[] = BACKENDS_CONFIG.map(cfg => ({
      ...cfg,
      binding: bindings[cfg.name],
    }));

    // Get the next counter value from the singleton Durable Object
    const id = env.ROUTER_STATE.idFromName("global");
    const stub = env.ROUTER_STATE.get(id);
    const counterRes = await stub.fetch("https://internal/next");
    const { counter } = await counterRes.json<{ counter: number }>();

    const backend = selectBackend(backends, counter);

    // Propagate which backend handled the request for observability
    const upstreamRes = await backend.binding.fetch(request);
    const response = new Response(upstreamRes.body, upstreamRes);
    response.headers.set("X-Served-By", backend.name);
    return response;
  },
};
```

### 5. Smooth degradation — skip unhealthy backends

```typescript
async function selectHealthy(
  backends: Backend[],
  counter: number,
  healthCache: Map<string, boolean>,
): Promise<Backend> {
  const healthyBackends = backends.filter(b => healthCache.get(b.name) !== false);
  if (healthyBackends.length === 0) {
    throw new Error("All backends are unhealthy");
  }
  return selectBackend(healthyBackends, counter);
}
```

Populate `healthCache` from a KV key that a periodic health-check Cron writes, or
consult the sidecar pattern documented in `health-check-sidecar-workers.md`.

---

## Weight Reconfiguration Without Redeployment

Store weights in Workers KV and refresh them on a per-isolate schedule:

```typescript
let cachedWeights: Record<string, number> | null = null;
let weightsCachedAt = 0;
const WEIGHTS_TTL_MS = 30_000;

async function getWeights(env: Env): Promise<Record<string, number>> {
  const now = Date.now();
  if (cachedWeights && now - weightsCachedAt < WEIGHTS_TTL_MS) {
    return cachedWeights;
  }
  const raw = await env.CONFIG_KV.get("wrr:weights", "json");
  cachedWeights = (raw as Record<string, number>) ?? { stable: 70, canary: 20, experimental: 10 };
  weightsCachedAt = now;
  return cachedWeights;
}
```

---

## Anti-patterns

- **Using `Math.random()` for weighted selection** — produces high variance for small
  traffic volumes; a 10 % backend may see 0 % or 25 % over a 100-request burst.
- **One Durable Object stub per request with no locality hint** — always use
  `idFromName("global")` so all requests hit the same shard.
- **Storing the counter in KV** — KV is eventually consistent; two requests can read
  the same counter value in different isolates and send both to the same backend,
  breaking the round-robin guarantee.
- **Blocking on the counter fetch** — if the DO is in a distant PoP the added latency
  can dominate; keep the DO in the same region as the router by using `locationHint`.

---

## Gotchas

- Workers service bindings count as subrequests against the 50-subrequest limit on
  the Workers Free plan. Budget accordingly if you also call external APIs.
- The counter Durable Object serialises all `/next` calls through a single actor.
  At very high RPS the DO becomes a bottleneck. Mitigate by sharding into N counters
  (e.g., `idFromName("shard-" + (Math.random() * N | 0))`) and merging weights
  accordingly.
- A Durable Object evicted from memory loses the in-memory counter. The `/init`
  endpoint restores from storage on cold start; call it before the first `/next`.
- `X-Force-Backend` must be stripped or validated — never forward it downstream
  without checking it comes from a trusted source (internal test harness).

---

## Verification

```bash
# Send 100 requests and count X-Served-By header distribution
for i in $(seq 1 100); do
  curl -s -o /dev/null -w "%header{x-served-by}\n" https://router.example.com/ping
done | sort | uniq -c
# Expected output near:  70 stable  20 canary  10 experimental
```

Unit-test the pure selector:

```typescript
import { selectBackend } from "./wrr";
const backends = [
  { name: "a", weight: 3, binding: null as unknown as Fetcher },
  { name: "b", weight: 1, binding: null as unknown as Fetcher },
];
// counters 0,1,2 → "a"; counter 3 → "b"; counter 4 → "a" again
for (let i = 0; i < 8; i++) {
  console.assert(selectBackend(backends, i).name === (i % 4 < 3 ? "a" : "b"));
}
```

---

## Related

- `health-check-sidecar-workers.md` — feeding live health state to the backend selector
- `scatter-gather-parallel-workers.md` — fan-out rather than fan-in
- `circuit-breaker-workers-d1-fetch.md` — disabling a backend after repeated failures
- `geo-aware-routing-workers.md` — region-aware backend selection

---

## Sources

- Cloudflare Workers Service Bindings docs — developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare Durable Objects — developers.cloudflare.com/durable-objects/
- Nginx Weighted Round-Robin algorithm — nginx.org/en/docs/http/load_balancing.html
