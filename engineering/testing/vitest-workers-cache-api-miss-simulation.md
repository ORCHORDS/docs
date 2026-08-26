# Vitest Workers Cache API Cache Miss Simulation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker uses the Cache API (`caches.default`) to serve responses from cache and fall
back to an origin fetch on a miss. The happy path (cache hit) is easy to test, but the miss path
—where the Worker must actually call the origin, build a response, set cache headers, and `put`
the result—is harder to drive reliably. Without explicit miss simulation, tests either always hit
a cold cache (giving no signal about cache hit logic) or always hit a warm cache (giving no signal
about miss logic). This article covers how to force cache misses deterministically in Vitest with
`@cloudflare/vitest-pool-workers`.

---

## Context

The Workers Cache API is a thin wrapper over the HTTP cache. In `wrangler dev --local` (backed by
Miniflare), `caches.default` is an in-memory `Map` keyed by the full request URL including
method, Vary headers, and cache key overrides. The cache is shared within a single Miniflare
process but is **not** persisted between Vitest test runs by default—so each `vitest run`
invocation starts with a cold cache. Within a single test file, however, the cache is shared
across tests unless explicitly cleared.

Key objects:
- `caches.default` — the default HTTP cache namespace
- `cache.match(request)` — returns `Response | undefined`
- `cache.put(request, response)` — stores a cloned response
- `cache.delete(request)` — removes a cached entry

---

## Vitest Pool Configuration

```ts
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { cloudflareWorkersPool } from "@cloudflare/vitest-pool-workers";

export default defineConfig({
  test: {
    pool: cloudflareWorkersPool,
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
  },
});
```

---

## The Worker Under Test

```ts
// src/worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cache = caches.default;
    const cacheKey = new Request(request.url, { method: "GET" });

    // Attempt cache hit
    const cached = await cache.match(cacheKey);
    if (cached) {
      const hit = new Response(cached.body, cached);
      hit.headers.set("X-Cache", "HIT");
      return hit;
    }

    // Cache miss — fetch from origin
    const origin = new URL(request.url);
    origin.hostname = env.ORIGIN_HOST;
    const originResponse = await fetch(origin.toString());

    // Cache the response for 60 seconds
    const toCache = new Response(originResponse.clone().body, originResponse);
    toCache.headers.set("Cache-Control", "public, max-age=60");
    await cache.put(cacheKey, toCache);

    const miss = new Response(originResponse.body, originResponse);
    miss.headers.set("X-Cache", "MISS");
    return miss;
  },
};
```

---

## Forcing a Cache Miss via `cache.delete`

The most reliable pattern is to delete the cache entry before each test that must exercise the
miss path:

```ts
// test/cache-miss.test.ts
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach, vi } from "vitest";

const TEST_URL = "https://example.com/api/resource";

beforeEach(async () => {
  // Evict any entry from a previous test
  const cache = caches.default;
  await cache.delete(new Request(TEST_URL, { method: "GET" }));
});

describe("cache miss path", () => {
  it("returns X-Cache: MISS on first request", async () => {
    // Stub the origin fetch so the test does not need a real upstream
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ data: "fresh" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      );

    const res = await SELF.fetch(TEST_URL);

    expect(res.status).toBe(200);
    expect(res.headers.get("X-Cache")).toBe("MISS");

    fetchSpy.mockRestore();
  });
});
```

---

## Simulating a Cache Miss with a Custom Cache Key Override

Workers can override the cache key via `cf.cacheKey`. Test that the miss path fires for each
unique key:

```ts
describe("cache key override miss simulation", () => {
  it("misses when cf.cacheKey changes even for same URL", async () => {
    // Pre-warm cache under key variant A
    const warmResponse = new Response("variant-a", {
      headers: { "Cache-Control": "public, max-age=60" },
    });
    await caches.default.put(
      new Request(`${TEST_URL}?_ck=a`),
      warmResponse.clone()
    );

    // Request with variant B key should miss
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response("variant-b", {
          status: 200,
          headers: { "Content-Type": "text/plain" },
        })
      );

    const res = await SELF.fetch(`${TEST_URL}?_ck=b`);
    expect(res.headers.get("X-Cache")).toBe("MISS");
    const body = await res.text();
    expect(body).toBe("variant-b");

    fetchSpy.mockRestore();
  });
});
```

---

## Verifying `cache.put` Is Called on Miss

Use `vi.spyOn` on `caches.default.put` to assert the Worker stores the fetched response:

