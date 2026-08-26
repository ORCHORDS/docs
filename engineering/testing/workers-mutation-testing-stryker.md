# Mutation Testing with Stryker for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers codebase has 85 % line coverage, but a critical pricing bug ships to production anyway. Coverage metrics tell you which lines ran during tests, not whether the tests would catch a wrong calculation. You need a mutation score: proof that your tests detect real defects.

## Context

Mutation testing works by introducing small, deliberate code changes ("mutants") — e.g. flipping `>` to `>=`, replacing `+` with `-`, deleting a `return` statement — and then running the test suite against each mutant. If the tests still pass, the mutant "survives", revealing a gap in test quality. If the tests fail, the mutant is "killed": your tests caught the defect.

Stryker is the de-facto mutation testing framework for JavaScript/TypeScript. `@stryker-mutator/vitest-runner` integrates with Vitest, which is the recommended test runner for Cloudflare Workers (via `@cloudflare/vitest-pool-workers`).

Mutation testing is expensive: a test suite with 200 tests may run 2 000–10 000 times (one per mutant). Target only business-critical modules; exclude glue code, generated files, and Worker entry points.

## Solution

```typescript
// stryker.config.ts
import type { Config } from '@stryker-mutator/core';

export default {
  testRunner: 'vitest',
  vitest: {
    configFile: 'vitest.config.ts',
  },
  mutate: [
    // Only mutate business-critical modules
    'src/pricing/**/*.ts',
    'src/inventory/**/*.ts',
    'src/auth/**/*.ts',
    // Exclude generated and type-only files
    '!src/**/*.d.ts',
    '!src/**/__generated__/**',
    '!src/**/index.ts',        // entry points — thin routers only
    '!src/**/*.test.ts',
    '!src/**/*.spec.ts',
  ],
  coverageAnalysis: 'perTest',   // required for incremental mutation runs
  thresholds: {
    high: 80,
    low: 60,
    break: 55,                   // CI fails below this mutation score
  },
  reporters: ['html', 'progress', 'json'],
  htmlReporter: {
    fileName: 'reports/mutation/index.html',
  },
  jsonReporter: {
    fileName: 'reports/mutation/report.json',
  },
  incremental: true,             // cache results between runs; only re-test changed mutants
  incrementalFile: '.stryker-tmp/incremental.json',
  timeoutMS: 10_000,             // kill slow mutant runs early
  concurrency: 4,                // parallel Workers; tune to CI runner CPU count
} satisfies Config;
```

```typescript
// src/pricing/calculate-order-total.ts
// This is the module under mutation — business-critical pricing logic

export interface LineItem {
  priceCents: number;
  quantity: number;
  discountPercent?: number;
}

export interface OrderTotal {
  subtotalCents: number;
  discountCents: number;
  taxCents: number;
  totalCents: number;
}

const TAX_RATE = 0.08; // 8 %
const MAX_DISCOUNT_PERCENT = 50;

export function calculateOrderTotal(
  items: LineItem[],
  couponDiscountPercent: number = 0
): OrderTotal {
  if (items.length === 0) {
    throw new Error('Order must contain at least one item');
  }

  const subtotalCents = items.reduce((sum, item) => {
    if (item.quantity <= 0) throw new Error('Quantity must be positive');
    if (item.priceCents < 0) throw new Error('Price cannot be negative');

    const itemDiscount = Math.min(
      item.discountPercent ?? 0,
      MAX_DISCOUNT_PERCENT
    );
    const effectivePrice = Math.round(
      item.priceCents * (1 - itemDiscount / 100)
    );
    return sum + effectivePrice * item.quantity;
  }, 0);

  const clampedCoupon = Math.min(
    Math.max(couponDiscountPercent, 0),
    MAX_DISCOUNT_PERCENT
  );
  const discountCents = Math.round(subtotalCents * (clampedCoupon / 100));
  const taxableCents  = subtotalCents - discountCents;
  const taxCents      = Math.round(taxableCents * TAX_RATE);
  const totalCents    = taxableCents + taxCents;

  return { subtotalCents, discountCents, taxCents, totalCents };
}
```

