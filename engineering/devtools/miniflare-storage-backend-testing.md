# Miniflare Custom Storage Backend Testing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need to test Workers that use R2, KV, or Durable Object storage with a custom or
in-memory backend — not the default SQLite-backed Miniflare store. Common scenarios:
testing with pre-seeded fixture data, verifying idempotency by resetting the store
between each test, or injecting a backend that counts reads/writes for coverage
assertions.

## Context

Miniflare v3/v4 (which ships inside `@cloudflare/vitest-pool-workers`) exposes a
`MemoryStorage` class and accepts custom storage factories. You can swap the default
file-backed store for a pure in-memory map, or for a proxy that wraps any store with
observability hooks. Tests run faster and don't leave stale SQLite files behind.

Dependencies: `miniflare@^4`, `@cloudflare/vitest-pool-workers@^0.5`,
`vitest@^2`, TypeScript 5.5+.

---

## 1. In-memory KV backend for Vitest

```typescript
// tests/helpers/memory-kv.ts
import { createMemoryStorage } from "miniflare";
import type { KVNamespace } from "@cloudflare/workers-types";

/**
 * Returns a fresh in-memory KV namespace pre-seeded with fixture data.
 * Safe to call per-test — each call creates an isolated store.
 */
export async function makeMemoryKV(
  seed: Record<string, string> = {}
): Promise<KVNamespace> {
  const storage = createMemoryStorage();
  const ns = await storage.namespace("TEST_KV");

  for (const [key, value] of Object.entries(seed)) {
    await ns.put(key, value);
  }

  return ns as unknown as KVNamespace;
}
```

## 2. Spy storage — tracking reads and writes

```typescript
// tests/helpers/spy-storage.ts
import type { Storage, StorageKey, StorageValue } from "miniflare";

export interface SpyStorageMetrics {
  reads: number;
  writes: number;
  deletes: number;
}

export class SpyStorage implements Storage {
  readonly metrics: SpyStorageMetrics = { reads: 0, writes: 0, deletes: 0 };

  constructor(private readonly inner: Storage) {}

  async get(key: StorageKey): Promise<StorageValue | undefined> {
    this.metrics.reads++;
    return this.inner.get(key);
  }

  async put(key: StorageKey, value: StorageValue): Promise<void> {
    this.metrics.writes++;
    return this.inner.put(key, value);
  }

  async delete(key: StorageKey): Promise<boolean> {
    this.metrics.deletes++;
    return this.inner.delete(key);
  }

  async list(options?: { prefix?: string; limit?: number; cursor?: string }) {
    return this.inner.list(options);
  }
}
```

## 3. Miniflare instance with custom storage factory

```typescript
// tests/helpers/miniflare-custom-store.ts
import { Miniflare, createMemoryStorage } from "miniflare";
import { SpyStorage } from "./spy-storage.js";

export function createTestMiniflare(spyEnabled = false) {
  const baseStorage = createMemoryStorage();
  const storage = spyEnabled ? new SpyStorage(baseStorage) : baseStorage;

  const mf = new Miniflare({
    script: `
      export default {
        async fetch(request, env) {
          const url = new URL(request.url);
          if (url.pathname === "/put") {
            await env.KV.put("k", "v");
            return new Response("ok");
          }
          return new Response(await env.KV.get("k"));
        }
      }
    `,
    modules: true,
    kvNamespaces: { KV: "test-kv" },
    // Provide the custom storage factory
    kvStorage: () => storage,
  });

  return { mf, storage };
}
```

## 4. Vitest test using the custom backend

```typescript
// tests/kv-worker.test.ts
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { createTestMiniflare } from "./helpers/miniflare-custom-store.js";
import type { SpyStorage } from "./helpers/spy-storage.js";

describe("KV Worker with custom storage", () => {
  let mf: Awaited<ReturnType<typeof createTestMiniflare>>["mf"];
  let storage: SpyStorage;

  beforeEach(() => {
    const result = createTestMiniflare(true);
    mf = result.mf;
    storage = result.storage as SpyStorage;
  });

  afterEach(() => mf.dispose());

  it("writes to KV and returns the value", async () => {
    await mf.dispatchFetch("http://localhost/put");
    const res = await mf.dispatchFetch("http://localhost/");

    expect(await res.text()).toBe("v");
    expect(storage.metrics.writes).toBe(1);
    expect(storage.metrics.reads).toBe(1);
  });

  it("returns null for missing keys", async () => {
    const res = await mf.dispatchFetch("http://localhost/");
    expect(await res.text()).toBe("");
    expect(storage.metrics.reads).toBe(1);
    expect(storage.metrics.writes).toBe(0);
  });
});
```

## 5. Resetting store between describe blocks

```typescript
// tests/helpers/reset-storage.ts
import { createMemoryStorage } from "miniflare";

/**
 * Utility that returns a fresh storage factory function.
 * Pass the returned factory to Miniflare's kvStorage / r2Storage options.
 */
export function freshStorageFactory() {
  let current = createMemoryStorage();
  return {
    factory: () => current,
    reset() {
      current = createMemoryStorage();
    },
  };
}
```

## 6. R2 custom backend with fixture blobs

```typescript
// tests/helpers/r2-fixture-storage.ts
import { createMemoryStorage } from "miniflare";

export async function createR2WithFixtures(
  fixtures: Record<string, Blob>
) {
  const storage = createMemoryStorage();
  const bucket = await storage.r2Bucket("TEST_BUCKET");

  for (const [key, blob] of Object.entries(fixtures)) {
    const arrayBuffer = await blob.arrayBuffer();
    await bucket.put(key, arrayBuffer, {
      httpMetadata: { contentType: blob.type },
    });
  }

  return { storage, bucket };
}
```

## Anti-patterns

- Using the default SQLite Miniflare store in unit tests — tests then depend on
  filesystem state and can interfere with each other when run in parallel.
- Not calling `mf.dispose()` in `afterEach` — Miniflare instances hold open SQLite
  connections, leaking file handles across test files.
- Storing spy state in module-level variables — state bleeds between tests that import
  the same module; always construct fresh instances per test.

## Gotchas

- `createMemoryStorage` is only exported from the `miniflare` package directly, not
  from `@cloudflare/vitest-pool-workers`. When the pool runner creates its own
  Miniflare instance you cannot swap the storage; the custom-backend pattern works best
  for self-managed Miniflare instances in integration tests outside the pool.
- The `SpyStorage` class must implement every method (including `list`) or Miniflare
  throws a runtime type error when KV performs internal listing during cleanup.
- Memory storage does not persist TTL-based expiry unless you implement it in your
  custom backend — tests that rely on KV TTL must handle expiry explicitly.

## Verification

```bash
# Run only the custom-storage tests
pnpm vitest run tests/kv-worker.test.ts

# Confirm no SQLite files are left behind
ls /tmp/*.sqlite 2>/dev/null || echo "no stale sqlite files"
```

## Related

- `miniflare-custom-plugins-bindings.md`
- `vitest-workers-miniflare-testing-setup.md`
- `vitest-pool-workers-cloudflare-test-api.md`

## Sources

- https://miniflare.dev/storage/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/miniflare
- https://developers.cloudflare.com/workers/testing/miniflare/
