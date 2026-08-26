# CLDR Supplemental Currency Fraction Digits in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A payment summary edge Worker formats `JPY 1234.00` with two decimal places even
though the Japanese yen has no sub-unit. Conversely, a Kuwaiti-dinar amount shows
`KWD 12.3` when it should carry three decimal places. The root issue is that
`Intl.NumberFormat` uses its own internal CLDR supplemental data, but your
*display logic* and *rounding logic* need access to the same data independently —
to decide whether to transmit `.00`, how many digits to store in D1, and what to
show in PDF line-items generated before `Intl` is ever called.

---

## Context

CLDR's `supplemental/currencyData.json` is the canonical source for:

| Field | Meaning |
|---|---|
| `_digits` | Minimum fraction digits for standard display |
| `_cashDigits` | Fraction digits when the currency is used in cash (may differ) |
| `_cashRounding` | Cash rounding increment (e.g., 0.05 for CHF) |

The V8 engine shipped in Cloudflare Workers exposes these values indirectly via
`Intl.NumberFormat`, but only for formatting — not for validation, storage, or
rounding decisions. You need to ship a compact lookup table derived from CLDR
data and use it in the Worker directly.

Affected currencies include (non-exhaustive):

- **0 decimal places**: BIF, CLP, DJF, GNF, ISK, JPY, KMF, KRW, PYG, RWF, UGX, VND, VUV, XAF, XOF, XPF
- **3 decimal places**: BHD, IQD, JOD, KWD, LYD, OMR, TND
- **4 decimal places**: CLF, UYW

---

## Embedding a CLDR Fraction Lookup Table

Shipping the full CLDR supplemental JSON (~40 KB) into a Worker bundle is
wasteful. Extract only what you need at build time.

### Build-time extraction script (Node.js, run in CI)

```typescript
// scripts/build-currency-fractions.ts
import supplemental from '@unicode/cldr-core/supplemental/currencyData.json' assert { type: 'json' };
import { writeFileSync } from 'fs';

// CLDR stores fraction data under supplemental.currencyData.fractions
// Each entry key is a currency code or "DEFAULT"
const raw = (supplemental as any).supplemental.currencyData.fractions as Record<
  string,
  { _digits?: string; _cashDigits?: string; _cashRounding?: string }
>;

const table: Record<string, { digits: number; cashDigits: number; cashRounding: number }> = {};
const defaultDigits = parseInt(raw['DEFAULT']?._digits ?? '2', 10);

for (const [code, data] of Object.entries(raw)) {
  if (code === 'DEFAULT') continue;
  const digits = data._digits !== undefined ? parseInt(data._digits, 10) : defaultDigits;
  const cashDigits = data._cashDigits !== undefined ? parseInt(data._cashDigits, 10) : digits;
  const cashRounding = data._cashRounding !== undefined ? parseFloat(data._cashRounding) : 0;
  table[code] = { digits, cashDigits, cashRounding };
}

writeFileSync(
  'src/data/currency-fractions.json',
  JSON.stringify({ default: defaultDigits, currencies: table }, null, 0)
);
console.log(`Wrote ${Object.keys(table).length} currency entries`);
```

Run this during CI to keep `src/data/currency-fractions.json` current when you
upgrade `@unicode/cldr-core`.

### Fraction lookup module

```typescript
// src/lib/currency-fractions.ts
import fractionData from '../data/currency-fractions.json';

export interface CurrencyFractionInfo {
  /** Standard minimum fraction digits (display) */
  digits: number;
  /** Cash transaction fraction digits */
  cashDigits: number;
  /** Cash rounding increment (0 = no rounding) */
  cashRounding: number;
}

const { default: defaultDigits, currencies } = fractionData as {
  default: number;
  currencies: Record<string, CurrencyFractionInfo>;
};

/**
 * Returns CLDR fraction data for a given ISO 4217 currency code.
 * Falls back to {digits:2, cashDigits:2, cashRounding:0} for unknown codes.
 */
export function getCurrencyFractions(currencyCode: string): CurrencyFractionInfo {
  const code = currencyCode.toUpperCase();
  return (
    currencies[code] ?? { digits: defaultDigits, cashDigits: defaultDigits, cashRounding: 0 }
  );
}

/**
 * Round an amount to the correct cash increment for a currency.
 * E.g. CHF with cashRounding=0.05 → 1.03 → 1.05
 */
export function roundToCashIncrement(amount: number, currencyCode: string): number {
  const { cashDigits, cashRounding } = getCurrencyFractions(currencyCode);
  if (cashRounding === 0) {
    const factor = Math.pow(10, cashDigits);
    return Math.round(amount * factor) / factor;
  }
  return Math.round(amount / cashRounding) * cashRounding;
}
```

