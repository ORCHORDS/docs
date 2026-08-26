# Locale-Aware Number Parsing and Validation in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A form submission from Germany sends `1.234,56` as a price field, while a US user sends `1,234.56` — both look like valid numbers but are parsed incorrectly by `parseFloat()`. A Worker receiving these inputs either silently stores wrong values in D1 or rejects valid inputs. You need to correctly interpret locale-formatted number strings from user input, validate them, and store a canonical float.

## Context

`parseFloat("1.234,56")` returns `1.234` in every JavaScript runtime — it stops at the comma. European locales use a period as a thousands separator and a comma as the decimal separator, which is the exact inverse of US conventions. Cloudflare Workers run V8, which fully supports the `Intl.NumberFormat` API at the edge. The safest parsing strategy is the format-then-compare approach: format a known sentinel value with the target locale's `Intl.NumberFormat`, extract which characters are used as group and decimal separators, then strip/replace them before calling `parseFloat()`. Validated canonical floats should be stored in D1 and re-formatted per `Accept-Language` on the way out.

## Parsing Locale Numbers with `Intl.NumberFormat`

```typescript
// utils/parseLocaleNumber.ts

/**
 * Detects the decimal and group separators for a given locale by formatting
 * a sentinel number (1111.1) and reading the resulting characters.
 */
function getSeparators(locale: string): { decimal: string; group: string } {
  const formatter = new Intl.NumberFormat(locale, { minimumFractionDigits: 1 });
  const parts = formatter.formatToParts(1111.1);
  let decimal = '.';
  let group = ',';
  for (const part of parts) {
    if (part.type === 'decimal') decimal = part.value;
    if (part.type === 'group') group = part.value;
  }
  return { decimal, group };
}

/**
 * Parses a locale-formatted number string into a canonical float.
 * Returns NaN if the string cannot be interpreted as a valid number.
 *
 * @example
 * parseLocaleNumber('1.234,56', 'de-DE') // => 1234.56
 * parseLocaleNumber('1,234.56', 'en-US') // => 1234.56
 * parseLocaleNumber('€ 1.234,56', 'de-DE') // => 1234.56  (currency stripped)
 */
export function parseLocaleNumber(str: string, locale: string): number {
  const { decimal, group } = getSeparators(locale);

  // Strip currency symbols, whitespace, and non-numeric noise
  let cleaned = str.replace(/[^\d\s.,٫٬،]/gu, '').trim();

  // Escape special regex chars in separators
  const escGroup = group.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const escDecimal = decimal.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  // Remove group separators, replace decimal separator with '.'
  cleaned = cleaned
    .replace(new RegExp(escGroup, 'g'), '')
    .replace(new RegExp(escDecimal), '.');

  const value = parseFloat(cleaned);
  return value;
}

/**
 * Validates that a string is a parseable number in the given locale
 * and optionally checks it falls within [min, max].
 */
export function validateLocaleNumber(
  str: string,
  locale: string,
  opts: { min?: number; max?: number } = {}
): { valid: boolean; value: number; error?: string } {
  const value = parseLocaleNumber(str, locale);
  if (Number.isNaN(value)) {
    return { valid: false, value: NaN, error: `Cannot parse "${str}" as a number for locale ${locale}` };
  }
  if (opts.min !== undefined && value < opts.min) {
    return { valid: false, value, error: `Value ${value} is below minimum ${opts.min}` };
  }
  if (opts.max !== undefined && value > opts.max) {
    return { valid: false, value, error: `Value ${value} exceeds maximum ${opts.max}` };
  }
  return { valid: true, value };
}
```

## Worker Request Handler

