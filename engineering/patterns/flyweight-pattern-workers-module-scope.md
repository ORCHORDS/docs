# Flyweight Pattern: Module-Scope Resource Sharing in Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Workers handler that parses a large JSON configuration file, compiles a set of regular expressions, constructs an OpenAPI validator, or creates a database schema object does this work on every request. Because Workers isolates persist across requests, doing expensive initialisation per-request discards work that could be shared. The handler is slower than necessary, and CPU billing accumulates for work that is logically identical on every call.

Classic signs:
- `JSON.parse(await env.KV.get("config"))` at the top of every `fetch` handler
- Regular expressions constructed inside the handler (`new RegExp(...)`) on each request
- SDK client objects (database clients, S3 clients) recreated for every invocation
- Cold-start latency high, warm-request latency surprisingly similar to cold latency
- Heap allocations climbing linearly with request count instead of staying flat

---

## Context

The Flyweight pattern shares immutable or safely reusable objects among many clients to reduce per-client allocation cost. In the Workers runtime, the isolate persists across requests for the lifetime of the isolate (minutes to hours). Module-scope variables survive across requests within the same isolate. The pattern exploits this: expensive objects are created once on the first request and reused on subsequent requests, amortising initialisation cost across the isolate's lifetime.

```
Request 1 → init()  → [expensive object created] → cached in module scope
Request 2 → init()  → [cache hit] → object returned in <1 µs
Request N → init()  → [cache hit] → same object
```

The critical constraint is that flyweight objects must be **effectively immutable or thread-safe for the Workers single-threaded concurrency model**—they can be read concurrently (between `await` points) but must not be mutated per-request.

---

## Core: Lazy-Init Cache with Async Coalescing

```typescript
// src/flyweight/lazy-resource.ts

type Factory<T> = () => Promise<T>;

interface CachedEntry<T> {
  value: T;
  loadedAt: number;
  ttlMs: number; // 0 = eternal
}

export class LazyResource<T> {
  private cache: CachedEntry<T> | undefined;
  private inflight: Promise<T> | undefined;

  constructor(
    private readonly factory: Factory<T>,
    private readonly ttlMs = 0 // 0 = no expiry
  ) {}

  async get(): Promise<T> {
    const now = Date.now();

    if (this.cache) {
      const expired = this.ttlMs > 0 && now - this.cache.loadedAt > this.ttlMs;
      if (!expired) return this.cache.value;
    }

    // Coalesce concurrent initialisations so the factory runs only once
    if (!this.inflight) {
      this.inflight = this.factory().then((value) => {
        this.cache = { value, loadedAt: Date.now(), ttlMs: this.ttlMs };
        this.inflight = undefined;
        return value;
      });
    }

    return this.inflight;
  }

  /** Force a refresh on the next access (e.g., after a config update). */
  invalidate() {
    this.cache = undefined;
    this.inflight = undefined;
  }
}
```

---

## Flyweight Registry: Multiple Resources by Key

```typescript
// src/flyweight/flyweight-registry.ts
import { LazyResource } from "./lazy-resource";

type Loader<T> = (key: string) => Promise<T>;

export class FlyweightRegistry<T> {
  private instances = new Map<string, LazyResource<T>>();

  constructor(
    private readonly loader: Loader<T>,
    private readonly ttlMs = 0
  ) {}

  get(key: string): LazyResource<T> {
    if (!this.instances.has(key)) {
      this.instances.set(key, new LazyResource(() => this.loader(key), this.ttlMs));
    }
    return this.instances.get(key)!;
  }

  invalidate(key: string) {
    this.instances.get(key)?.invalidate();
  }

  /** Evict keys that haven't been accessed since the start of this isolate (not tracked here).
   *  Call periodically if key space is unbounded. */
  clear() {
    this.instances.clear();
  }
}
```

---

## Concrete Flyweights: Configuration and Compiled Regexes

