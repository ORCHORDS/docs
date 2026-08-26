# Bulkhead Isolation with Cloudflare Workers Service Bindings

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A single slow downstream (e.g. a legacy database API) causes the entire edge Worker to exhaust its CPU budget, killing unrelated request paths. You want failures in one subsystem to be contained — a bulkhead — so that search, checkout, and content endpoints degrade independently rather than all failing together.

---

## Context

The bulkhead pattern (named after watertight compartments in ships) partitions a system into isolated pools. In Cloudflare Workers, the natural isolation unit is a **named Worker**. Service bindings (`env.SERVICE.fetch(request)`) let one Worker call another with near-zero overhead (same PoP, no TLS round-trip).

Each Worker has its own:
- CPU time limit (10 ms on free, 30 s on paid by default)
- Memory heap
- Subrequest budget
- Failure domain

By routing subsystem calls through a dedicated Worker, you get per-subsystem concurrency caps, timeouts, and circuit-breaker state — without any shared mutable state leaking between pools.

```
Gateway Worker
  ├─ env.SEARCH_SVC.fetch(...)   → search-worker     (pool A)
  ├─ env.CHECKOUT_SVC.fetch(...) → checkout-worker   (pool B)
  └─ env.CONTENT_SVC.fetch(...) → content-worker    (pool C)
```

---

## Defining Service Bindings (wrangler.toml)

```toml
# gateway/wrangler.toml
name = "gateway-worker"

[[services]]
binding = "SEARCH_SVC"
service = "search-worker"

[[services]]
binding = "CHECKOUT_SVC"
service = "checkout-worker"

[[services]]
binding = "CONTENT_SVC"
service = "content-worker"
```

Each bound service runs as its own Worker deployment and can be scaled, configured, or rolled back independently.

---

## Gateway Worker — Routing with Isolation

```typescript
// gateway/src/index.ts
import { Env } from './types';

interface BulkheadResult<T> {
  ok: boolean;
  data?: T;
  error?: string;
  latencyMs: number;
}

async function callWithTimeout<T>(
  serviceCall: () => Promise<Response>,
  timeoutMs: number,
  fallback: T
): Promise<BulkheadResult<T>> {
  const start = Date.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await serviceCall();
    clearTimeout(timer);
    if (!res.ok) {
      return { ok: false, error: `upstream ${res.status}`, latencyMs: Date.now() - start };
    }
    const data = await res.json() as T;
    return { ok: true, data, latencyMs: Date.now() - start };
  } catch (err) {
    clearTimeout(timer);
    const isTimeout = err instanceof Error && err.name === 'AbortError';
    return {
      ok: false,
      error: isTimeout ? 'timeout' : String(err),
      data: fallback,
      latencyMs: Date.now() - start,
    };
  }
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith('/search')) {
      const result = await callWithTimeout(
        () => env.SEARCH_SVC.fetch(request.clone()),
        3000,
        { results: [], degraded: true }
      );
      return Response.json(result.data ?? { results: [], degraded: true }, {
        status: result.ok ? 200 : 206,
      });
    }

    if (url.pathname.startsWith('/checkout')) {
      // Checkout is critical — no fallback, propagate error
      const result = await callWithTimeout(
        () => env.CHECKOUT_SVC.fetch(request.clone()),
        10_000,
        null
      );
      if (!result.ok) return new Response(result.error ?? 'Service unavailable', { status: 503 });
      return Response.json(result.data);
    }

    if (url.pathname.startsWith('/content')) {
      const result = await callWithTimeout(
        () => env.CONTENT_SVC.fetch(request.clone()),
        2000,
        { content: null, cached: false }
      );
      return Response.json(result.data, { status: 200 }); // always 200; UI handles null content
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

---

## Per-Bulkhead Worker with Internal Error Handling

```typescript
// search-worker/src/index.ts
import { Env } from './types';

