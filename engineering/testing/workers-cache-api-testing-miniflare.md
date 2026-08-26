# Workers Cache API Testing with Miniflare

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Cloudflare Workers can call `caches.default` and `caches.open()` to store and serve responses at the edge, but this Cache API is absent from the standard Node.js test environment. Tests that bypass the cache layer give false confidence and miss cache-key collisions, premature TTL expiry, and `Vary` header mismatches that only surface in production. Exercising the cache inside the Workers runtime via `@cloudflare/vitest-pool-workers` gives tests access to a real, per-test-isolated Cache API implementation without a network round-trip.

## Context

The Workers Cache API (`caches.default`, `cache.put()`, `cache.match()`, `cache.delete()`) is a superset of the browser Cache API spec. It is scoped to the Worker's zone and keyed on the full `Request` URL by default. Miniflare 3 (bundled with `@cloudflare/vitest-pool-workers`) emulates the Cache API in-process with per-test isolation so a `cache.put` in one test cannot bleed into another. Testing cache behaviour requires asserting both the miss path — no cache entry, upstream fetch executed — and the hit path — entry returned without calling upstream. The Worker source must clone the response before caching so that both the cached copy and the caller can read the body.

## Testing Cache Miss and Hit Paths

```typescript
// test/cache.spec.ts
import {
  createExecutionContext,
  waitOnExecutionContext,
  env,
} from "cloudflare:test";
import { describe, it, expect, vi, beforeEach } from "vitest";
import worker from "../src/index";

const TEST_URL = "https://example.com/api/data";

beforeEach(async () => {
  // Explicit cleanup guards against contamination in parallel shard runs
  await caches.default.delete(new Request(TEST_URL));
});

describe("Cache API — default cache miss/hit cycle", () => {
  it("calls upstream on first request and stores the response", async () => {
    const req = new Request(TEST_URL);
    const ctx = createExecutionContext();
    const res = await worker.fetch(req, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(res.status).toBe(200);
    expect(res.headers.get("X-Cache")).toBe("MISS");

    // Verify entry is now present in the cache
    const cached = await caches.default.match(new Request(TEST_URL));
    expect(cached).not.toBeUndefined();
    expect(cached?.headers.get("Cache-Control")).toMatch(/max-age=/);
  });

  it("returns the cached entry on the second request without calling upstream", async () => {
    // Warm the cache
    const ctx1 = createExecutionContext();
    await worker.fetch(new Request(TEST_URL), env, ctx1);
    await waitOnExecutionContext(ctx1);

    // Spy on global fetch to assert it is NOT called on cache hit
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    const ctx2 = createExecutionContext();
    const res = await worker.fetch(new Request(TEST_URL), env, ctx2);
    await waitOnExecutionContext(ctx2);

    expect(res.status).toBe(200);
    expect(res.headers.get("X-Cache")).toBe("HIT");
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
```

## Worker Source Under Test

```typescript
// src/index.ts — cache-aside pattern
export default {
  async fetch(request: Request, _env: Env): Promise<Response> {
    const cacheKey = new Request(request.url, { method: "GET" });
    const cached   = await caches.default.match(cacheKey);

    if (cached) {
      const hit = new Response(cached.body, cached);
      hit.headers.set("X-Cache", "HIT");
      return hit;
    }

    const upstream = await fetch(
      "https://origin.example.com" + new URL(request.url).pathname
    );
    const response = new Response(upstream.body, upstream);
    response.headers.set("Cache-Control", "public, max-age=300, s-maxage=3600");
    response.headers.set("X-Cache", "MISS");

    // Clone before caching — body can only be read once
    await caches.default.put(cacheKey, response.clone());
    return response;
  },
};
```

## Testing Named Caches and Vary-Header Keying

```typescript
// test/named-cache.spec.ts
import { createExecutionContext, waitOnExecutionContext, env } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import worker from "../src/index";

describe("Cache API — named cache with Vary: Accept-Language", () => {
  const makeReq = (lang: string) =>
    new Request("https://example.com/api/greet", {
      headers: { "Accept-Language": lang },
    });

  it("stores separate entries for each locale", async () => {
    for (const lang of ["en-US", "fr-FR"]) {
      const ctx = createExecutionContext();
      await worker.fetch(makeReq(lang), env, ctx);
      await waitOnExecutionContext(ctx);
    }

    const cache = await caches.open("greetings-v1");
    const enEntry = await cache.match(makeReq("en-US"));
    const frEntry = await cache.match(makeReq("fr-FR"));

    expect(enEntry).not.toBeUndefined();
    expect(frEntry).not.toBeUndefined();

    const enBody = await enEntry!.json<{ greeting: string }>();
    const frBody = await frEntry!.json<{ greeting: string }>();
    expect(enBody.greeting).toBe("Hello");
    expect(frBody.greeting).toBe("Bonjour");
  });

  it("removes a stale entry via cache.delete()", async () => {
    const cache = await caches.open("greetings-v1");

    // Seed manually for isolation
    await cache.put(
      makeReq("en-US"),
      new Response(JSON.stringify({ greeting: "Hello" }), {
        headers: {
          "Content-Type":  "application/json",
          "Cache-Control": "max-age=60",
          "Vary":          "Accept-Language",
        },
      })
    );

    const deleted = await cache.delete(makeReq("en-US"));
    expect(deleted).toBe(true);

    const afterDelete = await cache.match(makeReq("en-US"));
    expect(afterDelete).toBeUndefined();
  });
});
```

## Anti-patterns

- Mocking `caches.default` with `vi.fn()` — removes the real key-matching logic and hides bugs where the cache key differs between `put` and `match`
- Testing cache behaviour by calling `fetch()` directly without going through `worker.fetch()` — bypasses the Worker's cache-aside wrapper, making the assertion vacuous
- Not cloning `Response` before calling `cache.put()` — the body stream is consumed by the put operation and the caller's `return response` returns an empty body

## Gotchas

- Miniflare's Cache API respects `Vary` headers: a `put` with `Vary: Accept-Language` stored under an `en-US` request will not match a `fr-FR` request even if the URL is identical — this mirrors production behaviour and is often the source of cache miss bugs
- `caches.default.match()` returns `undefined` (not `null`) on a cache miss in the Workers runtime; assertions using `toBeNull()` will pass incorrectly for both miss and match outcomes
- Cache entries stored with `Cache-Control: no-store` or `private` are not persisted by Miniflare, mirroring production — tests that seed such a response directly via `cache.put()` will silently discard it

## Verification

```bash
npx vitest run test/cache.spec.ts test/named-cache.spec.ts --reporter=verbose
# All X-Cache header assertions and caches.default.match() checks should pass

# Manual smoke test with wrangler dev
npx wrangler dev --local src/index.ts &
sleep 2
curl -si http://localhost:8787/api/data | grep X-Cache   # MISS
curl -si http://localhost:8787/api/data | grep X-Cache   # HIT
```

## Related

- `testing/kv-testing-miniflare.md`
- `testing/durable-objects-miniflare-fake-timers.md`
- `testing/workers-unit-testing-fetch-mocking.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://miniflare.dev/storage/cache
