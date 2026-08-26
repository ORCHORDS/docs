# Miniflare Cache API Simulation Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker uses `caches.default` or `caches.open()` to cache API responses, images, or HTML fragments. You want to write unit and integration tests that verify cache hit/miss logic, `Cache-Control` header handling, and `cache.put` / `cache.match` interactions without making real network requests or deploying to a live environment.

## Context

Miniflare v3+ (used by `@cloudflare/vitest-pool-workers`) provides an in-process simulation of the Cache API backed by a local store. Unlike the real Cloudflare cache (which is distributed and eventually consistent), the Miniflare cache is synchronous per-test-runner process and isolated per test suite by default. Each `caches.open(cacheName)` call in Miniflare returns a scoped `Cache` instance backed by the same underlying Miniflare storage backend.

---

## Vitest Pool Workers Setup

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          // Cache API is enabled by default — no extra config needed
          // Optionally scope cache per test file:
          isolatedStorage: true,
        },
      },
    },
  },
});
```

---

## Testing Cache Hit and Miss

```typescript
// src/cache.test.ts
import { SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";

describe("Cache API", () => {
  beforeEach(async () => {
    // Clear the default cache between tests
    const cache = await caches.open("default-test");
    const keys = await cache.keys();
    await Promise.all(keys.map((req) => cache.delete(req)));
  });

  it("returns cached response on second request", async () => {
    const url = "https://example.com/api/data";

    // First request — cache miss, Worker fetches origin
    const res1 = await SELF.fetch(url);
    expect(res1.headers.get("cf-cache-status")).toBe("MISS");

    // Second request — cache hit
    const res2 = await SELF.fetch(url);
    expect(res2.headers.get("cf-cache-status")).toBe("HIT");
    expect(res2.status).toBe(200);
  });

  it("does not cache POST requests", async () => {
    const url = "https://example.com/api/submit";
    const res = await SELF.fetch(url, { method: "POST", body: '{"x":1}' });
    expect(res.headers.get("cf-cache-status")).toBeNull();
  });
});
```

---

## Directly Manipulating the Cache in Tests

```typescript
import { env } from "cloudflare:test";

it("serves stale response from cache", async () => {
  const cache = await caches.open("v1");
  const cachedUrl = "https://example.com/resource";

  // Pre-seed the cache with a controlled response
  const seedResponse = new Response(JSON.stringify({ stale: true }), {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, max-age=3600",
    },
  });
  await cache.put(new Request(cachedUrl), seedResponse.clone());

  // Verify the Worker reads from cache
  const matched = await cache.match(new Request(cachedUrl));
  expect(matched).not.toBeNull();
  const body = await matched!.json<{ stale: boolean }>();
  expect(body.stale).toBe(true);
});

it("cache.delete removes a cached entry", async () => {
  const cache = await caches.open("v1");
  const req = new Request("https://example.com/item");

  await cache.put(req.clone(), new Response("cached"));
  expect(await cache.match(req.clone())).not.toBeNull();

  await cache.delete(req.clone());
  expect(await cache.match(req.clone())).toBeUndefined();
});
```

---

## Testing Cache-Control Directives

```typescript
// src/worker.ts — the Worker under test
export default {
  async fetch(request: Request): Promise<Response> {
    const cache = caches.default;
    const cached = await cache.match(request);
    if (cached) return cached;

    const response = new Response(JSON.stringify({ ts: Date.now() }), {
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "public, s-maxage=60, stale-while-revalidate=30",
      },
    });
    // Clone before putting — body can only be consumed once
    await cache.put(request.clone(), response.clone());
    return response;
  },
};

// src/worker.cache-control.test.ts
it("respects s-maxage in cache-control", async () => {
  const url = "https://example.com/timed";
  const res1 = await SELF.fetch(url);
  const body1 = await res1.json<{ ts: number }>();

  // Miniflare honours max-age / s-maxage — response within TTL is returned
  const res2 = await SELF.fetch(url);
  const body2 = await res2.json<{ ts: number }>();

  // Same timestamp — served from cache, not re-computed
  expect(body2.ts).toBe(body1.ts);
});
```

---

## Namespaced Cache Isolation Between Tests

```typescript
import { describe, it, expect } from "vitest";

// Use unique cache names to avoid cross-test interference
// when isolatedStorage is not enabled at the pool level
function testCache(testId: string) {
  return caches.open(`test-${testId}-${Math.random().toString(36).slice(2)}`);
}

it("isolated cache namespace A", async () => {
  const cache = await testCache("a");
  await cache.put(
    new Request("https://x.com/"),
    new Response("from A")
  );
  const match = await cache.match("https://x.com/");
  expect(await match?.text()).toBe("from A");
});

it("isolated cache namespace B does not see A's entries", async () => {
  const cache = await testCache("b");
  const match = await cache.match("https://x.com/");
  expect(match).toBeUndefined();
});
```

---

## Anti-patterns

- Calling `await cache.put(req, res)` without cloning `res` before returning it — the response body is consumed and the Worker returns an empty body.
- Using `caches.default` in tests without resetting between test cases — prior test cache entries leak into later tests and produce false positives.
- Asserting `cf-cache-status: HIT` in Miniflare tests as proof of production cache behavior — Miniflare's cache is single-process and always synchronous; production cache is distributed and has separate edge PoP state.
- Mixing `caches.open("production-name")` in tests with real Wrangler dev (`wrangler dev`) — Miniflare and Wrangler dev use separate backing stores.
- Not setting `Cache-Control` on cached responses — Miniflare may or may not expire entries depending on version; always be explicit about TTL in tests.

---

## Gotchas

- `caches.default` in Miniflare is NOT the same object as `caches.open("default")` — they are separate cache namespaces.
- `cache.match()` returns `undefined` (not `null`) on a miss — use `toBeUndefined()` in assertions, not `toBeNull()`.
- Streaming responses (`ReadableStream` bodies) must be cloned before `cache.put` and also before reading — calling `.json()` or `.text()` on the response passed to `put` consumes it.
- In `vitest-pool-workers`, `isolatedStorage: true` resets Miniflare's cache between each test file, not each test case — use `beforeEach` cleanup for within-file isolation.
- Miniflare's Cache API does not simulate Cloudflare's Vary header handling or purge-by-tag semantics.

---

## Verification

```bash
# Run cache-specific tests with verbose output
pnpm vitest run --reporter=verbose src/cache.test.ts

# Check that Miniflare is using the Workers pool (not jsdom)
pnpm vitest run --reporter=verbose 2>&1 | grep "miniflare"

# Confirm no cache state leaks between test files
pnpm vitest run --sequence.concurrent=false src/cache.test.ts src/other.test.ts
```

---

## Related

- `miniflare-d1-test-seeding-fixtures.md` — seeding D1 data alongside cache tests
- `miniflare-durable-objects-fake-clock-testing.md` — simulating time for TTL expiry
- `miniflare-storage-backend-testing.md` — understanding Miniflare's backing store
- `vitest-workers-miniflare-testing-setup.md` — base Miniflare + Vitest configuration
- `msw-external-api-mocking-workers-tests.md` — mocking the origin that the Worker would cache

---

## Sources

- Cloudflare Cache API docs: https://developers.cloudflare.com/workers/runtime-apis/cache/
- Miniflare storage internals: https://github.com/cloudflare/workers-sdk/tree/main/packages/miniflare
- `@cloudflare/vitest-pool-workers` README: https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
