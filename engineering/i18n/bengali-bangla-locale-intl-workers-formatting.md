# Bengali and Bangla Locale Intl Formatting in Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Cloudflare Worker serves Bengali content for Bangladesh (`bn-BD`) or India (`bn-IN`) and you encounter wrong digit rendering (Bengali vs Western numerals), misformatted dates, unexpected currency symbols (BDT ৳ vs INR ₹), and sort order issues in D1 queries. Numbers formatted on the server differ from what users expect on the client.

---

## Context

Bengali (`bn`) is spoken by ~230 million people across Bangladesh and India. The two primary locales differ in currency, number grouping conventions, and default digit sets:

| Feature | `bn-BD` (Bangladesh) | `bn-IN` (India) |
|---------|---------------------|-----------------|
| Currency | BDT (৳) | INR (₹) |
| Digit set | Bengali digits ০–৯ by default | Bengali digits ০–৯ by default |
| Number grouping | South Asian (2+2+3) | South Asian (2+2+3) |
| Calendar | Gregorian (ISO) | Gregorian (ISO) |
| Time zone | Asia/Dhaka (UTC+6) | Asia/Kolkata (UTC+5:30) |

Both locales use **Bengali digits** (`০ ১ ২ ৩ ৪ ৫ ৬ ৭ ৮ ৯`) by default in V8 ICU, which surprises teams expecting Western Arabic numerals. Many Bangladeshi and Indian Bengali users on the web actually prefer Western digits; the decision should be data-driven and stored per user in KV.

---

## 1. Locale Detection for Bangladesh vs India

```typescript
// src/locale-detect-bn.ts
export function detectBengaliLocale(
  request: Request,
): 'bn-BD' | 'bn-IN' | null {
  const cf = (request as any).cf as IncomingRequestCfProperties | undefined;
  const country = cf?.country;
  if (country === 'BD') return 'bn-BD';
  if (country === 'IN') return 'bn-IN';

  const accept = request.headers.get('Accept-Language') ?? '';
  for (const part of accept.split(',')) {
    const tag = part.trim().split(';')[0].toLowerCase();
    if (tag === 'bn-bd' || tag === 'bn_bd') return 'bn-BD';
    if (tag === 'bn-in' || tag === 'bn_in') return 'bn-IN';
    if (tag.startsWith('bn')) {
      // Default to BD if region is omitted
      return 'bn-BD';
    }
  }
  return null;
}
```

---

## 2. Number Formatting — Bengali vs Western Digits

```typescript
// src/bn-number-format.ts

/** Return the user's preferred digit system from KV or default to 'beng' */
async function getDigitSystem(
  userId: string,
  kv: KVNamespace,
): Promise<'beng' | 'latn'> {
  const pref = await kv.get(`user:${userId}:digits`);
  return pref === 'latn' ? 'latn' : 'beng';
}

export function formatNumber(
  value: number,
  locale: string,
  digitSystem: 'beng' | 'latn' = 'beng',
): string {
  // Append Unicode extension for numbering system
  const tag = `${locale}-u-nu-${digitSystem}`;
  return new Intl.NumberFormat(tag, { useGrouping: true }).format(value);
}

// South Asian grouping: 1,00,00,000 (not 10,000,000)
// Both bn-BD and bn-IN use this by default.
// Verify: formatNumber(10000000, 'bn-BD', 'latn') => "১,০০,০০,০০০" with beng
//         or "1,00,00,000" with latn

export function formatPercent(
  value: number,
  locale: string,
  digitSystem: 'beng' | 'latn' = 'beng',
): string {
  const tag = `${locale}-u-nu-${digitSystem}`;
  return new Intl.NumberFormat(tag, {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value / 100);
}
```

---

## 3. Currency Formatting — BDT and INR

```typescript
// src/bn-currency.ts
export function formatCurrency(
  amount: number,
  locale: 'bn-BD' | 'bn-IN',
  digitSystem: 'beng' | 'latn' = 'beng',
): string {
  const currency = locale === 'bn-BD' ? 'BDT' : 'INR';
  const tag = `${locale}-u-nu-${digitSystem}`;
  return new Intl.NumberFormat(tag, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

// BDT: "৳১,০০০.০০" (beng) or "৳1,000.00" (latn)
// INR: "₹১,০০০.০০" (beng) or "₹1,000.00" (latn)
```

---

## 4. Date and Time Formatting

```typescript
// src/bn-datetime.ts

/** Time zones for each Bengali locale */
const TZ: Record<string, string> = {
  'bn-BD': 'Asia/Dhaka',
  'bn-IN': 'Asia/Kolkata',
};

export function formatDate(date: Date, locale: string): string {
  const timeZone = TZ[locale] ?? 'UTC';
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone,
  }).format(date);
}

export function formatDateTime(date: Date, locale: string): string {
  const timeZone = TZ[locale] ?? 'UTC';
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone,
  }).format(date);
}

export function formatRelative(date: Date, locale: string): string {
  const rtf = new Intl.RelativeTimeFormat(locale, {
    numeric: 'auto',
    style: 'long',
  });
  const diffMs = date.getTime() - Date.now();
  const diffDays = Math.round(diffMs / 86_400_000);
  if (Math.abs(diffDays) < 1) {
    return rtf.format(Math.round(diffMs / 3_600_000), 'hour');
  }
  return rtf.format(diffDays, 'day');
}

// bn-BD: "২০২৬ জানুয়ারী ১" (beng default)
// bn-IN: "১ জানুয়ারী, ২০২৬"
```

---

## 5. Plural Rules for Bengali

Bengali plural rules are simple: the language has a single plural form (other) — it does not inflect nouns for count. However ICU `PluralRules` still returns `'other'` for all values, so your message catalog needs only `one` and `other` keys, and Bengali will always use `other`.

