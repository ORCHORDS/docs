# Chaos Testing KV Eviction Simulation in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Cloudflare Worker caches expensive computations in KV and assumes cached values are always present after a `put`. Under traffic spikes, KV cache misses spike and your Worker throws because the code path after a `null` return from `kv.get()` was never tested. You need chaos tests that simulate KV eviction (returning `null` for keys that were just written) to validate that your Worker handles cache misses gracefully, falls back to the origin, and does not corrupt downstream state.

## Context

Cloudflare KV uses an eventually-consistent edge cache with a TTL-based eviction model. In production, `kv.get()` can return `null` for a key that was written milliseconds ago if the local edge cache has not propagated or if the entry was evicted under memory pressure. Miniflare's in-memory KV store does not simulate this behavior by default—it always returns the latest value. Chaos tests inject deliberate `null` returns at the mock layer to validate fallback logic without needing real KV eviction conditions.

---

## 1. Miniflare KV Proxy with Configurable Eviction Rate

```typescript
// tests/helpers/chaos-kv.ts
import type { KVNamespace } from '@cloudflare/workers-types';

export type ChaosKVOptions = {
  evictionRate: number;       // 0.0–1.0 probability of returning null on get
  evictOnlyKeys?: string[];   // if set, only evict these key prefixes
  log?: boolean;
};

export function createChaosKV(real: KVNamespace, opts: ChaosKVOptions): KVNamespace {
  return new Proxy(real, {
    get(target, prop) {
      if (prop !== 'get') return Reflect.get(target, prop);

      return async (key: string, options?: unknown) => {
        const shouldEvict =
          Math.random() < opts.evictionRate &&
          (!opts.evictOnlyKeys || opts.evictOnlyKeys.some((p) => key.startsWith(p)));

        if (shouldEvict) {
          if (opts.log) console.warn(`[ChaosKV] Simulating eviction for key: ${key}`);
          return null;
        }

        return (target as KVNamespace).get(key, options as never);
      };
    },
  }) as unknown as KVNamespace;
}
```

---

## 2. Vitest Test: Fallback on Cache Miss

```typescript
// tests/chaos/kv-eviction.test.ts
import { env } from 'cloudflare:test';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createChaosKV } from '../helpers/chaos-kv';
import { getProductPrice } from '../../src/services/product-price';

// getProductPrice: tries KV first, falls back to DB, then re-caches
const PRODUCT_ID = 'prod-abc123';

describe('KV eviction chaos tests', () => {
  beforeEach(async () => {
    // Seed the KV with a value that may or may not be returned
    await env.PRODUCT_CACHE.put(PRODUCT_ID, JSON.stringify({ price: 999 }), {
      expirationTtl: 60,
    });
  });

  it('returns correct price when KV is evicted (100% eviction rate)', async () => {
    const chaosKV = createChaosKV(env.PRODUCT_CACHE, {
      evictionRate: 1.0,
      log: true,
    });

    // Inject chaos KV into service
    const price = await getProductPrice(PRODUCT_ID, chaosKV, env.DB);

    // Should fall back to DB and return correct price
    expect(price).toBe(999);
  });

  it('does not throw when KV returns null', async () => {
    const chaosKV = createChaosKV(env.PRODUCT_CACHE, { evictionRate: 1.0 });

    await expect(
      getProductPrice(PRODUCT_ID, chaosKV, env.DB)
    ).resolves.not.toThrow();
  });

  it('re-populates KV after cache miss', async () => {
    const chaosKV = createChaosKV(env.PRODUCT_CACHE, { evictionRate: 1.0 });
    const putSpy = vi.spyOn(env.PRODUCT_CACHE, 'put');

    await getProductPrice(PRODUCT_ID, chaosKV, env.DB);

    expect(putSpy).toHaveBeenCalledWith(
      PRODUCT_ID,
      expect.stringContaining('999'),
      expect.objectContaining({ expirationTtl: expect.any(Number) })
    );
  });
});
```

---

## 3. The Service Under Test

```typescript
// src/services/product-price.ts
import type { KVNamespace, D1Database } from '@cloudflare/workers-types';

export async function getProductPrice(
  productId: string,
  kv: KVNamespace,
  db: D1Database
): Promise<number> {
  // Cache-first lookup
  const cached = await kv.get(productId, 'json') as { price: number } | null;
  if (cached !== null) {
    return cached.price;
  }

  // Fallback to D1
  const row = await db
    .prepare('SELECT price FROM products WHERE id = ?')
    .bind(productId)
    .first<{ price: number }>();

  if (!row) {
    throw new Error(`Product not found: ${productId}`);
  }

  // Re-populate cache
  await kv.put(productId, JSON.stringify({ price: row.price }), {
    expirationTtl: 300,
  });

  return row.price;
}
```

---

## 4. Probabilistic Chaos: Statistical Validation

Run the function many times under partial eviction and assert statistical properties:

```typescript
// tests/chaos/kv-eviction-statistical.test.ts
import { env } from 'cloudflare:test';
import { it, expect, beforeAll } from 'vitest';
import { createChaosKV } from '../helpers/chaos-kv';
import { getProductPrice } from '../../src/services/product-price';

const ITERATIONS = 200;
const EVICTION_RATE = 0.5;

beforeAll(async () => {
  await env.PRODUCT_CACHE.put('prod-stat', JSON.stringify({ price: 42 }), {
    expirationTtl: 3600,
  });
  await env.DB.prepare(
    "INSERT OR REPLACE INTO products (id, price) VALUES ('prod-stat', 42)"
  ).run();
});

it('always returns correct price regardless of eviction', async () => {
  const chaosKV = createChaosKV(env.PRODUCT_CACHE, { evictionRate: EVICTION_RATE });

  const results = await Promise.all(
    Array.from({ length: ITERATIONS }, () =>
      getProductPrice('prod-stat', chaosKV, env.DB)
    )
  );

  // Every invocation must return 42, regardless of eviction
  expect(results.every((r) => r === 42)).toBe(true);
  expect(results).toHaveLength(ITERATIONS);
});
```

---

## 5. Chaos Middleware: Inject at the Fetch Level

For integration tests that go through a full Worker fetch, inject chaos at the `env` level:

```typescript
// tests/chaos/kv-fetch-chaos.test.ts
import { createExecutionContext, waitOnExecutionContext } from 'cloudflare:test';
import { it, expect } from 'vitest';
import { createChaosKV } from '../helpers/chaos-kv';
import worker from '../../src/index';
import { env } from 'cloudflare:test';

it('Worker returns 200 even when KV is fully evicted', async () => {
  const chaosEnv = {
    ...env,
    PRODUCT_CACHE: createChaosKV(env.PRODUCT_CACHE, { evictionRate: 1.0 }),
  };

  const request = new Request('https://example.com/products/prod-abc123');
  const ctx = createExecutionContext();

  const response = await worker.fetch(request, chaosEnv, ctx);
  await waitOnExecutionContext(ctx);

  expect(response.status).toBe(200);
  const body = await response.json<{ price: number }>();
  expect(body.price).toBeGreaterThan(0);
});
```

---

## Anti-patterns

- **Testing only the happy path (KV always returns a value)**: Production KV eviction is real. Code that assumes `kv.get()` never returns `null` will fail in production.
- **Using `vi.spyOn(env.KV, 'get').mockResolvedValue(null)` for all calls**: This breaks setup and teardown if they also use `kv.get`. Scope the mock to a specific test or key range.
- **Not re-seeding KV after chaos tests**: Chaos tests that call the real `put` path may leave stale or unexpected values. Clean up with `kv.delete()` in `afterEach`.
- **Chaos rate of exactly 1.0 without a fallback**: 100% eviction tests are only useful if the fallback is implemented. Test both 100% and partial rates.
- **Ignoring the `put` path in chaos scenarios**: If the `put` after a cache miss also fails (network error, size limit), the service must handle that gracefully too.

---

## Gotchas

- Miniflare's KV does not enforce the 25 MB value size limit or 512-byte key limit by default. Add a wrapper that enforces these limits in your chaos KV if you want to catch size-related bugs.
- KV `getWithMetadata()` returns `{ value: null, metadata: null }` on a miss, not just `null`. If your code uses `getWithMetadata`, your chaos proxy must return the correct shape.
- The `evictionRate` in tests should not use `Math.random()` unseeded—use a seeded PRNG for reproducible failures. Import `seedrandom` or use a simple LCG.
- Cloudflare KV has eventual consistency across regions; `put` then `get` from a different region may return the old value for up to 60 seconds. This is not a bug; design your Worker accordingly.
- Chaos tests that exercise the DB fallback path require the test D1 to be seeded with matching data. Seed before chaos, assert after.

---

## Verification

```bash
# Run chaos tests with Vitest
npx vitest run tests/chaos/

# Run statistical test with verbose output
npx vitest run tests/chaos/kv-eviction-statistical.test.ts --reporter=verbose

# Confirm service handles null KV response end-to-end
npx vitest run tests/chaos/kv-fetch-chaos.test.ts
```

---

## Related

- `kv-testing-miniflare.md`
- `miniflare-kv-ttl-expiry-testing.md`
- `chaos-engineering-cloudflare-workers.md`
- `chaos-durable-objects-hibernation-testing.md`
- `resilience-circuit-breaker-testing.md`

---

## Sources

- Cloudflare KV consistency model: https://developers.cloudflare.com/kv/concepts/how-kv-works/
- Miniflare KV testing: https://developers.cloudflare.com/workers/testing/miniflare/
- Vitest mocking guide: https://vitest.dev/guide/mocking.html
- Cloudflare KV limits: https://developers.cloudflare.com/kv/platform/limits/
