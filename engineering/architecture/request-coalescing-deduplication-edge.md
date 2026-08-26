# Request Coalescing and Deduplication at the Edge

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A product page receives 4 000 concurrent requests per second during a flash sale. Each request
independently fans out to the same upstream API to fetch the same price data. Even with a 1-second
CDN TTL the upstream receives thousands of cache-miss storms every minute, causing latency spikes
and occasional 503s. The solution is to coalesce those identical in-flight requests so that only
one upstream call is made per logical key at any point in time, and every waiting caller receives
the same resolved response.

## Context

Cloudflare Workers run at every PoP but do not share in-process memory across isolates. Naive
in-memory Maps therefore only coalesce requests within a single isolate on a single machine.
True edge-wide coalescing requires either a Durable Object (single-threaded actor with guaranteed
serialisation) or a Cache API write that includes a `cf-cache-status: MISS` coalescing guarantee
from the platform. This article covers three complementary layers:

1. Cache API short-circuit (zero cost, platform-handled).
2. Durable Object coalescing (programmable, cross-isolate, cross-machine within a PoP).
3. KV deduplication token for idempotent mutations.

## Layer 1 — Cache API Short-Circuit

```typescript
// worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cacheKey = new Request(canonicalUrl(request), { method: "GET" });
    const cache = caches.default;

    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    // Only one concurrent request per isolate reaches here;
    // the platform coalesces identical in-flight cache misses automatically.
    const upstream = await fetch(env.ORIGIN_URL + new URL(request.url).pathname);
    const response = new Response(upstream.body, upstream);
    response.headers.set("Cache-Control", "public, max-age=5, stale-while-revalidate=10");

    // Non-blocking write — callers don't wait for the cache write.
    event.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  },
} satisfies ExportedHandler<Env>;

function canonicalUrl(req: Request): string {
  const url = new URL(req.url);
  url.search = new URLSearchParams([...url.searchParams].sort()).toString();
  return url.toString();
}
```

The platform coalesces simultaneous cache misses for the same key automatically when the response
carries appropriate `Cache-Control` headers, but this is limited to the local PoP's cache node.

## Layer 2 — Durable Object Coalescing

A Durable Object acts as a single-writer actor per coalescing key. All requests that arrive during
an outstanding upstream call subscribe to the same Promise and resolve together.

```typescript
// CoalescingProxy.ts — Durable Object
export class CoalescingProxy implements DurableObject {
  private inflight: Map<string, Promise<{ body: string; status: number; headers: Record<string, string> }>> = new Map();

  async fetch(request: Request): Promise<Response> {
    const key = new URL(request.url).searchParams.get("key") ?? "";
    const upstreamUrl = new URL(request.url).searchParams.get("upstream") ?? "";

    let pending = this.inflight.get(key);
    if (!pending) {
      pending = this.callUpstream(upstreamUrl);
      this.inflight.set(key, pending);
      // Auto-clean after resolution so the next request triggers a fresh call
      pending.finally(() => this.inflight.delete(key));
    }

    const result = await pending;
    return new Response(result.body, {
      status: result.status,
      headers: result.headers,
    });
  }

  private async callUpstream(url: string) {
    const res = await fetch(url);
    const body = await res.text();
    const headers: Record<string, string> = {};
    res.headers.forEach((v, k) => { headers[k] = v; });
    return { body, status: res.status, headers };
  }
}
```

```typescript
// Worker entry-point routing to the DO
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const coalescingKey = url.pathname; // or a composite hash of path + query

    const id = env.COALESCING_PROXY.idFromName(coalescingKey);
    const stub = env.COALESCING_PROXY.get(id);

    // Forward with the coalescing key as a search param
    const proxyUrl = new URL("https://do-internal/");
    proxyUrl.searchParams.set("key", coalescingKey);
    proxyUrl.searchParams.set("upstream", env.ORIGIN + url.pathname + url.search);

    return stub.fetch(new Request(proxyUrl, { method: "GET" }));
  },
} satisfies ExportedHandler<Env>;
```

`wrangler.toml` binding:

```toml
[[durable_objects.bindings]]
name = "COALESCING_PROXY"
class_name = "CoalescingProxy"

[[migrations]]
tag = "v1"
new_classes = ["CoalescingProxy"]
```

