# Intl.NumberFormat Accounting Notation and signDisplay for Financial UI in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A revenue dashboard renders negative currency values as `-$1,234.00` for every locale, but
German accountants expect `−1.234,00 €` (with a proper minus sign, not a hyphen-minus), and
US finance teams expect `($1,234.00)` (parentheses, no minus at all) to match Excel/GAAP
convention. Additionally, a gains/losses column should show `+$500.00` for positive values,
not `$500.00`, so sign is always explicit. Both requirements are locale-sensitive and must be
satisfied from Cloudflare Workers without a browser runtime.

## Context

`Intl.NumberFormat` exposes two underused options relevant to financial formatting:

- **`currencySign: 'accounting'`** — uses locale-specific accounting notation (parentheses
  for negatives in `en-US`, a different pattern in many other locales).
- **`signDisplay`** — controls when the sign character appears: `'auto'` (default, negative
  only), `'always'` (force `+` on positive), `'exceptZero'` (sign on non-zero), `'never'`
  (suppress sign), `'negative'` (sign only on negative, never on zero).

Both options are fully supported on the V8 engine used by Cloudflare Workers as of V8 11.x
(ECMA-402 2023+). They compose with `style: 'currency'`, `style: 'decimal'`, and
`style: 'percent'`.

---

## 1. Accounting notation for currency display

```typescript
// src/lib/finance-format.ts

export type AccountingFormatOptions = {
  locale: string;
  currency: string;
  /** 'accounting' uses parentheses for negatives per locale convention */
  currencySign?: 'standard' | 'accounting';
};

export function formatAccountingCurrency(
  amount: number,
  { locale, currency, currencySign = 'accounting' }: AccountingFormatOptions
): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    currencySign,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

// Examples:
// formatAccountingCurrency(-1234.56, { locale: 'en-US', currency: 'USD' })
//   => "($1,234.56)"           — US accounting convention
// formatAccountingCurrency(-1234.56, { locale: 'de-DE', currency: 'EUR' })
//   => "-1.234,56 €"           — German: no parentheses, locale minus sign
// formatAccountingCurrency(-1234.56, { locale: 'en-GB', currency: 'GBP' })
//   => "(£1,234.56)"           — UK accounting
// formatAccountingCurrency(1234.56, { locale: 'en-US', currency: 'USD' })
//   => "$1,234.56"             — positive: no change from standard
```

---

## 2. Explicit sign display for gains/losses columns

```typescript
export type SignDisplayStyle = 'always' | 'exceptZero' | 'auto' | 'never' | 'negative';

export function formatChange(
  amount: number,
  locale: string,
  currency: string,
  signDisplay: SignDisplayStyle = 'always'
): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    signDisplay,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

// formatChange(500,   'en-US', 'USD')  => "+$500.00"
// formatChange(-200,  'en-US', 'USD')  => "-$200.00"
// formatChange(0,     'en-US', 'USD', 'exceptZero') => "$0.00"   (zero: no sign)
// formatChange(500,   'de-DE', 'EUR')  => "+500,00 €"
// formatChange(-200,  'fr-FR', 'EUR')  => "-200,00 €"
```

---

## 3. Composing accounting notation with `formatToParts` for custom rendering

```typescript
// Extract sign and value parts separately for colour-coded cell rendering
export interface AccountingParts {
  sign: 'positive' | 'negative' | 'zero';
  formatted: string;
  isParenthetical: boolean;
}

export function accountingParts(
  amount: number,
  locale: string,
  currency: string
): AccountingParts {
  const fmt = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    currencySign: 'accounting',
    minimumFractionDigits: 2,
  });

  const parts = fmt.formatToParts(amount);
  const hasParenthesis = parts.some(p => p.type === 'literal' && p.value === '(');
  const hasMinusSign  = parts.some(p => p.type === 'minusSign');

  return {
    sign: amount > 0 ? 'positive' : amount < 0 ? 'negative' : 'zero',
    formatted: parts.map(p => p.value).join(''),
    isParenthetical: hasParenthesis && !hasMinusSign,
  };
}
```

Use `isParenthetical` to apply CSS class `text-red-600` without parsing the output string.

---

## 4. Workers handler: locale-aware financial row formatting

```typescript
// src/handlers/financial-export.ts
import { formatAccountingCurrency, formatChange } from '../lib/finance-format';

export interface Env { DB: D1Database; }

interface LedgerRow {
  description: string;
  amount: number;
  currency: string;
}

export async function handleLedgerExport(req: Request, env: Env): Promise<Response> {
  const url = new URL(req.url);
  const locale = url.searchParams.get('locale') ?? 'en-US';

  const rows = await env.DB.prepare(
    'SELECT description, amount, currency FROM ledger ORDER BY created_at DESC LIMIT 200'
  ).all<LedgerRow>();

  const formatted = rows.results.map(row => ({
    description: row.description,
    display: formatAccountingCurrency(row.amount, { locale, currency: row.currency }),
    change: formatChange(row.amount, locale, row.currency, 'exceptZero'),
    sign: row.amount >= 0 ? 'credit' : 'debit',
  }));

  return Response.json({ locale, rows: formatted });
}
```

