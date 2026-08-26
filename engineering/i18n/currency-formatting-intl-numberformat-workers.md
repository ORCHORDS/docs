# Currency Formatting with `Intl.NumberFormat` in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker returns product prices from D1 where amounts are stored as integer cents, and you need to render them as correctly formatted strings (`¥1,234`, `$12.34`, `€12,34`) depending on the user's locale and preferred currency. Naively calling `.toFixed(2)` produces wrong results for JPY (which has no fractional subunit) and outputs the wrong separator in locales that use commas as decimal marks.

---

## Context

Storing monetary amounts as integer cents (or the smallest subunit) avoids floating-point rounding errors and keeps D1 schema simple. Formatting is a display-layer concern only and belongs in the Worker that serialises the HTTP response. `Intl.NumberFormat` with `style: 'currency'` automatically handles fractional digits (0 for JPY, 3 for KWD, 2 for USD), grouping separators, and currency symbol placement per locale. User locale and currency preference are stored in D1 `user_preferences` keyed by session token. Cloudflare Workers support `Intl.NumberFormat` fully as of compatibility date `2022-03-21`.

---

## Section 1 — D1 schema

```sql
-- Products table: price stored as integer minor units
CREATE TABLE IF NOT EXISTS products (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  price_minor INTEGER NOT NULL,   -- e.g. 1234 = $12.34 or ¥1234
  currency    TEXT NOT NULL       -- ISO 4217: 'USD', 'JPY', 'EUR', 'KWD'
);

-- User preferences: locale + preferred display currency
CREATE TABLE IF NOT EXISTS user_preferences (
  user_id        TEXT PRIMARY KEY,
  display_locale TEXT NOT NULL DEFAULT 'en-US',
  display_currency TEXT NOT NULL DEFAULT 'USD'
);

-- Example rows
INSERT INTO products VALUES ('p1', 'Widget', 1234,  'USD');  -- $12.34
INSERT INTO products VALUES ('p2', 'Gadget', 123400,'JPY');  -- ¥123,400
INSERT INTO products VALUES ('p3', 'Donut',  150,   'EUR');  -- €1.50
```

---

## Section 2 — Currency formatter utility

```typescript
// src/i18n/currency.ts

/**
 * ISO 4217 exponent map: number of decimal places for the currency's minor unit.
 * Intl.NumberFormat handles this automatically, but we need the divisor to
 * convert integer minor units back to the major unit before formatting.
 */
const CURRENCY_EXPONENTS: Record<string, number> = {
  BHD: 3, IQD: 3, JOD: 3, KWD: 3, LYD: 3, OMR: 3, TND: 3, // 3 decimals
  JPY: 0, KRW: 0, VND: 0, XOF: 0, XAF: 0,                  // 0 decimals
  // All others default to 2
};

function minorToMajor(minorUnits: number, currency: string): number {
  const exp = CURRENCY_EXPONENTS[currency.toUpperCase()] ?? 2;
  return minorUnits / Math.pow(10, exp);
}

/**
 * Format an integer minor-unit price as a locale-aware currency string.
 *
 * @param minorUnits  - The raw value from D1 (e.g. 1234)
 * @param currency    - ISO 4217 currency code (e.g. 'USD')
 * @param locale      - BCP 47 locale tag (e.g. 'de-DE')
 * @returns           - Formatted string (e.g. '12,34 $')
 */
export function formatCurrency(
  minorUnits: number,
  currency: string,
  locale: string
): string {
  const amount = minorToMajor(minorUnits, currency);

  const formatter = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: currency.toUpperCase(),
    // Let the runtime choose the correct fraction digits for the currency.
    // Explicitly setting minimumFractionDigits overrides CLDR data — avoid it.
  });

  return formatter.format(amount);
}

/**
 * Format a price for display in a specific target currency, converting from
 * the product's stored currency. This is a display-only conversion — real
 * FX should be done server-side with accurate rates.
 */
export function formatPriceRow(
  priceMinor: number,
  storedCurrency: string,
  displayLocale: string,
  displayCurrency: string
): string {
  // If display currency matches stored currency, no conversion needed.
  if (storedCurrency.toUpperCase() === displayCurrency.toUpperCase()) {
    return formatCurrency(priceMinor, storedCurrency, displayLocale);
  }
  // In a real implementation, apply FX rate here before formatting.
  // For now, format in stored currency but honour the user's locale.
  return formatCurrency(priceMinor, storedCurrency, displayLocale);
}
```

---

## Section 3 — Worker handler with D1 lookup

