# Vitest Durable Objects RPC Testing

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare Workers project uses the Durable Objects RPC API (`env.MY_DO.get(id).myMethod(args)`) instead of the older `fetch`-based request model. Tests written against the `fetch` handler no longer apply. The team needs Vitest tests that exercise RPC methods directly, assert return values, verify that state mutations are visible across multiple RPC calls to the same stub, and confirm that method-level errors propagate correctly.

## Context

Durable Objects RPC (available from `workerd` 2024-04-03 onward) allows callers to invoke named methods on a DO stub as if calling a local function. The DO class extends `DurableObject` (or uses the legacy `WorkerEntrypoint` pattern), and methods become directly callable. `@cloudflare/vitest-pool-workers` supports RPC stubs transparently: `env.MY_DO.get(id)` returns a real stub backed by an in-process Miniflare instance. Tests can call RPC methods, assert return values, and check that DO storage mutations persist across calls within a test.

---

## Strategy 1 — Basic RPC method invocation and return value assertion

Test that a DO RPC method returns the expected value given a fresh state.

```typescript
// src/__tests__/counter-rpc.test.ts
import { env } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';

describe('CounterDO RPC', () => {
  it('increment returns new count', async () => {
    const id = env.COUNTER_DO.newUniqueId();
    const stub = env.COUNTER_DO.get(id);

    const result = await stub.increment(1);

    expect(result).toBe(1);
  });

  it('multiple increments accumulate', async () => {
    const id = env.COUNTER_DO.newUniqueId();
    const stub = env.COUNTER_DO.get(id);

    await stub.increment(5);
    await stub.increment(3);
    const total = await stub.increment(0);

    expect(total).toBe(8);
  });

  it('reset returns zero', async () => {
    const id = env.COUNTER_DO.newUniqueId();
    const stub = env.COUNTER_DO.get(id);

    await stub.increment(10);
    const afterReset = await stub.reset();

    expect(afterReset).toBe(0);
  });
});
```

Corresponding DO class:

```typescript
// src/counter-do.ts
import { DurableObject } from 'cloudflare:workers';

export class CounterDO extends DurableObject {
  async increment(delta: number): Promise<number> {
    const current = (await this.ctx.storage.get<number>('count')) ?? 0;
    const next = current + delta;
    await this.ctx.storage.put('count', next);
    return next;
  }

  async reset(): Promise<number> {
    await this.ctx.storage.put('count', 0);
    return 0;
  }
}
```

---

## Strategy 2 — Testing state isolation between distinct DO instances

Each `newUniqueId()` produces a separate instance with its own storage. Verify that two stubs do not share state.

```typescript
// src/__tests__/do-rpc-isolation.test.ts
import { env } from 'cloudflare:test';
import { it, expect } from 'vitest';

it('different IDs have independent state', async () => {
  const idA = env.COUNTER_DO.newUniqueId();
  const idB = env.COUNTER_DO.newUniqueId();

  const stubA = env.COUNTER_DO.get(idA);
  const stubB = env.COUNTER_DO.get(idB);

  await stubA.increment(7);
  await stubB.increment(3);

  const countA = await stubA.increment(0);
  const countB = await stubB.increment(0);

  expect(countA).toBe(7);
  expect(countB).toBe(3);
});

it('same ID from different get() calls shares state', async () => {
  const id = env.COUNTER_DO.idFromName('shared-room');
  const stub1 = env.COUNTER_DO.get(id);
  const stub2 = env.COUNTER_DO.get(id);

  await stub1.increment(4);
  const seen = await stub2.increment(0);

  expect(seen).toBe(4);
});
```

---

## Strategy 3 — Error propagation over RPC

Verify that exceptions thrown inside a DO RPC method surface as rejected Promises on the caller side.

```typescript
// src/__tests__/do-rpc-errors.test.ts
import { env } from 'cloudflare:test';
import { it, expect } from 'vitest';

it('throws RangeError when delta is negative', async () => {
  const stub = env.COUNTER_DO.get(env.COUNTER_DO.newUniqueId());

  await expect(stub.increment(-1)).rejects.toThrow(RangeError);
  await expect(stub.increment(-1)).rejects.toThrow('delta must be non-negative');
});

it('throws on read after explicit destroy', async () => {
  const id = env.COUNTER_DO.idFromName('ephemeral');
  const stub = env.COUNTER_DO.get(id);
  await stub.increment(1);
  await stub.destroy();

  await expect(stub.getCount()).rejects.toThrow();
});
```

Updated DO implementation for error cases:

```typescript
// src/counter-do.ts (extended)
import { DurableObject } from 'cloudflare:workers';

export class CounterDO extends DurableObject {
  #destroyed = false;

  async increment(delta: number): Promise<number> {
    if (this.#destroyed) throw new Error('Instance destroyed');
    if (delta < 0) throw new RangeError('delta must be non-negative');
    const current = (await this.ctx.storage.get<number>('count')) ?? 0;
    const next = current + delta;
    await this.ctx.storage.put('count', next);
    return next;
  }

  async getCount(): Promise<number> {
    if (this.#destroyed) throw new Error('Instance destroyed');
    return (await this.ctx.storage.get<number>('count')) ?? 0;
  }

  async reset(): Promise<number> {
    await this.ctx.storage.put('count', 0);
    return 0;
  }

  async destroy(): Promise<void> {
    await this.ctx.storage.deleteAll();
    this.#destroyed = true;
  }
}
```