---

## 5. Percent change with explicit sign and locale grouping

```typescript
// Profit margin or growth rate columns
export function formatPercentChange(rate: number, locale: string): string {
  // rate = 0.053 → "+5.3 %"  (fr-FR inserts narrow no-break space before %)
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    signDisplay: 'always',
    minimumFractionDigits: 1,
    maximumFractionDigits: 2,
  }).format(rate);
}

// formatPercentChange(0.053,  'en-US') => "+5.3%"
// formatPercentChange(-0.12,  'en-US') => "-12%"
// formatPercentChange(0.053,  'fr-FR') => "+5,3 %"
// formatPercentChange(0,      'en-US', /* signDisplay 'exceptZero' */) => "0%"
```

---

## 6. Caching formatters per locale in Workers isolates

```typescript
// Formatter instances are expensive to create; cache per isolate per locale+currency pair
const fmtCache = new Map<string, Intl.NumberFormat>();

function cachedAccountingFmt(locale: string, currency: string): Intl.NumberFormat {
  const key = `${locale}:${currency}`;
  if (!fmtCache.has(key)) {
    fmtCache.set(key, new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
      currencySign: 'accounting',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }));
  }
  return fmtCache.get(key)!;
}
```

A typical financial page renders 50–200 rows per locale; caching avoids 50–200 constructor
calls and halves formatting time in hot paths.

---

## Anti-patterns

- **String-based sign detection** — `amount < 0 ? '(' + fmt(amount) + ')' : fmt(amount)` is
  wrong; `currencySign: 'accounting'` produces locale-correct parenthesis placement including
  the currency symbol position.
- **Hardcoding `−` (U+2212 MINUS SIGN) vs `-` (U+002D HYPHEN-MINUS)** — let `Intl` emit the
  correct sign character for the locale; some locales use the Arabic minus or other glyphs.
- **Assuming accounting means parentheses everywhere** — `de-DE` and many European locales
  use a minus sign even in accounting mode; only some locales switch to parentheses.
- **Displaying skeleton strings to users** — never expose the `key` used for formatter
  caching; it is an internal identifier, not a display-safe string.

## Gotchas

- **`currencySign: 'accounting'` applies only to `style: 'currency'`** — it has no effect on
  `style: 'decimal'` or `style: 'percent'`; use `signDisplay` for those.
- **Zero handling** — `signDisplay: 'always'` may emit `+$0.00` for zero; use `'exceptZero'`
  to suppress the sign on zero-balance rows.
- **`formatToParts` parenthesis detection** — the literal `(` is a `literal` part, not a
  distinct `parenthesis` type; test `part.type === 'literal' && part.value === '('`.
- **Locale string must be BCP 47 valid** — pass through `new Intl.Locale(locale).toString()`
  to canonicalise before constructing the formatter; invalid tags throw in strict V8 builds.

## Verification

```typescript
import { describe, it, expect } from 'vitest';
import { formatAccountingCurrency, formatChange } from '../src/lib/finance-format';

describe('accounting notation', () => {
  it('wraps negative in parens for en-US', () => {
    expect(formatAccountingCurrency(-1234.56, { locale: 'en-US', currency: 'USD' }))
      .toBe('($1,234.56)');
  });
  it('uses minus not parens for de-DE', () => {
    const result = formatAccountingCurrency(-1234.56, { locale: 'de-DE', currency: 'EUR' });
    expect(result).not.toContain('(');
    expect(result).toContain('1.234,56');
  });
  it('always shows + for positive with signDisplay always', () => {
    expect(formatChange(500, 'en-US', 'USD', 'always')).toContain('+');
  });
});
```

## Related

- `currency-formatting-cloudflare-workers-intl-numberformat.md`
- `intl-numberformat-explicit-rounding-policy.md`
- `intl-numberformat-range-source-parts.md`
- `locale-aware-number-currency-formatting.md`
- `number-currency-formatting-2026.md`

## Sources

- ECMA-402 Intl.NumberFormat `currencySign` and `signDisplay`: https://tc39.es/ecma402/#sec-intl-numberformat-constructor
- MDN Intl.NumberFormat currencySign: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat#currencysign
- MDN Intl.NumberFormat signDisplay: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat#signdisplay
- CLDR currency format patterns: https://cldr.unicode.org/translation/number-currency-formats/number-and-currency-patterns
- Cloudflare Workers V8 ECMA-402 support: https://developers.cloudflare.com/workers/runtime-apis/web-standards/