```typescript
// src/pricing/calculate-order-total.test.ts
// Strong tests designed to kill mutants

import { describe, it, expect } from 'vitest';
import { calculateOrderTotal, type LineItem } from './calculate-order-total';

describe('calculateOrderTotal', () => {
  const base: LineItem = { priceCents: 1000, quantity: 2 };

  it('returns correct subtotal for multiple items', () => {
    const result = calculateOrderTotal([base, { priceCents: 500, quantity: 3 }]);
    expect(result.subtotalCents).toBe(3500); // 2*1000 + 3*500
  });

  it('applies item-level discount before summing', () => {
    const item: LineItem = { priceCents: 1000, quantity: 1, discountPercent: 10 };
    const result = calculateOrderTotal([item]);
    expect(result.subtotalCents).toBe(900); // not 1000, not 100
  });

  it('applies coupon discount to subtotal', () => {
    const result = calculateOrderTotal([base], 20);
    // subtotal = 2000, discount = 400
    expect(result.discountCents).toBe(400);
    expect(result.subtotalCents).toBe(2000);
  });

  it('computes tax on post-discount amount', () => {
    const result = calculateOrderTotal([base], 0);
    // taxable = 2000, tax = 160
    expect(result.taxCents).toBe(160);
  });

  it('total equals taxable amount plus tax', () => {
    const result = calculateOrderTotal([{ priceCents: 1000, quantity: 1 }], 0);
    expect(result.totalCents).toBe(result.subtotalCents - result.discountCents + result.taxCents);
  });

  it('clamps coupon discount at MAX_DISCOUNT_PERCENT', () => {
    const result = calculateOrderTotal([base], 99);
    // discount = 50% of 2000 = 1000, not 99%
    expect(result.discountCents).toBe(1000);
  });

  it('clamps coupon below zero to zero', () => {
    const result = calculateOrderTotal([base], -10);
    expect(result.discountCents).toBe(0);
  });

  it('throws on empty items array', () => {
    expect(() => calculateOrderTotal([])).toThrow('at least one item');
  });

  it('throws on non-positive quantity', () => {
    expect(() => calculateOrderTotal([{ priceCents: 100, quantity: 0 }])).toThrow('positive');
  });

  it('throws on negative price', () => {
    expect(() => calculateOrderTotal([{ priceCents: -1, quantity: 1 }])).toThrow('negative');
  });

  it('item discount capped at 50 %', () => {
    const item: LineItem = { priceCents: 1000, quantity: 1, discountPercent: 80 };
    const result = calculateOrderTotal([item]);
    expect(result.subtotalCents).toBe(500); // not 200 (80% off)
  });

  it('two identical items double the cost', () => {
    const single = calculateOrderTotal([{ priceCents: 1000, quantity: 1 }]);
    const double = calculateOrderTotal([{ priceCents: 1000, quantity: 2 }]);
    expect(double.subtotalCents).toBe(single.subtotalCents * 2);
  });
});
```

## Implementation Details

**`coverageAnalysis: 'perTest'`** — Stryker uses Vitest's per-test coverage to know which tests cover which source lines, and only runs the relevant tests for each mutant. This reduces runtime from O(mutants × all_tests) to roughly O(mutants × covering_tests).

**Incremental runs in CI** — commit `.stryker-tmp/incremental.json` to a CI cache (e.g. GitHub Actions cache keyed on `hashFiles('src/pricing/**')`) so that only mutants in changed files are re-evaluated on each PR.

**Interpreting surviving mutants** — a surviving mutant in a conditional (`>` → `>=`) means no test exercises the boundary case. The fix is a new test at the exact boundary, not a weaker mutant exclusion.

**Excluding mutants explicitly** — use `// Stryker disable next-line ArithmeticOperator` to suppress a specific mutant type on a line where it is logically irrelevant (e.g. a logging timestamp calculation). Use this sparingly; every suppression is a documented risk acceptance.

## Anti-patterns

- **Running mutation testing on the entire codebase** — glue code, Worker entry-point routers, and generated Zod schemas produce thousands of low-value mutants and inflate runtime. Scope tightly to domain logic.
- **Setting `break: 0`** — disabling the CI failure threshold defeats the purpose of mutation testing. Start at 50, raise to 70 after an initial improvement sprint.
- **Writing tests to kill mutants mechanically** — tests written only to satisfy Stryker (e.g. asserting an exact integer that masks the real invariant) are fragile and misleading. Write tests that express business rules.
- **Ignoring timeout kills** — `TimedOut` mutants are not killed mutants; they are slow tests. Fix the underlying test performance rather than raising `timeoutMS`.

## Gotchas

- `@cloudflare/vitest-pool-workers` runs tests inside a Miniflare Worker sandbox. Stryker's Vitest runner instruments files before Vitest loads them; ensure the Stryker instrumentation happens before Miniflare's module transform chain. Set `vitest.pool` back to `'forks'` (Node) in `stryker.config.ts` for pure business-logic modules that have no Worker bindings.
- Stryker's HTML report is large for codebases with many mutants. Add `reports/mutation/` to `.gitignore`.
- The `incremental` cache becomes stale when you rename a test file. Delete `.stryker-tmp/` on rename to avoid phantom results.
- Mutation scores fluctuate by 1–2 % across runs when tests are non-deterministic (e.g. using `Date.now()`). Freeze time in tests with `vi.useFakeTimers()`.

## Verification

```bash
# Full mutation run on pricing module
npx stryker run

# Inspect survivors in the JSON report
cat reports/mutation/report.json \
  | jq '[.files | to_entries[] | .value.mutants[] | select(.status == "Survived")] | length'

# View HTML report
open reports/mutation/index.html

# CI gate check (exit 1 if mutation score < break threshold)
npx stryker run --reporters json 2>&1 | tail -5
echo "Exit: $?"
```

## Related

- `documentation/categories/testing/workers-golden-path-test-suite.md`
- `documentation/categories/testing/workers-contract-testing-pact.md`
- Stryker docs: https://stryker-mutator.io/docs/stryker-js/introduction/
- Vitest pool for Workers: https://developers.cloudflare.com/workers/testing/vitest-integration/

## Sources

- Stryker Mutator — Vitest Runner docs (2025)
- Cloudflare Workers — Vitest integration guide (2025)
- example.com internal runbook: mutation-testing-strategy (2026-05)