---

## Formatting Amounts Correctly in a Worker

```typescript
// src/workers/payment-summary.ts
import { getCurrencyFractions, roundToCashIncrement } from '../lib/currency-fractions';

export interface LineItem {
  description: string;
  amount: number; // raw float, may be unrounded
  currency: string;
}

export function formatLineItem(item: LineItem, displayLocale: string): string {
  const { currency } = item;
  const { digits } = getCurrencyFractions(currency);

  const formatter = new Intl.NumberFormat(displayLocale, {
    style: 'currency',
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

  return formatter.format(item.amount);
}

export function formatCashTotal(amount: number, currency: string, displayLocale: string): string {
  const { cashDigits } = getCurrencyFractions(currency);
  const rounded = roundToCashIncrement(amount, currency);

  return new Intl.NumberFormat(displayLocale, {
    style: 'currency',
    currency,
    minimumFractionDigits: cashDigits,
    maximumFractionDigits: cashDigits,
  }).format(rounded);
}

// Worker handler
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const currency = url.searchParams.get('currency') ?? 'USD';
    const amount = parseFloat(url.searchParams.get('amount') ?? '0');
    const locale = request.headers.get('Accept-Language')?.split(',')[0].trim() ?? 'en-US';

    const fractions = getCurrencyFractions(currency);

    return Response.json({
      display: formatLineItem({ description: 'Total', amount, currency }, locale),
      cashTotal: formatCashTotal(amount, currency, locale),
      meta: { digits: fractions.digits, cashDigits: fractions.cashDigits },
    });
  },
};
```

---

## Storing Amounts in D1 with Correct Precision

Store monetary amounts as integers in the smallest currency unit (sub-unit) to
avoid floating-point drift. The fraction digit count tells you the multiplier.

```typescript
// src/lib/currency-storage.ts
import { getCurrencyFractions } from './currency-fractions';

/** Convert a display float (e.g. 12.34 USD) to integer minor units (1234) */
export function toMinorUnits(amount: number, currency: string): number {
  const { digits } = getCurrencyFractions(currency);
  return Math.round(amount * Math.pow(10, digits));
}

/** Convert integer minor units back to display float */
export function fromMinorUnits(minorUnits: number, currency: string): number {
  const { digits } = getCurrencyFractions(currency);
  return minorUnits / Math.pow(10, digits);
}

// D1 schema: store as INTEGER, never REAL
// CREATE TABLE orders (
//   id TEXT PRIMARY KEY,
//   currency TEXT NOT NULL,         -- e.g. 'JPY'
//   amount_minor INTEGER NOT NULL,  -- e.g. 1234 for ¥1234
//   created_at TEXT NOT NULL
// );

export async function insertOrder(
  db: D1Database,
  id: string,
  currency: string,
  displayAmount: number
): Promise<void> {
  const minorUnits = toMinorUnits(displayAmount, currency);
  await db
    .prepare('INSERT INTO orders (id, currency, amount_minor, created_at) VALUES (?, ?, ?, ?)')
    .bind(id, currency, minorUnits, new Date().toISOString())
    .run();
}
```

---

## Anti-patterns

**Hardcoding two decimal places for all currencies:**
```typescript
// Wrong — breaks for JPY, KWD, BHD, etc.
const fmt = new Intl.NumberFormat('en', {
  style: 'currency',
  currency,
  minimumFractionDigits: 2, // ❌
});
```

