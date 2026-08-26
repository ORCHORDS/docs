# Vitest Workers KV Namespace Testing Patterns

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Worker reads, writes, and lists from KV namespaces and you need deterministic unit tests that
cover cache hits, expiration TTLs, metadata handling, and list-cursor pagination without real
network round-trips.

## Context
`@cloudflare/vitest-pool-workers` runs tests inside a Miniflare Workers sandbox, providing an
in-memory KV implementation that faithfully models the production API: `put`/`get`/`list`/`delete`,
expiration via `expirationTtl`, metadata, value types (`text`, `json`, `arrayBuffer`, `stream`),
and list cursors. Bindings declared in `wrangler.toml` under `[[kv_namespaces]]` are automatically
wired up; you can also add ephemeral bindings in `vitest.config.ts` for test-only namespaces.

## Configuring KV Bindings for Tests

```toml
# wrangler.toml
[[kv_namespaces]]
binding = "CACHE"
id = "abc123"

[[kv_namespaces]]
binding = "SESSIONS"
id = "def456"
```

```ts
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          // Add a test-only namespace not in wrangler.toml
          kvNamespaces: ["TEMP_STORE"],
        },
      },
    },
  },
});
```

## Basic Put / Get / Delete Tests

```ts
// src/kv.test.ts
import { env } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";

describe("KV basic operations", () => {
  beforeEach(async () => {
    // Miniflare KV persists within the test run; clear between tests
    const keys = await env.CACHE.list();
    await Promise.all(keys.keys.map((k) => env.CACHE.delete(k.name)));
  });

  it("stores and retrieves a string value", async () => {
    await env.CACHE.put("greeting", "hello world");
    const value = await env.CACHE.get("greeting");
    expect(value).toBe("hello world");
  });

  it("returns null for a missing key", async () => {
    const value = await env.CACHE.get("does-not-exist");
    expect(value).toBeNull();
  });

  it("deletes a key", async () => {
    await env.CACHE.put("temp", "value");
    await env.CACHE.delete("temp");
    expect(await env.CACHE.get("temp")).toBeNull();
  });

  it("stores and retrieves JSON", async () => {
    const data = { userId: 42, role: "admin" };
    await env.CACHE.put("user:42", JSON.stringify(data));
    const raw = await env.CACHE.get("user:42", "json");
    expect(raw).toEqual(data);
  });
});
```

## Testing Metadata

```ts
// src/kv-metadata.test.ts
import { env } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";

interface UserMeta {
  createdAt: number;
  version: number;
}

describe("KV metadata", () => {
  beforeEach(async () => {
    const list = await env.CACHE.list();
    await Promise.all(list.keys.map((k) => env.CACHE.delete(k.name)));
  });

  it("stores metadata alongside the value", async () => {
    const meta: UserMeta = { createdAt: Date.now(), version: 3 };
    await env.CACHE.put("user:99", '{"name":"Alice"}', { metadata: meta });

    const result = await env.CACHE.getWithMetadata<string, UserMeta>("user:99");
    expect(result.value).toBe('{"name":"Alice"}');
    expect(result.metadata?.version).toBe(3);
  });

  it("returns null metadata when none was stored", async () => {
    await env.CACHE.put("plain", "value");
    const result = await env.CACHE.getWithMetadata("plain");
    expect(result.metadata).toBeNull();
  });
});
```

## Testing TTL / Expiration Behaviour

Miniflare's KV does not advance time automatically. Use fake timers to simulate TTL expiry:

```ts
// src/kv-ttl.test.ts
import { env } from "cloudflare:test";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

describe("KV TTL expiration", () => {
  beforeEach(async () => {
    vi.useFakeTimers();
    const list = await env.CACHE.list();
    await Promise.all(list.keys.map((k) => env.CACHE.delete(k.name)));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("key is accessible before TTL expires", async () => {
    await env.CACHE.put("session:1", "active", { expirationTtl: 60 });
    // Advance 30 seconds — key still present
    vi.advanceTimersByTime(30_000);
    const value = await env.CACHE.get("session:1");
    expect(value).toBe("active");
  });

  it("key is absent after TTL expires in Miniflare", async () => {
    // Miniflare checks expiration at access time using Date.now()
    // Fake timers advance Date.now(), so expired keys return null
    await env.CACHE.put("short", "data", { expirationTtl: 10 });
    vi.advanceTimersByTime(11_000);
    const value = await env.CACHE.get("short");
    expect(value).toBeNull();
  });
});
```

## Testing List with Cursor Pagination

```ts
// src/kv-list.test.ts
import { env } from "cloudflare:test";
import { describe, it, expect, beforeAll, afterAll } from "vitest";

describe("KV list pagination", () => {
  beforeAll(async () => {
    // Seed 15 keys with a common prefix
    await Promise.all(
      Array.from({ length: 15 }, (_, i) =>
        env.CACHE.put(`item:${String(i).padStart(3, "0")}`, `value-${i}`)
      )
    );
  });

  afterAll(async () => {
    const list = await env.CACHE.list({ prefix: "item:" });
    await Promise.all(list.keys.map((k) => env.CACHE.delete(k.name)));
  });

  it("returns first page with limit", async () => {
    const page1 = await env.CACHE.list({ prefix: "item:", limit: 5 });
    expect(page1.keys).toHaveLength(5);
    expect(page1.list_complete).toBe(false);
    expect(page1.cursor).toBeTruthy();
  });

  it("retrieves all keys across paginated requests", async () => {
    const allKeys: string[] = [];
    let cursor: string | undefined;

    do {
      const page = await env.CACHE.list({ prefix: "item:", limit: 5, cursor });
      allKeys.push(...page.keys.map((k) => k.name));
      cursor = page.list_complete ? undefined : page.cursor;
    } while (cursor);

    expect(allKeys).toHaveLength(15);
    expect(allKeys[0]).toBe("item:000");
    expect(allKeys[14]).toBe("item:014");
  });
});
```

## Anti-patterns
- Do not call `env.KV.put(…)` inside a `beforeAll` without a matching `afterAll` cleanup — KV
  state persists across tests in the same pool worker process, causing inter-test pollution.
- Do not test exact expiration timestamps against wall-clock time; use fake timers or assert that
  a key is absent after advancing time, not at a specific epoch second.
- Do not use `list()` without a `prefix` in production-mirroring tests; the in-memory store will
  return keys from other tests if cleanup is imperfect.
- Do not assume KV `list` returns keys in insertion order; Miniflare returns them lexicographically,
  matching production behaviour.

## Gotchas
- Miniflare's KV store is scoped per namespace binding; `env.CACHE` and `env.SESSIONS` are
  separate stores even if both are declared as in-memory in tests.
- `expirationTtl` must be a positive integer ≥ 60 in production; Miniflare accepts smaller values,
  so tests using TTL < 60 will pass locally but fail in production.
- `get(key, "json")` returns `null` rather than throwing when the stored value is not valid JSON;
  always validate the shape with `zod` or a type guard.
- Clearing KV between tests with `list()` + `delete()` is O(n) for the number of keys; for large
  fixture sets, prefer unique prefixes per test rather than deleting everything.

## Verification

```bash
# Run KV tests only
pnpm vitest run src/kv.test.ts src/kv-metadata.test.ts src/kv-list.test.ts

# Run with verbose output to see each assertion
pnpm vitest run --reporter=verbose src/

# Check coverage of KV-touching code paths
pnpm vitest run --coverage src/
```

## Related
- `miniflare-d1-test-seeding-fixtures.md` — seeding D1 with fixtures for tests
- `vitest-workers-miniflare-testing-setup.md` — pool configuration fundamentals
- `miniflare-storage-backend-testing.md` — R2 and Durable Object storage testing
- `wrangler-dev-local-d1-r2-kv.md` — local KV in wrangler dev (not test)

## Sources
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://miniflare.dev/storage/kv
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
