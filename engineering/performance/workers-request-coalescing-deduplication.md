# Workers Request Coalescing Deduplication Pattern

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

Under traffic spikes, many concurrent Workers requests for the same resource (product page, pricing feed, configuration JSON) each fire an independent subrequest to the origin or D1/KV, overwhelming the upstream and inflating your billable subrequest count. Cache-Control has a TTL, but within a single cache miss window dozens of requests stampede simultaneously. You need exactly-one in-flight fetch per unique resource key per isolate.

---

## Context

Each Cloudflare Workers isolate is a V8 isolate that handles **one request at a time** within a single JS event loop turn, but multiple concurrent requests can be routed to the same isolate during a burst. JavaScript's single-threaded cooperative scheduling means a `Map` used as an in-flight registry is safe without locks — there is no race condition between concurrent reads of the map and mutation of it within the same microtask checkpoint.

Request coalescing (also called request deduplication or "thundering herd prevention") is the pattern of:

1. Receiving a cache miss for key K.
2. Checking whether a fetch for K is already in-flight.
3. If yes, awaiting the **same Promise** rather than starting a new fetch.
4. If no, creating the fetch Promise, storing it in the registry, and awaiting it.
5. After resolution, removing the key from the registry and optionally populating the cache.

This is distinct from cache stampede prevention (which focuses on stale-while-revalidate) and from HTTP/2 connection coalescing (which is a transport-layer mechanism).

---

## In-Process Coalescing with a Module-Level Map

```typescript
// Module-level: survives across multiple requests in the same isolate lifetime.
const inFlight = new Map<string, Promise<Response>>();

interface Env {
  ORIGIN: string; // e.g. "https://api.example.com"
}

async function fetchWithCoalescing(
  key: string,
  fetcher: () => Promise<Response>
): Promise<Response> {
  const existing = inFlight.get(key);
  if (existing) {
    // Clone because a Response body can only be consumed once.
    return (await existing).clone();
  }

  const promise = fetcher().then(async (res) => {
    // Buffer the body so all waiters can clone it.
    const body = await res.arrayBuffer();
    return new Response(body, {
      status: res.status,
      headers: res.headers,
    });
  });

  inFlight.set(key, promise);

  try {
    const result = await promise;
    return result.clone();
  } finally {
    inFlight.delete(key);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname + url.search;

    return fetchWithCoalescing(key, () =>
      fetch(`${env.ORIGIN}${key}`, {
        headers: { "X-Internal": "1" },
      })
    );
  },
};
```

---

## Adding a Short In-Memory Cache After Coalescing

```typescript
interface CacheEntry {
  body: ArrayBuffer;
  status: number;
  headers: Record<string, string>;
  expiresAt: number;
}

const inFlight = new Map<string, Promise<CacheEntry>>();
const memCache = new Map<string, CacheEntry>();
const TTL_MS = 5_000; // 5 seconds — short enough to be "near-live"

async function getResource(key: string, origin: string): Promise<Response> {
  const cached = memCache.get(key);
  if (cached && cached.expiresAt > Date.now()) {
    return new Response(cached.body.slice(0), {
      status: cached.status,
      headers: cached.headers,
    });
  }

  let inflight = inFlight.get(key);
  if (!inflight) {
    inflight = fetch(`${origin}${key}`)
      .then(async (res) => {
        const body = await res.arrayBuffer();
        const headers: Record<string, string> = {};
        res.headers.forEach((v, k) => {
          headers[k] = v;
        });
        const entry: CacheEntry = {
          body,
          status: res.status,
          headers,
          expiresAt: Date.now() + TTL_MS,
        };
        memCache.set(key, entry);
        return entry;
      })
      .finally(() => inFlight.delete(key));

    inFlight.set(key, inflight);
  }

  const entry = await inflight;
  return new Response(entry.body.slice(0), {
    status: entry.status,
    headers: entry.headers,
  });
}
```

---

## Cross-Isolate Coalescing via Durable Objects

In-process coalescing only helps within a single isolate. Multiple isolates serving the same edge PoP each independently fire their own subrequest. For true cross-isolate deduplication, route cache-miss coordination through a Durable Object.

```typescript
// durable_object.ts
export class RequestCoalescer implements DurableObject {
  private inFlight = new Map<string, Promise<{ body: string; status: number; headers: Record<string, string> }>>();

  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const { key, origin } = (await request.json()) as { key: string; origin: string };

    let promise = this.inFlight.get(key);
    if (!promise) {
      promise = fetch(`${origin}${key}`)
        .then(async (res) => {
          const body = await res.text();
          const headers: Record<string, string> = {};
          res.headers.forEach((v, k) => (headers[k] = v));
          return { body, status: res.status, headers };
        })
        .finally(() => this.inFlight.delete(key));

      this.inFlight.set(key, promise);
    }

    const result = await promise;
    return new Response(result.body, {
      status: result.status,
      headers: result.headers,
    });
  }
}

// worker.ts — routes cache misses through the Durable Object
export default {
  async fetch(request: Request, env: Env & { COALESCER: DurableObjectNamespace }): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname;

    // Stable name ensures all isolates reach the same DO instance.
    const id = env.COALESCER.idFromName(key);
    const stub = env.COALESCER.get(id);

    return stub.fetch("https://internal/coalesce", {
      method: "POST",
      body: JSON.stringify({ key, origin: "https://api.example.com" }),
    });
  },
};
```