```typescript
// src/flyweight/resources.ts
import { LazyResource } from "./lazy-resource";
import { FlyweightRegistry } from "./flyweight-registry";
import type { Env } from "../types";

// ── 1. Compiled route-matching regex set ──────────────────────────────────
export const routeRegexCache = new FlyweightRegistry<RegExp>(
  async (pattern) => new RegExp(pattern),
  0 // regexes never expire
);

// ── 2. KV-backed application config (refreshed every 5 minutes) ───────────
let configResource: LazyResource<AppConfig> | undefined;

export interface AppConfig {
  featureFlags: Record<string, boolean>;
  rateLimits: Record<string, number>;
  allowedOrigins: string[];
}

export function getConfigResource(env: Env): LazyResource<AppConfig> {
  if (!configResource) {
    configResource = new LazyResource(
      async () => {
        const raw = await env.KV.get("app:config");
        if (!raw) throw new Error("app:config not found in KV");
        return JSON.parse(raw) as AppConfig;
      },
      5 * 60 * 1000 // 5 minutes
    );
  }
  return configResource;
}

// ── 3. Wasm module (compiled once, instantiated per use) ──────────────────
let wasmModuleResource: LazyResource<WebAssembly.Module> | undefined;

export function getWasmModule(env: Env): LazyResource<WebAssembly.Module> {
  if (!wasmModuleResource) {
    wasmModuleResource = new LazyResource(async () => {
      // Fetch the Wasm binary from a Worker binding or KV
      const bytes = await env.KV.get("wasm:validator", "arrayBuffer");
      if (!bytes) throw new Error("Wasm binary not found");
      return WebAssembly.compile(bytes);
    });
  }
  return wasmModuleResource;
}
```

---

## Worker: Using Module-Scope Flyweights

```typescript
// src/worker.ts
import type { Env } from "./types";
import { getConfigResource, routeRegexCache } from "./flyweight/resources";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // ── Config: loaded once per isolate, refreshed every 5 minutes ──
    const config = await getConfigResource(env).get();

    const origin = request.headers.get("Origin") ?? "";
    if (origin && !config.allowedOrigins.includes(origin)) {
      return new Response("Forbidden", { status: 403 });
    }

    // ── Regex: compiled once per pattern string, then cached ──
    const path = new URL(request.url).pathname;
    const adminRouteRegex = await routeRegexCache.get("^/admin/").get();
    const isAdmin = adminRouteRegex.test(path);

    if (isAdmin && !config.featureFlags["admin_access"]) {
      return new Response("Feature disabled", { status: 403 });
    }

    // ── Wasm: compile once, instantiate cheaply on each request ──
    // (instantiating a pre-compiled module is ~10× cheaper than compiling)
    // const wasmModule = await getWasmModule(env).get();
    // const instance = await WebAssembly.instantiate(wasmModule, {});

    return Response.json({
      path,
      isAdmin,
      featureFlags: config.featureFlags,
    });
  },
};
```

---

## Invalidation via a Webhook or Queue Consumer

```typescript
// src/invalidation-worker.ts
import type { Env } from "./types";
import { getConfigResource } from "./flyweight/resources";

// Called when config is updated in KV; invalidates the local cache
// so the next request fetches fresh data.
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === "POST" && new URL(request.url).pathname === "/invalidate-config") {
      getConfigResource(env).invalidate();
      return new Response(null, { status: 204 });
    }
    return new Response("Not found", { status: 404 });
  },
};
```

---

## Testing LazyResource

```typescript
// src/flyweight/__tests__/lazy-resource.test.ts
import { describe, it, expect, vi } from "vitest";
import { LazyResource } from "../lazy-resource";

it("calls factory only once for concurrent gets", async () => {
  const factory = vi.fn().mockResolvedValue({ value: 42 });
  const resource = new LazyResource(factory);

  const [a, b, c] = await Promise.all([resource.get(), resource.get(), resource.get()]);
  expect(factory).toHaveBeenCalledTimes(1);
  expect(a).toBe(b);
  expect(b).toBe(c);
});

it("refreshes after TTL expiry", async () => {
  vi.useFakeTimers();
  let count = 0;
  const factory = vi.fn().mockImplementation(async () => ({ n: ++count }));
  const resource = new LazyResource(factory, 1000);

  const first = await resource.get();
  expect(first.n).toBe(1);

  vi.advanceTimersByTime(1001);
  const second = await resource.get();
  expect(second.n).toBe(2);
  expect(factory).toHaveBeenCalledTimes(2);
  vi.useRealTimers();
});

it("invalidate forces refetch", async () => {
  const factory = vi.fn().mockResolvedValue("new-value");
  const resource = new LazyResource(factory);
  await resource.get();
  resource.invalidate();
  await resource.get();
  expect(factory).toHaveBeenCalledTimes(2);
});
```

