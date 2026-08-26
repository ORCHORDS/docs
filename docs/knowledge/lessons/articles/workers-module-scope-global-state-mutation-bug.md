# Workers Module Scope Global State Mutation Bug

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker that handles multi-tenant API requests began returning
stale or cross-contaminated configuration data to tenants after periods of
high traffic. Under low load the bug disappeared. A cache warm-up object
declared at module scope was being mutated inside request handlers, causing
values set by one request to leak into subsequent requests served by the same
isolate instance.

---

## Context

Cloudflare Workers run inside V8 isolates. An isolate is created when a script
is first loaded and may be reused across many requests on the same edge node.
Variables declared at module scope — outside any handler function — persist for
the lifetime of that isolate. This is unlike traditional serverless platforms
that guarantee a fresh execution context per invocation.

The Workers runtime does **not** guarantee a fresh isolate per request. It
does not guarantee that requests are serialized either; multiple in-flight
requests can share the same isolate simultaneously when using service bindings
or when the runtime decides to reuse an isolate for throughput.

The incident worker looked approximately like this:

```typescript
// workers/api.ts  (BUGGY VERSION — DO NOT COPY)

// Declared at module scope — lives for the isolate lifetime
const configCache: Record<string, unknown> = {};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const tenantId = request.headers.get("x-tenant-id") ?? "default";

    // BUG: mutating a module-scope object inside a request handler
    if (!configCache[tenantId]) {
      const config = await env.KV.get(`config:${tenantId}`, { type: "json" });
      configCache[tenantId] = config;
    }

    // Later in the same handler the cache is updated again with derived state
    configCache["_lastTenant"] = tenantId;   // BUG: cross-request write

    return new Response(JSON.stringify(configCache[tenantId]));
  },
};
```

The `_lastTenant` write is the obvious contamination, but any mutation of a
module-scope mutable object is dangerous. Under concurrency, two requests can
interleave their writes.

---

## Why Module Scope Feels Safe (and Isn't)

Developers coming from Lambda or Cloud Run expect cold-start/warm-start
semantics where the module scope is effectively read-only after initialization.
In those runtimes each invocation is usually serialized or short-lived enough
that mutations are invisible across calls.

Workers isolates are long-lived to minimize cold starts. The runtime will serve
hundreds or thousands of requests through a single isolate before retiring it.
Any mutable object initialized once at module scope accumulates mutations from
every request that passes through.

The Workers documentation notes this explicitly but it is easy to miss when
porting code from other runtimes.

---

## Safe Patterns

### 1. Read-only module-scope constants only

```typescript
// SAFE: primitives and frozen objects are fine at module scope
const MAX_RETRY = 3;
const SUPPORTED_REGIONS = Object.freeze(["us-east", "eu-west", "ap-south"]);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // request-scoped mutable state lives inside the handler
    const configCache: Record<string, unknown> = {};
    const tenantId = request.headers.get("x-tenant-id") ?? "default";

    const config = await env.KV.get(`config:${tenantId}`, { type: "json" });
    configCache[tenantId] = config;

    return new Response(JSON.stringify(config));
  },
};
```

### 2. Use a module-scope cache with care — immutable values, no cross-tenant keys

```typescript
// ACCEPTABLE: cache is only ever written once per key, value is frozen
const tenantConfigCache = new Map<string, Readonly<TenantConfig>>();

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const tenantId = request.headers.get("x-tenant-id") ?? "default";

    if (!tenantConfigCache.has(tenantId)) {
      const raw = await env.KV.get<TenantConfig>(`config:${tenantId}`, {
        type: "json",
      });
      if (raw) {
        tenantConfigCache.set(tenantId, Object.freeze(raw));
      }
    }

    const config = tenantConfigCache.get(tenantId);
    if (!config) {
      return new Response("tenant not found", { status: 404 });
    }

    return new Response(JSON.stringify(config));
  },
};
```

Note: This pattern is still a best-effort cache. The isolate may be retired
at any time, so it must never be the source of truth — only a performance
optimization on top of KV.

### 3. Use Durable Objects or KV for shared mutable state

If you genuinely need state shared across requests (counters, rate-limit
buckets, session stores), use a proper storage primitive:

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const sessionId = request.headers.get("x-session-id");
    if (!sessionId) return new Response("missing session", { status: 400 });

    // State lives in Durable Objects — isolated, serialized, durable
    const stub = env.SESSIONS.get(env.SESSIONS.idFromName(sessionId));
    return stub.fetch(request);
  },
};
```

---

## Anti-patterns

- Declaring `let someState = {}` at module scope and mutating it per-request.
- Appending to a module-scope array to collect metrics across requests (use
  Workers Analytics Engine instead).
- Storing per-request context (user ID, tenant ID, trace ID) in a module-scope
  variable — this is a security and correctness bug under concurrency.
- Importing a third-party SDK that internally stores mutable singletons at
  module scope. Audit SDK source or test under concurrent load.

---

## Gotchas

**Concurrency within a single isolate**: Workers supports concurrent async
requests in one isolate. Two requests can both be awaiting KV reads at the
same time. Any mutation to shared state between those awaits is a race
condition.

**Miniflare does not reproduce this bug by default**: Local development with
Miniflare (vitest-pool-workers) by default gives each test a fresh isolate.
You will not see cross-request contamination in unit tests. Reproduce the bug
by reusing the worker handler across multiple simulated requests in a single
test context with a shared module cache.

**Isolate retirement is not predictable**: Do not rely on the isolate being
retired to flush stale state. The runtime decides when to retire isolates
based on memory pressure and policy — it may keep an isolate alive for hours.

**`workerd` vs production semantics differ slightly**: The open-source workerd
runtime used by Miniflare may have slightly different isolate lifecycle
behavior than the production Workers runtime. Always validate caching
assumptions with integration tests against a deployed preview environment.

---

## Verification

1. Write a Miniflare integration test that reuses the worker module across 100
   sequential requests with different tenant IDs. Assert that each response
   contains only the config for its own tenant.
2. In staging, run a k6 or wrk load test with concurrent requests from two
   different tenant IDs. Assert no response contains the wrong tenant's data.
3. Add a Sentry (or Tail Worker) alert for any response body that contains a
   tenant ID that doesn't match the request's `x-tenant-id` header.

```typescript
// vitest integration check (miniflare)
it("does not leak config across requests", async () => {
  const worker = await createWorker(); // module reused across calls
  const resA = await worker.fetch(new Request("https://example.com/", {
    headers: { "x-tenant-id": "tenant-a" },
  }));
  const resB = await worker.fetch(new Request("https://example.com/", {
    headers: { "x-tenant-id": "tenant-b" },
  }));
  const bodyA = await resA.json();
  const bodyB = await resB.json();
  expect(bodyA.tenantId).toBe("tenant-a");
  expect(bodyB.tenantId).toBe("tenant-b");
});
```

---

## Related

- `workers-memory-128mb-limit-oom-postmortem.md` — isolate memory pressure
- `cloudflare-workers-engineering-onboarding.md` — isolate lifecycle overview
- `workers-testing-miniflare-vitest.md` — local test environment limitations

---

## Sources

- Cloudflare Workers documentation: "How Workers works" — isolate lifecycle
- Cloudflare Workers documentation: "Using module workers"
- GitHub issue: workers-sdk #3412 — module-scope mutation in concurrent handlers
