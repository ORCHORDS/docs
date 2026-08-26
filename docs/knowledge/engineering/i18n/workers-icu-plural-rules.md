# ICU Plural Rules with Intl.PluralRules in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your internationalized Worker returns strings like "1 items in cart" or hard-codes English plural logic (`n === 1 ? 'item' : 'items'`). This breaks for Russian (6 plural forms), Arabic (up to 6 forms), Polish (4 forms), and languages that require a "zero" or "few" form English lacks. You need a correct, CLDR-backed plural selection system that works entirely within the Worker runtime.

## Context

`Intl.PluralRules` is part of the ECMA-402 specification and is available in all modern V8 builds, including Cloudflare Workers. It implements the Unicode Common Locale Data Repository (CLDR) plural rule algorithm. CLDR defines up to six plural categories per locale:

| Category | English example | Russian example            |
|----------|-----------------|----------------------------|
| `zero`   | (not used)      | (not used in `ru`)         |
| `one`    | 1 item          | 1 предмет (1, 21, 31…)     |
| `two`    | (not used)      | (not used in `ru`)         |
| `few`    | (not used)      | 2 предмета (2-4, 22-24…)   |
| `many`   | (not used)      | 5 предметов (5-20, 25-30…) |
| `other`  | 2 items         | 0 предметов                |

Ordinal plurals ("1st", "2nd", "3rd") use a separate `type: 'ordinal'` rule set.

## Solution

```typescript
// workers-icu-plural-rules.ts
// Plural-form selection for Cloudflare Workers using Intl.PluralRules

export interface Env {
  DB: D1Database;    // stores plural-form message strings
  TRANS_KV: KVNamespace; // caches compiled translation catalogs
}

// ─── 1. Types ─────────────────────────────────────────────────────────────

type PluralCategory = 'zero' | 'one' | 'two' | 'few' | 'many' | 'other';

/**
 * A plural-form message entry stored in D1.
 * All six CLDR categories are nullable; 'other' must be non-null.
 */
export interface PluralMessage {
  key: string;
  locale: string;
  zero: string | null;
  one: string | null;
  two: string | null;
  few: string | null;
  many: string | null;
  other: string;          // required fallback
}

// ─── 2. PluralRules resolver ──────────────────────────────────────────────

/** Memoized Intl.PluralRules instances (cardinal). */
const cardinalRulesCache = new Map<string, Intl.PluralRules>();
function getCardinalRules(locale: string): Intl.PluralRules {
  if (!cardinalRulesCache.has(locale)) {
    cardinalRulesCache.set(locale, new Intl.PluralRules(locale, { type: 'cardinal' }));
  }
  return cardinalRulesCache.get(locale)!;
}

/** Memoized Intl.PluralRules instances (ordinal). */
const ordinalRulesCache = new Map<string, Intl.PluralRules>();
function getOrdinalRules(locale: string): Intl.PluralRules {
  if (!ordinalRulesCache.has(locale)) {
    ordinalRulesCache.set(locale, new Intl.PluralRules(locale, { type: 'ordinal' }));
  }
  return ordinalRulesCache.get(locale)!;
}

/**
 * Selects the correct plural form string from a PluralMessage
 * for a given count using CLDR cardinal rules.
 *
 * @param msg    - PluralMessage object with per-category strings
 * @param count  - The numeric count to pluralise
 * @param locale - BCP 47 locale string
 * @returns      - The selected string with `{{count}}` interpolated
 */
export function selectPlural(
  msg: PluralMessage,
  count: number,
  locale: string
): string {
  const rules = getCardinalRules(locale);
  const category = rules.select(count) as PluralCategory;
  const template: string =
    msg[category] ?? msg.other;  // fall back to 'other' if category is null
  return interpolate(template, { count });
}

/**
 * Selects the ordinal plural form (1st, 2nd, 3rd, 4th…).
 * The caller provides ordinal-form strings keyed by CLDR category.
 */
export function selectOrdinal(
  forms: Record<PluralCategory, string>,
  count: number,
  locale: string
): string {
  const rules = getOrdinalRules(locale);
  const category = rules.select(count) as PluralCategory;
  const template = forms[category] ?? forms.other;
  return interpolate(template, { count });
}

// ─── 3. String interpolation ──────────────────────────────────────────────

/**
 * Replaces `{{key}}` placeholders in a template string with values
 * from the provided data map.
 *
 * @example interpolate('{{count}} items', { count: 3 }) => '3 items'
 */
export function interpolate(
  template: string,
  data: Record<string, string | number>
): string {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key) =>
    key in data ? String(data[key]) : `{{${key}}}`
  );
}

// ─── 4. D1 storage helpers ────────────────────────────────────────────────

/** D1 DDL — run once during migration. */
export const PLURAL_TABLE_DDL = `
CREATE TABLE IF NOT EXISTS plural_messages (
  key     TEXT NOT NULL,
  locale  TEXT NOT NULL,
  zero    TEXT,
  one     TEXT,
  two     TEXT,
  few     TEXT,
  many    TEXT,
  other   TEXT NOT NULL,
  PRIMARY KEY (key, locale)
);
CREATE INDEX IF NOT EXISTS idx_pm_locale ON plural_messages (locale);
`;

/** Upserts a plural message record. */
export async function upsertPluralMessage(
  db: D1Database,
  msg: PluralMessage
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO plural_messages (key, locale, zero, one, two, few, many, other)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)
       ON CONFLICT(key, locale) DO UPDATE SET
         zero=excluded.zero, one=excluded.one, two=excluded.two,
         few=excluded.few, many=excluded.many, other=excluded.other`
    )
    .bind(
      msg.key, msg.locale,
      msg.zero, msg.one, msg.two,
      msg.few, msg.many, msg.other
    )
    .run();
}