**Relying solely on `Intl.NumberFormat` for business logic:**
`Intl.NumberFormat` formats correctly for display but does not expose the digit
count programmatically via a stable API. Do not parse the formatted string to
infer precision.

**Storing amounts as REAL in SQLite:**
```sql
-- Wrong: floating-point representation errors accumulate
amount REAL  -- ❌
```

**Using `cashRounding` without checking it is nonzero:**
```typescript
// Wrong: Math.round(x / 0) = NaN
const rounded = Math.round(amount / cashRounding) * cashRounding; // ❌ when cashRounding=0
```

---

## Gotchas

- **CLF (Unidad de Fomento, Chile)**: 4 decimal places. Exotic but real — some
  Chilean financial APIs send CLF amounts.
- **XOF / XAF / XPF**: West/Central African CFA and CFP franc — 0 decimal places
  despite looking like regional subdivisional currencies.
- **MRU (Mauritanian Ouguiya)**: switched from 2 to 1 decimal place in 2018; older
  CLDR versions still say 2. Pin your `@unicode/cldr-core` version.
- **USN (US Dollar, next day)**: listed in CLDR with 2 digits but rarely seen in
  production; treat `getCurrencyFractions('USN')` returning `{digits:2}` as correct.
- **CHF cash rounding**: Switzerland rounds cash to 0.05; card payments use 0.01.
  Your checkout flow needs to know which channel it's on before applying rounding.
- CLDR fraction data does not change frequently, but do update `@unicode/cldr-core`
  when a new Unicode/CLDR release ships — new currencies and corrections arrive
  roughly annually.

---

## Verification

```typescript
// tests/currency-fractions.test.ts
import { getCurrencyFractions, toMinorUnits, fromMinorUnits } from '../src/lib/currency-fractions';
import { describe, it, expect } from 'vitest';

describe('getCurrencyFractions', () => {
  it('returns 0 digits for JPY', () => {
    expect(getCurrencyFractions('JPY').digits).toBe(0);
  });
  it('returns 3 digits for KWD', () => {
    expect(getCurrencyFractions('KWD').digits).toBe(3);
  });
  it('returns 2 digits for USD (default)', () => {
    expect(getCurrencyFractions('USD').digits).toBe(2);
  });
  it('returns 2 for unknown currency', () => {
    expect(getCurrencyFractions('ZZZ').digits).toBe(2);
  });
});

describe('minor unit conversion', () => {
  it('converts JPY correctly (no sub-unit)', () => {
    expect(toMinorUnits(1234, 'JPY')).toBe(1234);
    expect(fromMinorUnits(1234, 'JPY')).toBe(1234);
  });
  it('converts USD correctly', () => {
    expect(toMinorUnits(12.34, 'USD')).toBe(1234);
    expect(fromMinorUnits(1234, 'USD')).toBe(12.34);
  });
  it('converts KWD correctly (3 decimal places)', () => {
    expect(toMinorUnits(1.234, 'KWD')).toBe(1234);
  });
});
```

Run with `vitest run` in a Node.js 22+ environment. Workers runtime tests can
use `vitest --environment edge-runtime` with the `@edge-runtime/vitest-environment`
package to verify the `Intl.NumberFormat` output matches expectations.

---

## Related

- `currency-formatting-cloudflare-workers-intl-numberformat.md`
- `cldr-data-2026.md`
- `number-system-locale-workers-d1.md`
- `intl-numberformat-explicit-rounding-policy.md`
- `locale-aware-csv-import-parsing-workers.md`

---

## Sources

- CLDR supplemental currencyData: https://github.com/unicode-org/cldr-json/blob/main/cldr-json/cldr-core/supplemental/currencyData.json
- ISO 4217 currency codes: https://www.six-group.com/en/products-services/financial-information/data-standards.html#scrollTo=currency-codes
- `@unicode/cldr-core` npm package: https://www.npmjs.com/package/@unicode/cldr-core
- Cloudflare Workers D1 documentation: https://developers.cloudflare.com/d1/