---

## Anti-patterns

- **Storing per-request state in module-scope variables**: Module scope is shared across all concurrent requests in the isolate. Writing `currentUser = ...` at module scope causes request-to-request data leaks. Flyweights must be immutable or otherwise safe to share.
- **Caching objects that hold a network socket or mutable cursor**: Database connections and streaming responses maintain open sockets. Workers cannot keep these alive across requests; cache stateless factories or configurations, not live connections.
- **Never invalidating config flyweights**: KV-backed config with TTL = 0 will serve stale values for the entire isolate lifetime (potentially hours). Set a TTL appropriate to how quickly config changes must propagate.
- **Ignoring the `inflight` coalescing**: Without coalescing, the first 10 concurrent requests on a cold isolate each spawn a separate factory invocation (e.g., 10 KV reads). The `inflight` promise ensures only one executes.
- **Unbounded `FlyweightRegistry` key space**: If keys are derived from user input (e.g., tenant IDs × resource types), the registry map can grow until OOM. Add a size cap with LRU eviction or scope the registry to a fixed key set.

---

## Gotchas

- Workers isolates are evicted after ~30 seconds of inactivity or after hitting memory limits. After eviction, the next request is a cold start; the module-scope cache is empty and the factory re-runs. Design around this: cold-start latency should be acceptable even on every request.
- `WebAssembly.compile` is relatively expensive. Once compiled, the `WebAssembly.Module` object can be instantiated cheaply per-request. Never store a `WebAssembly.Instance` in module scope—instances have mutable linear memory that is not safe to share across requests.
- KV `get` in Workers is not free: each call consumes ~1 ms and counts against KV read units. A TTL of 5 minutes means at most 1 KV read per 5 minutes per isolate instead of 1 per request—often a 10 000× reduction at steady state.
- Module-scope variables are **not** shared across different isolate instances (e.g., running in different PoPs or after an isolate restart). The flyweight cache is per-isolate, not global. Treat it as an in-process cache, not a distributed cache.
- If the factory throws (e.g., KV unavailable), `this.inflight` is cleared and `this.cache` remains undefined. The next call will attempt the factory again. This is correct—transient failures should not permanently poison the cache.

---

## Verification

1. Add a `console.log("factory called")` inside the config factory; verify it fires once per cold start, not once per request, during a load test.
2. Update the KV value and wait for the TTL to expire; verify the next request returns the updated config without a restart.
3. Call `/invalidate-config`; verify the next request triggers a factory call even before the TTL expires.
4. Run the `LazyResource` unit tests with fake timers; confirm TTL expiry triggers exactly one new factory call regardless of concurrency.
5. Use `wrangler dev` memory metrics to confirm heap allocation is flat across 1 000 requests after the warm-up request.

---

## Related

- `lazy-init-module-cache-workers.md` — the original module-cache pattern for single-value resources
- `cache-aside-kv-d1-fallback.md` — KV as a shared (cross-isolate) cache when module scope is insufficient
- `proxy-pattern-workers-service-binding-auth.md` — module-scope `TokenStore` is itself a flyweight
- `build-time-vs-runtime.md` — when to bake config into the Worker bundle vs. fetch at runtime

---

## Sources

- Gamma et al. — Design Patterns: Elements of Reusable Object-Oriented Software (1994): Flyweight
- Cloudflare Workers isolate lifecycle: https://developers.cloudflare.com/workers/reference/how-workers-works/
- Workers KV read limits and pricing: https://developers.cloudflare.com/kv/platform/limits/
- WebAssembly in Workers: https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- Cloudflare Workers memory limits: https://developers.cloudflare.com/workers/platform/limits/#memory