/** Fetches a single plural message from D1. */
export async function fetchPluralMessage(
  db: D1Database,
  key: string,
  locale: string
): Promise<PluralMessage | null> {
  return db
    .prepare('SELECT * FROM plural_messages WHERE key=?1 AND locale=?2')
    .bind(key, locale)
    .first<PluralMessage>();
}

/** Fetches all messages for a locale and caches them in KV. */
export async function loadCatalog(
  db: D1Database,
  kv: KVNamespace,
  locale: string
): Promise<Map<string, PluralMessage>> {
  const cacheKey = `plural-catalog:${locale}`;
  const cached = await kv.get(cacheKey, 'json') as PluralMessage[] | null;

  let rows: PluralMessage[];
  if (cached) {
    rows = cached;
  } else {
    const result = await db
      .prepare('SELECT * FROM plural_messages WHERE locale=?1')
      .bind(locale)
      .all<PluralMessage>();
    rows = result.results;
    // Cache for 5 minutes (translators update infrequently during a session)
    await kv.put(cacheKey, JSON.stringify(rows), { expirationTtl: 300 });
  }

  const catalog = new Map<string, PluralMessage>();
  for (const row of rows) catalog.set(row.key, row);
  return catalog;
}

// ─── 5. Worker handler ────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const locale = url.searchParams.get('locale') ?? 'en';
    const countStr = url.searchParams.get('count') ?? '1';
    const key = url.searchParams.get('key') ?? 'cart.items';
    const count = parseInt(countStr, 10);

    if (isNaN(count)) {
      return new Response('Invalid count', { status: 400 });
    }

    const catalog = await loadCatalog(env.DB, env.TRANS_KV, locale);
    const msg = catalog.get(key);

    if (!msg) {
      return new Response(`Key not found: ${key}`, { status: 404 });
    }

    const text = selectPlural(msg, count, locale);
    return Response.json({ locale, key, count, text });
  },
};

// ─── 6. Ordinal suffix helper (English example) ───────────────────────────

/** English ordinal forms for use with selectOrdinal(). */
export const EN_ORDINAL_FORMS: Record<PluralCategory, string> = {
  zero:  '{{count}}th',
  one:   '{{count}}st',   // 1st, 21st, 31st
  two:   '{{count}}nd',   // 2nd, 22nd, 32nd
  few:   '{{count}}rd',   // 3rd, 23rd, 33rd
  many:  '{{count}}th',
  other: '{{count}}th',   // 4th–20th, etc.
};
// Usage: selectOrdinal(EN_ORDINAL_FORMS, 3, 'en') => '3rd'
// Usage: selectOrdinal(EN_ORDINAL_FORMS, 21, 'en') => '21st'
```

## Implementation Details

**CLDR plural categories** — `Intl.PluralRules.prototype.select()` returns one of the six CLDR category strings. Not all categories are used by every locale: English uses only `one` and `other`; Arabic uses all six; Japanese and Chinese use only `other`.

**Memoizing `Intl.PluralRules`** — Constructing a new `Intl.PluralRules` object carries non-trivial overhead because it loads CLDR data for the locale. The module-level `Map` caches instances across requests in the same Worker isolate lifetime.

**D1 schema rationale** — Storing all six plural form columns as nullable `TEXT` keeps each message in a single row and avoids a per-category JOIN. The `other` column is `NOT NULL` because every locale defines the `other` category as a catch-all fallback.

**KV caching layer** — D1 reads are fast but not zero-latency; for every request that needs the full catalog (e.g., a page with 40 strings), a 5-minute KV cache cuts D1 reads by ~99% during steady-state traffic.

**Fractional counts** — `Intl.PluralRules` handles decimal numbers: `rules.select(1.5)` returns `'other'` in English but `'one'` in French. Pass the raw numeric value (not a pre-formatted string) to `select()`.

## Anti-patterns

- **Do not** implement plural selection with `n === 1 ? 'one' : 'other'` — this is correct only for a handful of Western European languages.
- **Do not** store plural forms as a JSON column in D1 — individual indexed columns allow partial updates and are faster to read.
- **Do not** call `new Intl.PluralRules()` on every request — cache instances as shown above.
- **Do not** rely on the English `other` form as a fallback for other locales — Russian's `other` form uses the genitive plural (not nominative singular) and differs from English grammar entirely.

## Gotchas

- `Intl.PluralRules.prototype.selectRange()` (for ranges like "1–3 items") is available in V8 >= 10.4; check Worker compatibility flags before using.
- The `count` value passed to `select()` should be the *actual* numeric value, not a formatted string — passing `"1,000"` will produce NaN-like behaviour.
- Arabic plural rules change based on the *last two digits* of the number (modulo 100). `Intl.PluralRules` handles this automatically; manual implementations often miss it.
- Languages like Slovenian and Maltese have `two` and `few` forms with non-obvious rules. Always test with values from the CLDR plural test cases: https://github.com/unicode-org/cldr/blob/main/common/testData/plurals/pluralRules.xml

## Verification

```typescript
import { describe, it, expect } from 'vitest';
import {
  selectPlural, selectOrdinal, interpolate,
  EN_ORDINAL_FORMS, type PluralMessage
} from './workers-icu-plural-rules';