---

## Strategy 4 — RPC methods that accept and return complex types

Test RPC methods that take structured arguments and return typed objects.

```typescript
// src/__tests__/cart-do-rpc.test.ts
import { env } from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';

interface CartItem { sku: string; qty: number; price: number }
interface CartSummary { items: CartItem[]; total: number }

describe('CartDO RPC', () => {
  let stub: DurableObjectStub;

  beforeEach(() => {
    const id = env.CART_DO.newUniqueId();
    stub = env.CART_DO.get(id);
  });

  it('adds items and computes total', async () => {
    await stub.addItem({ sku: 'A1', qty: 2, price: 9.99 });
    await stub.addItem({ sku: 'B2', qty: 1, price: 4.50 });

    const summary: CartSummary = await stub.getSummary();

    expect(summary.items).toHaveLength(2);
    expect(summary.total).toBeCloseTo(24.48, 2);
  });

  it('removes an item by SKU', async () => {
    await stub.addItem({ sku: 'X1', qty: 3, price: 2.00 });
    await stub.addItem({ sku: 'Y2', qty: 1, price: 5.00 });
    await stub.removeItem('X1');

    const summary: CartSummary = await stub.getSummary();

    expect(summary.items.every((i) => i.sku !== 'X1')).toBe(true);
    expect(summary.total).toBeCloseTo(5.00, 2);
  });

  it('returns empty summary for new cart', async () => {
    const summary: CartSummary = await stub.getSummary();

    expect(summary.items).toEqual([]);
    expect(summary.total).toBe(0);
  });
});
```

---

## Strategy 5 — Asserting transactional consistency of RPC writes

Verify that a DO RPC method that performs a `transaction()` either commits all writes or none.

```typescript
// src/__tests__/do-rpc-transaction.test.ts
import { env } from 'cloudflare:test';
import { it, expect } from 'vitest';

it('rolls back all writes when transaction throws', async () => {
  const id = env.LEDGER_DO.idFromName('test-ledger');
  const stub = env.LEDGER_DO.get(id);

  await stub.credit('alice', 100);

  // This transfer will fail partway through (insufficient funds guard)
  await expect(
    stub.transfer({ from: 'alice', to: 'bob', amount: 200 })
  ).rejects.toThrow('insufficient funds');

  // Alice's balance must be unchanged — no partial debit
  const balance = await stub.getBalance('alice');
  expect(balance).toBe(100);

  // Bob must not have been credited
  const bobBalance = await stub.getBalance('bob');
  expect(bobBalance).toBe(0);
});
```

---

## Anti-patterns

- Calling RPC methods on a stub obtained from `idFromName` without a unique suffix per test — tests share DO state because the named ID resolves to the same instance.
- Using `vi.mock` to mock DO RPC methods — the Workers pool provides real stubs; mocking bypasses Miniflare's storage and breaks cross-call state assertions.
- Asserting DO storage directly via `stub.ctx.storage` from the test — `ctx` is not accessible from the caller side. Assert via the RPC interface only.
- Forgetting `await` on RPC calls — a missing `await` means state changes may not be visible in the assertion that follows, producing intermittent test failures.
- Using the same `newUniqueId()` across `describe` blocks by storing it at module scope — the ID is shared across all tests in all blocks, causing state contamination.

---

## Gotchas

- DO RPC requires the class to extend `DurableObject` from `cloudflare:workers` (not the legacy `Request`-handler pattern). Legacy DOs that only implement `fetch()` are not callable via RPC.
- Vitest pool workers automatically wire bindings declared in `wrangler.toml` / `vitest.config.ts` `miniflare.durableObjects`. Missing wiring causes `env.MY_DO` to be `undefined` at test time.
- RPC method names that start with underscore (`_myMethod`) are private by convention and are not callable from outside the DO. Tests targeting such methods must refactor the DO to expose a public interface.
- In Miniflare, each test file runs in a separate worker, but DO instances persist for the lifetime of that worker process. Use `newUniqueId()` per test (not `idFromName` with a fixed string) to prevent cross-test leakage within the same file.
- RPC serialisation uses the same structured-clone algorithm as `postMessage`. Types that are not structured-cloneable (e.g., functions, class instances with methods) will throw a `DataCloneError` at the RPC boundary — prefer plain objects.

---

## Verification

```bash
# Run only DO RPC tests
npx vitest run --reporter=verbose src/__tests__/*-rpc*

# Run in random order to detect ordering dependencies
npx vitest run --sequence.shuffle.tests src/__tests__/*-rpc*

# Watch mode during development
npx vitest --reporter=verbose src/__tests__/counter-rpc.test.ts
```

---

## Related

- `vitest-durable-objects-storage-reset-isolation.md` — storage isolation between tests
- `durable-objects-miniflare-fake-timers.md` — alarm and timer testing for DOs
- `durable-objects-alarm-testing-miniflare.md` — alarm lifecycle testing
- `vitest-cloudflare-pool-workers.md` — pool configuration reference
- `workers-service-bindings-vitest-testing.md` — service binding RPC patterns

---

## Sources

- https://developers.cloudflare.com/durable-objects/api/rpc/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/durable-objects/api/base/
- https://miniflare.dev/storage/durable-objects
- https://vitest.dev/guide/test-context.html