const MAX_CONCURRENT = 20; // enforced by Durable Object semaphore in production
let activeRequests = 0;    // coarse in-process limit per isolate

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (activeRequests >= MAX_CONCURRENT) {
      return new Response('Bulkhead full', { status: 503, headers: { 'Retry-After': '1' } });
    }

    activeRequests++;
    try {
      const query = new URL(request.url).searchParams.get('q') ?? '';
      const rows = await env.DB.prepare(
        'SELECT id, title FROM articles WHERE title LIKE ? LIMIT 20'
      ).bind(`%${query}%`).all();

      return Response.json({ results: rows.results });
    } catch (err) {
      // Failure is contained to this Worker; gateway gets a 500, applies its fallback
      return new Response(String(err), { status: 500 });
    } finally {
      activeRequests--;
    }
  },
};
```

---

## Durable Object Semaphore for Precise Concurrency Cap

For production-grade bulkheads the in-process counter above is per-isolate (Cloudflare may spin up multiple isolates). Use a Durable Object for a globally enforced limit:

```typescript
// shared/semaphore-do.ts
export class SemaphoreDO implements DurableObject {
  private count = 0;
  private readonly limit: number;

  constructor(state: DurableObjectState) {
    this.limit = 20; // configurable via env in practice
  }

  async fetch(request: Request): Promise<Response> {
    const action = new URL(request.url).pathname;

    if (action === '/acquire') {
      if (this.count >= this.limit) {
        return new Response('rejected', { status: 429 });
      }
      this.count++;
      return new Response('acquired', { status: 200 });
    }

    if (action === '/release') {
      this.count = Math.max(0, this.count - 1);
      return new Response('released', { status: 200 });
    }

    return new Response('Unknown', { status: 400 });
  }
}

// Usage in search-worker
async function withSemaphore<T>(
  doStub: DurableObjectStub,
  fn: () => Promise<T>
): Promise<T | null> {
  const acquired = await doStub.fetch('https://do/acquire');
  if (acquired.status === 429) return null; // bulkhead full

  try {
    return await fn();
  } finally {
    await doStub.fetch('https://do/release');
  }
}
```

---

## Anti-patterns

- **Shared mutable state across bulkheads**: using a single KV key as a global counter defeats isolation. Each bulkhead's semaphore should be a separate Durable Object.
- **Bulkhead without fallback**: a bulkhead that returns 503 with no fallback simply moves the failure from downstream to the gateway without improving UX. Pair with graceful degradation.
- **Identical timeouts across bulkheads**: a 10 s timeout for search is the same as no timeout from a UX perspective. Tune per-service SLO.
- **Calling bulkhead Workers in sequence**: if search, content, and recommendations are independent, fan them out with `Promise.allSettled` rather than awaiting one before the next.

---

## Gotchas

- Service binding calls do **not** count against the calling Worker's subrequest limit separately — each bound-service invocation does consume one subrequest slot from the caller's budget (1000/invocation on paid tier).
- A bulkhead Worker that itself calls another Worker inherits the *original* request's CPU wall-clock budget; it does NOT get a fresh 30 s budget.
- `AbortController` signals passed into `fetch` inside a service binding call are respected only from the caller side; the callee Worker continues running until its own timeout.
- In-process `activeRequests` counters reset between cold starts. The semaphore Durable Object approach is necessary when isolates are frequently evicted.

---

## Verification

```bash
# Load-test the search bulkhead to confirm 503 under saturation
npx autocannon -c 50 -d 10 https://gateway.example.com/search?q=test

# Confirm checkout is unaffected while search is saturated
npx autocannon -c 5 -d 10 https://gateway.example.com/checkout
```

```typescript
// Unit test: gateway returns 206 (degraded) when search-worker returns 500
const mockSearchSvc = {
  fetch: async () => new Response('error', { status: 500 }),
};
const env = { SEARCH_SVC: mockSearchSvc, CHECKOUT_SVC: ..., CONTENT_SVC: ... };
const res = await gatewayWorker.fetch(new Request('https://x/search?q=test'), env, ctx);
assert.equal(res.status, 206);
const body = await res.json();
assert.equal(body.degraded, true);
```

---

## Related

- `bulkhead-pattern.md`
- `circuit-breaker-design.md`
- `circuit-breaker-kv-state-machine.md`
- `worker-to-worker-rpc-service-bindings.md`
- `scatter-gather-workers-service-bindings.md`
- `rate-limiting-architecture-workers.md`

---

## Sources

- Cloudflare Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Release It! (Bulkhead chapter) — Michael T. Nygard, Pragmatic Programmers 2018
- Durable Objects — https://developers.cloudflare.com/durable-objects/
