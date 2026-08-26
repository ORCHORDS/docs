# Property-Based Testing for Workers Business Logic with fast-check

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Unit tests cover only the cases you think of. A pricing function passes all hand-written tests, then a customer submits a fractional-cent amount and the Worker throws. Property-based testing (PBT) generates thousands of inputs automatically, surfacing edge cases before production does.

## Context

Cloudflare Workers run in the V8 isolate; `fast-check` is a pure-JS property-based testing library that integrates directly with Vitest. It needs no network and no Worker runtime — business-logic code can be extracted and tested in Node/Vitest without Miniflare, keeping the suite fast. Stateful tests (KV, D1) require Miniflare via `@cloudflare/vitest-pool-workers`.

---

## Solution

### 1. Install dependencies

```bash
npm install --save-dev fast-check vitest @cloudflare/vitest-pool-workers
```

### 2. Arbitrary generators for domain types

```typescript
// test/arbitraries.ts
import fc from 'fast-check';

export interface Price {
  amount: number;   // integer cents
  currency: 'USD' | 'EUR' | 'GBP';
}

export interface LineItem {
  sku: string;
  quantity: number;
  unitPrice: Price;
}

/** Generates a valid positive-integer cent amount (0–999_999). */
export const arbCents = fc.integer({ min: 0, max: 999_999 });

/** Generates one of the supported ISO currency codes. */
export const arbCurrency = fc.constantFrom('USD', 'EUR', 'GBP') as fc.Arbitrary<Price['currency']>;

/** Generates a structurally valid Price object. */
export const arbPrice: fc.Arbitrary<Price> = fc.record({
  amount: arbCents,
  currency: arbCurrency,
});

/** Generates a SKU: 3 uppercase letters followed by 4 digits. */
export const arbSku = fc
  .tuple(fc.stringOf(fc.constantFrom(...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')), { minLength: 3, maxLength: 3 }),
         fc.stringOf(fc.constantFrom(...'0123456789'.split('')), { minLength: 4, maxLength: 4 }))
  .map(([letters, digits]) => letters + digits);

/** Generates a valid LineItem. */
export const arbLineItem: fc.Arbitrary<LineItem> = fc.record({
  sku: arbSku,
  quantity: fc.integer({ min: 1, max: 1_000 }),
  unitPrice: arbPrice,
});

/** Generates a non-empty array of LineItems sharing the same currency. */
export const arbCart = arbCurrency.chain((currency) =>
  fc.array(
    fc.record({
      sku: arbSku,
      quantity: fc.integer({ min: 1, max: 1_000 }),
      unitPrice: fc.record({ amount: arbCents, currency: fc.constant(currency) }),
    }),
    { minLength: 1, maxLength: 20 },
  ),
);
```

### 3. Property definitions for business invariants

```typescript
// src/pricing.ts  (pure business logic — no Worker bindings)
export function calculateTotal(items: LineItem[]): number {
  return items.reduce((sum, item) => sum + item.quantity * item.unitPrice.amount, 0);
}

export function applyDiscount(total: number, discountBps: number): number {
  if (discountBps < 0 || discountBps > 10_000) throw new RangeError('discount out of range');
  return Math.round(total * (1 - discountBps / 10_000));
}

export function splitEvenly(total: number, parts: number): number[] {
  if (parts <= 0) throw new RangeError('parts must be positive');
  const share = Math.floor(total / parts);
  const remainder = total - share * parts;
  return Array.from({ length: parts }, (_, i) => (i < remainder ? share + 1 : share));
}
```

```typescript
// test/pricing.property.test.ts
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { calculateTotal, applyDiscount, splitEvenly } from '../src/pricing';
import { arbCart } from './arbitraries';

describe('calculateTotal — properties', () => {
  it('is never negative', () => {
    fc.assert(
      fc.property(arbCart, (items) => {
        expect(calculateTotal(items)).toBeGreaterThanOrEqual(0);
      }),
    );
  });

  it('is monotone: adding an item can only increase the total', () => {
    fc.assert(
      fc.property(arbCart, fc.record({ sku: fc.string(), quantity: fc.integer({ min: 1, max: 100 }), unitPrice: fc.record({ amount: fc.integer({ min: 1, max: 10_000 }), currency: fc.constant('USD' as const) }) }), (items, extra) => {
        const before = calculateTotal(items);
        const after  = calculateTotal([...items, extra]);
        expect(after).toBeGreaterThanOrEqual(before);
      }),
    );
  });

  it('sum of split equals total', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 1_000_000 }),
        fc.integer({ min: 1, max: 50 }),
        (total, parts) => {
          const split = splitEvenly(total, parts);
          expect(split.reduce((a, b) => a + b, 0)).toBe(total);
          expect(split.length).toBe(parts);
          const max = Math.max(...split);
          const min = Math.min(...split);
          expect(max - min).toBeLessThanOrEqual(1);
        },
      ),
    );
  });
});

describe('applyDiscount — properties', () => {
  it('never increases total', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 1_000_000 }),
        fc.integer({ min: 0, max: 10_000 }),
        (total, bps) => {
          expect(applyDiscount(total, bps)).toBeLessThanOrEqual(total);
        },
      ),
    );
  });

  it('full discount (10 000 bps) always yields 0', () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 1_000_000 }), (total) => {
        expect(applyDiscount(total, 10_000)).toBe(0);
      }),
    );
  });
});
```