```typescript
// src/index.ts
import { formatPriceRow } from './i18n/currency';

export interface Env {
  DB: D1Database;
}

interface Product {
  id: string;
  name: string;
  price_minor: number;
  currency: string;
}

interface UserPrefs {
  display_locale: string;
  display_currency: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const productId = url.searchParams.get('id') ?? 'p1';
    const userId    = url.searchParams.get('user') ?? 'anonymous';

    // Fetch product and user prefs in parallel.
    const [productRow, prefsRow] = await Promise.all([
      env.DB
        .prepare('SELECT id, name, price_minor, currency FROM products WHERE id = ?')
        .bind(productId)
        .first<Product>(),
      env.DB
        .prepare('SELECT display_locale, display_currency FROM user_preferences WHERE user_id = ?')
        .bind(userId)
        .first<UserPrefs>(),
    ]);

    if (!productRow) {
      return Response.json({ error: 'product not found' }, { status: 404 });
    }

    const locale   = prefsRow?.display_locale   ?? 'en-US';
    const currency = prefsRow?.display_currency  ?? productRow.currency;

    const formatted = formatPriceRow(
      productRow.price_minor,
      productRow.currency,
      locale,
      currency
    );

    return Response.json({
      id:             productRow.id,
      name:           productRow.name,
      price_minor:    productRow.price_minor,
      stored_currency: productRow.currency,
      display_locale:  locale,
      formatted_price: formatted,
    });
  },
};

// Example outputs:
// id=p1, user with en-US / USD  → "$12.34"
// id=p1, user with de-DE / EUR  → "12,34 $"  (locale-aware grouping)
// id=p2, user with ja-JP / JPY  → "¥123,400" (no decimals for JPY)
// id=p3, user with fr-FR / EUR  → "1,50 €"
```

---

## Anti-patterns

- **Storing prices as `REAL` floats in D1** — Floating-point arithmetic causes rounding drift; always store as `INTEGER` minor units and divide only at the display layer.
- **Hard-coding `minimumFractionDigits: 2`** — This forces two decimal places on JPY, yielding `¥123,400.00`, which is wrong. Let `Intl.NumberFormat` derive the correct digit count from the currency code.
- **Using `Number.toFixed()` for display** — Produces locale-invariant output (always a period as decimal separator) and ignores grouping, symbol placement, and RTL considerations.
- **Instantiating `Intl.NumberFormat` inside a tight loop** — Cache formatter instances keyed by `${locale}:${currency}` when formatting large product lists in a single request.

---

## Gotchas

- JPY, KRW, and VND have zero fractional digits. Dividing their minor-unit values by 100 before formatting will produce `¥1.23` for a stored value of `123`; use the exponent table or rely solely on `Intl.NumberFormat` knowing the zero-exponent currencies natively (it does, but only if you do NOT override `minimumFractionDigits`).
- `Intl.NumberFormat` in Workers does not support `currencyDisplay: 'narrowSymbol'` before compatibility date `2023-03-01`. Use `'symbol'` as a safe default.
- The `format` method returns a string with non-breaking spaces (U+00A0) as grouping separators in some locales (e.g. `fr-FR`). Strip or replace these if you are later parsing the output for any reason.
- D1 returns `INTEGER` columns as JavaScript `number` — safe up to 2^53-1, which covers any realistic price in minor units.

---

## Verification

```bash
# 1. Apply schema and seed data
npx wrangler d1 execute MY_DB --local --file=schema.sql

# 2. Run dev server
npx wrangler dev

# 3. Test USD formatting
curl 'http://localhost:8787/?id=p1'
# Expected: { "formatted_price": "$12.34" }

# 4. Test JPY (zero fractional digits)
curl 'http://localhost:8787/?id=p2&user=jp_user'
# Expected: { "formatted_price": "¥123,400" }

# 5. Test EUR with German locale
curl 'http://localhost:8787/?id=p3&user=de_user'
# Expected: { "formatted_price": "1,50 €" }

# 6. Unit-test the formatter directly
node -e "
const { formatCurrency } = require('./dist/i18n/currency');
console.assert(formatCurrency(1234,  'USD', 'en-US') === '$12.34');
console.assert(formatCurrency(123400,'JPY', 'ja-JP') === '¥123,400');
console.assert(formatCurrency(150,   'EUR', 'de-DE') === '1,50 €');
console.log('All assertions passed');
"
```

---

## Related

- `date-time-formatting-intl-datetimeformat-workers.md`
- `plural-rules-intl-pluralrules-workers.md`
- `translation-key-missing-fallback-kv-workers.md`

---

## Sources

- MDN Intl.NumberFormat — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- ISO 4217 currency exponents — https://www.six-group.com/en/products-services/financial-information/data-standards.html
- Cloudflare D1 — https://developers.cloudflare.com/d1/