## Layer 3 — KV Deduplication for Mutations

Write operations (POST, PUT, PATCH) must not be coalesced blindly — only idempotent requests with
the same idempotency key should be deduplicated. Use KV as a distributed token store.

```typescript
// idempotencyGuard.ts
export async function withIdempotency<T>(
  kv: KVNamespace,
  idempotencyKey: string,
  ttlSeconds: number,
  fn: () => Promise<T>
): Promise<{ result: T; duplicate: boolean }> {
  const stored = await kv.get<T>(idempotencyKey, "json");
  if (stored !== null) {
    return { result: stored, duplicate: true };
  }

  const result = await fn();
  // Best-effort store — not transactional, but acceptable for most APIs.
  await kv.put(idempotencyKey, JSON.stringify(result), { expirationTtl: ttlSeconds });
  return { result, duplicate: false };
}

// Usage in handler
export async function handleOrder(request: Request, env: Env): Promise<Response> {
  const key = request.headers.get("Idempotency-Key");
  if (!key) return new Response("Idempotency-Key header required", { status: 400 });

  const { result, duplicate } = await withIdempotency(
    env.IDEMPOTENCY_KV,
    `order:${key}`,
    300, // 5-minute window
    () => createOrder(request, env)
  );

  return Response.json(result, {
    status: duplicate ? 200 : 201,
    headers: duplicate ? { "X-Idempotent-Replayed": "true" } : {},
  });
}
```

## Anti-patterns

- **Coalescing mutations**: Never coalesce write operations without an explicit idempotency key.
  Two `POST /checkout` calls from different browser tabs are not the same logical operation.
- **Infinite coalescing windows**: Always clean up the `inflight` Map after the Promise resolves.
  A stuck upstream call will hold all coalescers indefinitely.
- **Mixing coalescing with personalised responses**: Coalescing is only safe for responses where
  every caller can receive identical bytes. Responses containing `Set-Cookie`, user-specific data,
  or `Vary`-sensitive headers must never be coalesced.
- **Relying on KV for sub-second deduplication**: KV has eventual consistency with ~60 ms median
  write propagation. Two requests arriving within milliseconds of each other may both pass the
  deduplication gate. Use Durable Objects when stricter guarantees are required.

## Gotchas

- Cloudflare's built-in cache coalescing applies only to GET/HEAD requests and only when the
  Worker does not call `cache.put()` before returning — returning early from `cache.match()` is
  enough to let the platform coalesce.
- Durable Objects are region-pinned. If a PoP in Singapore routes to a DO in `enam` (Eastern North
  America), coalescing helps throughput but adds round-trip latency. Pin critical DOs close to the
  upstream origin instead.
- The `inflight` Map in a Durable Object persists only for the lifetime of the isolate. After the
  DO hibernates (no traffic for ~10 seconds) the Map is empty, but that is fine — the point is to
  coalesce requests that are concurrent, not across cold starts.
- `cache.put()` has a 525 MB per-response size limit and silently drops responses exceeding it.
  Always check response size before caching large payloads.

## Verification

```bash
# Simulate 100 concurrent requests and confirm origin receives far fewer:
hey -n 100 -c 100 https://your-worker.example.com/expensive-resource

# Inspect Cloudflare cache status header:
curl -sI https://your-worker.example.com/expensive-resource | grep cf-cache-status

# Confirm idempotency replays:
KEY=$(uuidgen)
curl -X POST https://your-worker.example.com/orders \
  -H "Idempotency-Key: $KEY" -d '{"item":"widget"}' -v
curl -X POST https://your-worker.example.com/orders \
  -H "Idempotency-Key: $KEY" -d '{"item":"widget"}' -v
# Second call must return X-Idempotent-Replayed: true
```

## Related

- `caching-topology-cloudflare-native.md`
- `message-deduplication.md`
- `idempotency-keys-workers-api.md`
- `durable-object-alarm-api-scheduled-retry.md`
- `rate-limiting-architecture-workers.md`

## Sources

- Cloudflare Workers Cache API docs — https://developers.cloudflare.com/workers/runtime-apis/cache/
- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- RFC 9110 §9.2 Idempotent Methods — https://www.rfc-editor.org/rfc/rfc9110#section-9.2
- Stripe Idempotency Keys design — https://stripe.com/blog/idempotency