const EN_ITEMS: PluralMessage = {
  key: 'cart.items', locale: 'en',
  zero: null, two: null, few: null, many: null,
  one: '{{count}} item',
  other: '{{count}} items',
};

const RU_ITEMS: PluralMessage = {
  key: 'cart.items', locale: 'ru',
  zero: null, two: null,
  one:   '{{count}} предмет',
  few:   '{{count}} предмета',
  many:  '{{count}} предметов',
  other: '{{count}} предметов',
};

describe('selectPlural (English)', () => {
  it('1 => one form',    () => expect(selectPlural(EN_ITEMS, 1, 'en')).toBe('1 item'));
  it('2 => other form',  () => expect(selectPlural(EN_ITEMS, 2, 'en')).toBe('2 items'));
  it('0 => other form',  () => expect(selectPlural(EN_ITEMS, 0, 'en')).toBe('0 items'));
});

describe('selectPlural (Russian)', () => {
  it('1  => one  (предмет)',   () => expect(selectPlural(RU_ITEMS, 1, 'ru')).toBe('1 предмет'));
  it('2  => few  (предмета)',  () => expect(selectPlural(RU_ITEMS, 2, 'ru')).toBe('2 предмета'));
  it('5  => many (предметов)', () => expect(selectPlural(RU_ITEMS, 5, 'ru')).toBe('5 предметов'));
  it('21 => one  (предмет)',   () => expect(selectPlural(RU_ITEMS, 21, 'ru')).toBe('21 предмет'));
});

describe('selectOrdinal (English)', () => {
  it('1  => 1st',  () => expect(selectOrdinal(EN_ORDINAL_FORMS, 1, 'en')).toBe('1st'));
  it('2  => 2nd',  () => expect(selectOrdinal(EN_ORDINAL_FORMS, 2, 'en')).toBe('2nd'));
  it('3  => 3rd',  () => expect(selectOrdinal(EN_ORDINAL_FORMS, 3, 'en')).toBe('3rd'));
  it('4  => 4th',  () => expect(selectOrdinal(EN_ORDINAL_FORMS, 4, 'en')).toBe('4th'));
  it('11 => 11th', () => expect(selectOrdinal(EN_ORDINAL_FORMS, 11, 'en')).toBe('11th'));
  it('21 => 21st', () => expect(selectOrdinal(EN_ORDINAL_FORMS, 21, 'en')).toBe('21st'));
});

describe('interpolate', () => {
  it('replaces single placeholder', () => expect(interpolate('{{count}} items', { count: 5 })).toBe('5 items'));
  it('leaves unknown placeholder',  () => expect(interpolate('{{count}} {{unit}}', { count: 3 })).toBe('3 {{unit}}'));
});
```

## Related

- `documentation/docs/policies/i18n/workers-currency-formatting-intl.md` — number formatting with locale-specific decimal/grouping separators
- `documentation/docs/policies/i18n/workers-locale-negotiation.md` — selecting the right locale before looking up plural strings
- `documentation/docs/policies/i18n/translation-import-export-d1.md` — importing plural-form catalogs from XLIFF/PO files into D1
- CLDR plural rules chart: https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html

## Sources

- ECMA-402 Intl.PluralRules specification: https://tc39.es/ecma402/#pluralrules-objects
- Unicode CLDR Plural Rules: https://cldr.unicode.org/index/cldr-spec/plural-rules
- CLDR plural test data: https://github.com/unicode-org/cldr/blob/main/common/testData/plurals/pluralRules.xml
- MDN Intl.PluralRules: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules
- Cloudflare Workers D1 documentation: https://developers.cloudflare.com/d1/