---

## Keying Strategy

The coalescing key must capture exactly the cache dimensions that make two requests equivalent. Over-broad keys serve the wrong content; over-narrow keys reduce deduplication hit rate.

```typescript
function buildCoalesceKey(request: Request): string {
  const url = new URL(request.url);
  // Include path and query; exclude per-user parameters from public resources.
  const canonical = `${url.pathname}?${url.searchParams.toString()}`;

  // For auth-gated resources, include the user tier but NOT the full token.
  const tier = request.headers.get("X-User-Tier") ?? "public";

  return `${tier}:${canonical}`;
}
```

---

## Timeout and Error Propagation

```typescript
async function fetchWithTimeout(url: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

// Errors in the shared Promise propagate to all waiters — handle them:
async function safeCoalesce(key: string, fetcher: () => Promise<Response>) {
  let inflight = inFlight.get(key);
  if (inflight) return (await inflight).clone();

  inflight = fetcher()
    .then(async (r) => new Response(await r.arrayBuffer(), { status: r.status, headers: r.headers }))
    .catch((err) => {
      inFlight.delete(key); // Don't cache errors
      throw err;
    })
    .finally(() => {
      // Only delete on success path (error path deletes above)
    });

  inFlight.set(key, inflight);
  return (await inflight).clone();
}
```

---

## Anti-patterns

- **Coalescing mutable or personalised resources.** Sharing a response body between users with different auth contexts is a data leak. Coalescing only applies to resources that are identical across all concurrent requesters sharing the same key.
- **Forgetting to clone the Response.** A `Response` body is a one-time-read stream. Every caller must receive a `.clone()` or an independent `new Response(bufferedBody)`.
- **Infinite-growth Map.** If key space is unbounded and the Map is never pruned, the isolate leaks memory across its lifetime. Add a max-size eviction or bound the key space (e.g., only coalesce paths matching `/api/public/*`).
- **Using coalescing as a replacement for the Cache API.** Coalescing only deduplicates concurrent in-flight requests. Between bursts, a cold isolate has an empty map. Use the Cache API or KV for cross-request caching; use coalescing to protect the upstream during the fill window.
- **Coalescing write or non-idempotent requests.** Only GET/HEAD requests that return the same body for all concurrent callers are candidates.

---

## Gotchas

- **Isolate lifecycle:** Cloudflare can spin up or down isolates at any time. The in-process Map is not shared across isolates, even on the same PoP machine. Cross-isolate coalescing requires Durable Objects.
- **Memory spike during large response buffering.** Coalescing a 10 MB payload means the isolate holds that buffer while all waiters consume it. Set a size threshold above which you skip coalescing and let callers fetch independently.
- **Promise rejection propagates to all waiters.** If the origin is flaky and returns an error, all coalesced callers get the same error. Implement a retry in the fetcher rather than in each caller.
- **V8 heap pressure with many concurrent keys.** Each in-flight Promise holds a live V8 object. Under extreme fan-out (thousands of distinct keys simultaneously) the Map itself becomes a GC pressure point.

---

## Verification

```typescript
// Track deduplication ratio in Worker analytics
let totalRequests = 0;
let coalescedHits = 0;

// In the coalescing function:
totalRequests++;
if (inFlight.has(key)) coalescedHits++;

// Emit to Analytics Engine or logpush every N requests:
if (totalRequests % 100 === 0) {
  console.log(JSON.stringify({
    dedup_ratio: coalescedHits / totalRequests,
    in_flight_keys: inFlight.size,
  }));
}
```

Monitor `subrequests` count in Cloudflare Worker metrics — a successful coalescing deployment should show a measurable drop in subrequest rate relative to inbound request rate during traffic bursts.

---

## Related

- `cache-stampede-prevention.md`
- `workers-subrequest-fanout-parallelism.md`
- `durable-objects-read-cache-layer.md`
- `kv-read-performance.md`
- `workers-fetch-connection-reuse-tcp.md`

---

## Sources

- Cloudflare Workers runtime API: https://developers.cloudflare.com/workers/runtime-apis/
- Durable Objects documentation: https://developers.cloudflare.com/durable-objects/
- MDN Response.clone(): https://developer.mozilla.org/en-US/docs/Web/API/Response/clone
- "Thundering herd problem" — Wikipedia: https://en.wikipedia.org/wiki/Thundering_herd_problem