```typescript
// worker.ts
import { validateLocaleNumber } from './utils/parseLocaleNumber';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const acceptLanguage = request.headers.get('Accept-Language') ?? 'en-US';
    // Take the first locale tag (e.g., "de-DE" from "de-DE,de;q=0.9")
    const locale = acceptLanguage.split(',')[0].trim().split(';')[0].trim();

    const body = await request.formData();
    const rawPrice = body.get('price') as string | null;

    if (!rawPrice) {
      return Response.json({ error: 'Missing price field' }, { status: 400 });
    }

    const result = validateLocaleNumber(rawPrice, locale, { min: 0, max: 1_000_000 });
    if (!result.valid) {
      return Response.json({ error: result.error }, { status: 422 });
    }

    // Store canonical float in D1
    await env.DB.prepare(
      'INSERT INTO products (price_canonical, price_locale, locale) VALUES (?, ?, ?)'
    )
      .bind(result.value, rawPrice, locale)
      .run();

    // Re-format for the response in the user's locale
    const formatted = new Intl.NumberFormat(locale, {
      style: 'currency',
      currency: 'EUR',
    }).format(result.value);

    return Response.json({ canonical: result.value, formatted });
  },
};
```

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS products (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  price_canonical REAL    NOT NULL,   -- canonical IEEE-754 float
  price_locale    TEXT    NOT NULL,   -- original user input
  locale          TEXT    NOT NULL,   -- e.g. "de-DE"
  created_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_products_price ON products(price_canonical);
```

## Returning Locale-Formatted Output

When reading rows back, re-format `price_canonical` with the requesting client's locale:

```typescript
async function formatProductPrice(canonical: number, acceptLanguage: string): Promise<string> {
  const locale = acceptLanguage.split(',')[0].trim().split(';')[0].trim();
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
  }).format(canonical);
}
```

Never store the formatted string as the source of truth — always store the canonical float.

## Anti-patterns

- **Using `parseFloat()` directly on locale strings** — silently truncates at the first unexpected character, producing wrong values without throwing.
- **Storing formatted strings in D1** — makes arithmetic queries (`SUM`, `AVG`, range filters) impossible without re-parsing.
- **Guessing the locale from IP alone** — IP geolocation gives a country, not a locale; a French-speaking user in Canada may expect `fr-CA` formatting. Prefer `Accept-Language`.
- **Hardcoding separator characters** — `/,/g` to strip thousands separators will corrupt Swiss or Indian formatted numbers.

## Gotchas

- `Intl.NumberFormat.formatToParts()` is available in Workers but the exact separator characters depend on the ICU data bundled with V8 in the runtime version — test with real locale strings.
- Arabic-Indic digits (`٠١٢٣`) are valid in `ar` locales; the regex `[^\d]` only strips ASCII digits — use `\p{N}` (Unicode numeric) with the `u` flag if you need to support them.
- When a user pastes a number from a spreadsheet, the thousands separator may be a non-breaking space (` `) — include it in your strip pattern.
- `minimumFractionDigits` affects the sentinel format — use `{ minimumFractionDigits: 1 }` consistently so the decimal part always appears.

## Verification

```bash
# Run unit tests locally with Vitest + @cloudflare/vitest-pool-workers
npx vitest run src/utils/parseLocaleNumber.test.ts

# Quick smoke test against a deployed Worker
curl -X POST https://my-worker.example.workers.dev/price \
  -H 'Accept-Language: de-DE,de;q=0.9' \
  -F 'price=1.234,56'
# Expected: {"canonical":1234.56,"formatted":"1.234,56 €"}

curl -X POST https://my-worker.example.workers.dev/price \
  -H 'Accept-Language: en-US,en;q=0.9' \
  -F 'price=1,234.56'
# Expected: {"canonical":1234.56,"formatted":"€1,234.56"}
```

## Related

- `intl-relativetimeformat-edge-localization-workers.md`
- `locale-aware-sorting-d1-sqlite-icu.md`
- `bidi-text-rendering-rtl-mixed-content-workers.md`

## Sources

- MDN Intl.NumberFormat.prototype.formatToParts() — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/formatToParts
- Cloudflare Workers Runtime APIs — https://developers.cloudflare.com/workers/runtime-apis/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