```typescript
// src/bn-plural.ts
const pr = new Intl.PluralRules('bn-BD');

export function pluralize(
  count: number,
  one: string,
  other: string,
): string {
  // Bengali: PluralRules always returns 'other' for count != 1
  // but CLDR bn uses 'one' for 1 and 'other' for everything else
  return pr.select(count) === 'one' ? one : other;
}

// Usage: pluralize(1, '১টি পণ্য', '{{n}}টি পণ্য')
// Note: Bengali uses classifiers (টি, জন, খানা) not true plural suffixes.
// The classifier is baked into the translation string, not derived by code.
```

---

## 6. Collation and D1 Sorting

Bengali text in D1 requires explicit collation because SQLite's default `ORDER BY` uses byte order which does not match CLDR Bengali tailoring.

```typescript
// src/bn-d1-sort.ts
import { formatISO } from './utils';

export async function fetchSortedProducts(
  db: D1Database,
  locale: 'bn-BD' | 'bn-IN',
): Promise<{ name: string; price: number }[]> {
  // Fetch unsorted rows, sort in Worker with Intl.Collator
  const { results } = await db
    .prepare('SELECT name, price FROM products WHERE locale = ?')
    .bind(locale)
    .all<{ name: string; price: number }>();

  const collator = new Intl.Collator(locale, {
    sensitivity: 'variant',
    usage: 'sort',
  });

  return results.sort((a, b) => collator.compare(a.name, b.name));
}
```

---

## Anti-patterns

- **Hardcoding "৳" or "₹" as a string prefix** — Use `Intl.NumberFormat` with `style: 'currency'`; the symbol position and spacing follow CLDR and differ between locales.
- **Passing `bn` without a region subtag** — `bn` resolves to `bn-BD` in most ICU builds but this is not guaranteed. Always use the full `bn-BD` or `bn-IN` tag.
- **Assuming Bengali users want Bengali digits** — Many web users in Bangladesh and India prefer `latn` digits; store and respect per-user preference.
- **Formatting numbers with `.toLocaleString()` on Node** — CF Workers uses V8 ICU, not Node; APIs are the same but test in a Worker environment, not locally, as ICU data versions differ.
- **Using `.length` on Bengali strings** — Bengali grapheme clusters span multiple code points. Use `Intl.Segmenter` with `granularity: 'grapheme'` to count visual characters.

---

## Gotchas

- **South Asian grouping**: `10,000,000` groups as `1,00,00,000` in both `bn-BD` and `bn-IN`. This matches the South Asian numbering system (lakh, crore) and is correct; do not override unless a specific product requirement demands it.
- **BDT `narrowSymbol`**: `Intl.NumberFormat` with `currencyDisplay: 'narrowSymbol'` returns `৳` for BDT in most ICU versions; `symbol` may return `BDT` or `৳` depending on CLDR version — test explicitly.
- **`bn-IN` vs `hi-IN` overlap**: Both are used in West Bengal and other Indian states. If country is `IN` and `Accept-Language` is ambiguous, check if the user comes from West Bengal geo data (unavailable from CF directly) or default to `hi-IN` for India and only use `bn-IN` if the tag explicitly requests it.
- **Time zone for Bangladesh**: `Asia/Dhaka` is UTC+6 with no DST. `Asia/Kolkata` is UTC+5:30 with no DST. Both are fixed offsets; you will not encounter DST surprises here.
- **`Intl.RelativeTimeFormat` unit names**: Bengali unit names are correct in modern V8 ICU, but verify against your target ICU version by logging the output during development.

---

## Verification

```typescript
// Run with: wrangler dev, then GET /verify-bn
export default {
  async fetch(): Promise<Response> {
    const results: Record<string, string> = {
      num_beng_BD: new Intl.NumberFormat('bn-BD-u-nu-beng').format(1000000),
      // Expected: "১০,০০,০০০"
      num_latn_BD: new Intl.NumberFormat('bn-BD-u-nu-latn').format(1000000),
      // Expected: "10,00,000"
      curr_BD: new Intl.NumberFormat('bn-BD', {
        style: 'currency', currency: 'BDT',
      }).format(1500.5),
      curr_IN: new Intl.NumberFormat('bn-IN', {
        style: 'currency', currency: 'INR',
      }).format(1500.5),
      date_BD: new Intl.DateTimeFormat('bn-BD', {
        dateStyle: 'long', timeZone: 'Asia/Dhaka',
      }).format(new Date('2026-08-23')),
      plural_one: new Intl.PluralRules('bn-BD').select(1),
      // Expected: "one"
      plural_two: new Intl.PluralRules('bn-BD').select(2),
      // Expected: "other"
    };
    return Response.json(results);
  },
};
```

---

## Related

- `indic-script-rendering.md`
- `locale-aware-number-currency-formatting.md`
- `number-system-locale-workers-d1.md`
- `d1-locale-aware-date-range-queries.md`
- `unicode-collation-d1-sqlite-locale-sort.md`
- `intl-api-workers-edge-formatting.md`

---

## Sources

- CLDR bn data: https://github.com/unicode-org/cldr/blob/main/common/main/bn.xml
- CLDR bn_BD data: https://github.com/unicode-org/cldr/blob/main/common/main/bn_BD.xml
- Unicode Bengali block U+0980–U+09FF: https://www.unicode.org/charts/PDF/U0980.pdf
- ICU Plural Rules — Bengali: https://unicode-org.github.io/cldr-staging/charts/latest/supplemental/language_plural_rules.html
- South Asian numbering: https://en.wikipedia.org/wiki/Indian_numbering_system
- Cloudflare Workers geolocation: https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