```ts
describe("cache population on miss", () => {
  it("calls cache.put with the fetched response on a miss", async () => {
    const cache = caches.default;
    const putSpy = vi.spyOn(cache, "put");

    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("origin data", {
        status: 200,
        headers: {
          "Content-Type": "text/plain",
          "Cache-Control": "public, max-age=60",
        },
      })
    );

    await SELF.fetch(TEST_URL);

    expect(putSpy).toHaveBeenCalledOnce();
    const [putRequest, putResponse] = putSpy.mock.calls[0];
    expect((putRequest as Request).url).toBe(TEST_URL);
    expect(putResponse.headers.get("Cache-Control")).toBe("public, max-age=60");

    putSpy.mockRestore();
    vi.restoreAllMocks();
  });
});
```

---

## Confirming Hit After Miss (Warm-Up Cycle)

The full warm-up cycle (MISS then HIT) validates both branches end-to-end:

```ts
describe("miss → hit cycle", () => {
  it("returns MISS then HIT for the same URL", async () => {
    // First request: miss
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("cached body", {
        status: 200,
        headers: {
          "Content-Type": "text/plain",
          "Cache-Control": "public, max-age=60",
        },
      })
    );

    const first = await SELF.fetch(TEST_URL);
    expect(first.headers.get("X-Cache")).toBe("MISS");
    expect(await first.text()).toBe("cached body");

    // Second request: hit (no fetch mock—would throw if called)
    const second = await SELF.fetch(TEST_URL);
    expect(second.headers.get("X-Cache")).toBe("HIT");
    expect(await second.text()).toBe("cached body");

    vi.restoreAllMocks();
  });
});
```

---

## Simulating Cache Bypass via `Cache-Control: no-store`

Some Worker implementations honour `no-store` requests to bypass the cache entirely:

```ts
describe("Cache-Control: no-store bypass", () => {
  it("bypasses cache when request sends no-store", async () => {
    // Pre-warm
    await caches.default.put(
      new Request(TEST_URL),
      new Response("stale", { headers: { "Cache-Control": "public, max-age=3600" } })
    );

    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("fresh via bypass", { status: 200 })
    );

    const res = await SELF.fetch(TEST_URL, {
      headers: { "Cache-Control": "no-store" },
    });

    // Worker should have called fetch (origin) not served the cached "stale" body
    expect(await res.text()).toBe("fresh via bypass");
    vi.restoreAllMocks();
  });
});
```

---

## Anti-patterns

- **Relying on test execution order to produce a cold cache** — Vitest may run tests in any
  order. Always `cache.delete` in `beforeEach` for tests that require a miss.
- **Mocking `caches.default` entirely** — replacing the cache object loses real `put`/`match`
  semantics. Spy on individual methods instead.
- **Calling `cache.put` with a non-cloned response** — the Cache API requires the response body
  to be unused at `put` time. In tests, always `clone()` before the assertion reads the body.
- **Not asserting `X-Cache` headers** — without the header check, a test that always hits can
  pass even when the miss branch is broken.

---

## Gotchas

- Miniflare's in-memory cache does **not** respect `max-age` expiry during a test run; entries
  stay until explicitly `delete`d. You cannot simulate cache expiry by advancing a clock—use
  `cache.delete` instead.
- `caches.default.match` performs a method + URL match. A `POST` request will never match a `GET`
  cache entry even with the same URL.
- When the Worker sets `Vary` headers on cached responses, `cache.match` uses the same
  Vary-matching rules as a real CDN. Vary mismatches in tests produce unexpected misses; add
  `Vary: *` assertions to your test suite if your Worker sets it.
- `vi.spyOn(globalThis, "fetch")` in the Workers pool intercepts the Worker's `fetch` global, not
  the Node.js `fetch`. Ensure you restore spies in every test to avoid leakage.

---

## Verification

```bash
# Run the cache miss suite
npx vitest run test/cache-miss.test.ts

# Watch mode during development
npx vitest test/cache-miss.test.ts --reporter=verbose

# Confirm no cross-test cache leakage by running in random order
npx vitest run test/cache-miss.test.ts --sequence.shuffle
```

---

## Related

- `workers-cache-api-testing-miniflare.md`
- `vitest-cloudflare-pool-workers.md`
- `snapshot-testing-workers-responses.md`
- `vitest-workers-scheduled-cron-trigger-testing.md`

---

## Sources

- Cloudflare Cache API docs — https://developers.cloudflare.com/workers/runtime-apis/cache/
- `@cloudflare/vitest-pool-workers` — https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- Cloudflare Cache API limits — https://developers.cloudflare.com/workers/platform/limits/#cache-api
- Vitest spy docs — https://vitest.dev/api/vi.html#vi-spyon