### 4. Shrinking on failure

fast-check shrinks automatically. When a property fails, it reports the minimal counter-example:

```
Property failed after 1 tests
{ seed: -1234567, path: "0:1", endOnFailure: true }
Counterexample: [{ sku: 'AAA0000', quantity: 1, unitPrice: { amount: 0, currency: 'USD' } }]
```

To reproduce deterministically:

```typescript
fc.assert(
  fc.property(arbCart, (items) => { /* ... */ }),
  { seed: -1234567, path: '0:1' },  // paste from failure output
);
```

### 5. Stateful model testing for KV operations

```typescript
// test/kv-model.property.test.ts
import { describe, it } from 'vitest';
import fc from 'fast-check';
import { env } from 'cloudflare:test';  // Miniflare KV binding

// Model: a plain Map that mirrors expected KV state
type Model = Map<string, string>;

const PutCommand = fc.record({
  kind: fc.constant('put' as const),
  key: fc.string({ minLength: 1, maxLength: 64 }),
  value: fc.string({ maxLength: 256 }),
});

const DeleteCommand = fc.record({
  kind: fc.constant('delete' as const),
  key: fc.string({ minLength: 1, maxLength: 64 }),
});

const GetCommand = fc.record({
  kind: fc.constant('get' as const),
  key: fc.string({ minLength: 1, maxLength: 64 }),
});

const arbCommand = fc.oneof(PutCommand, DeleteCommand, GetCommand);

describe('KV stateful model', () => {
  it('KV mirrors the model Map under any command sequence', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(arbCommand, { minLength: 1, maxLength: 40 }),
        async (commands) => {
          const model: Model = new Map();
          // Reset KV between runs by listing and deleting all keys
          const listed = await env.MY_KV.list();
          await Promise.all(listed.keys.map((k) => env.MY_KV.delete(k.name)));

          for (const cmd of commands) {
            if (cmd.kind === 'put') {
              await env.MY_KV.put(cmd.key, cmd.value);
              model.set(cmd.key, cmd.value);
            } else if (cmd.kind === 'delete') {
              await env.MY_KV.delete(cmd.key);
              model.delete(cmd.key);
            } else {
              const actual = await env.MY_KV.get(cmd.key);
              const expected = model.get(cmd.key) ?? null;
              if (actual !== expected) return false;
            }
          }
          return true;
        },
      ),
      { numRuns: 50 },
    );
  });
});
```

---

## Implementation Details

- `fc.assert` runs 100 examples by default; increase with `{ numRuns: 500 }` for CI.
- `fc.record` is composable: build complex generators from simple primitives.
- `fc.chain` lets a later arbitrary depend on an earlier value (same-currency cart above).
- Vitest's `expect` matchers work inside property callbacks; throw or return `false` to signal failure.
- Stateful tests need `asyncProperty` and `fc.assert` awaited.

---

## Anti-patterns

- **Generating invalid inputs and expecting no throw** — test the validator separately; PBT should test invariants of *valid* domain values.
- **Using `Math.random()` inside a property** — defeats reproducibility; use `fc.integer` or `fc.float` instead.
- **Too-wide arbitrary for shrinking to be useful** — constrain ranges to the realistic domain; `fc.integer({ min: 0, max: Number.MAX_SAFE_INTEGER })` makes shrinking slow.
- **Stateful test that shares KV without cleanup** — always reset bindings between runs to avoid contamination.

---

## Gotchas

- `fast-check` v3+ ships ESM-only; add `"type": "module"` to `package.json` or use `import()` in a `.mjs` test helper.
- `fc.asyncProperty` with Miniflare can be slow; set `testTimeout: 30_000` in `vitest.config.ts`.
- `fc.string()` generates Unicode by default including null bytes; add `{ unit: 'grapheme-composite' }` or restrict to ASCII for HTTP header values.

---

## Verification

```bash
# Run property tests only
npx vitest run --reporter=verbose test/*.property.test.ts

# Run with a fixed seed for CI reproducibility
FC_GLOBAL_SEED=42 npx vitest run
```

Expected output: all properties pass; on failure the counter-example and seed are printed.

---

## Related

- `documentation/categories/testing/vitest-workers-miniflare.md`
- `documentation/categories/testing/workers-vitest-d1-fixtures.md`
- `documentation/categories/testing/workers-test-data-factory-d1.md`

---

## Sources

- https://fast-check.dev/docs/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://github.com/dubzzz/fast-check/blob/main/packages/fast-check/README.md
