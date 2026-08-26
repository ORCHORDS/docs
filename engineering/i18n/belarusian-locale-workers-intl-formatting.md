# Belarusian Locale in Cloudflare Workers — i18n Formatting

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You operate a service for Belarusian (`be`) users and find that `Intl` output defaults
to Russian (`ru`) formatting, month names appear in Russian Cyrillic, currency amounts
use the wrong grouping separator, or plural rules silently apply Russian patterns instead
of the distinctly different Belarusian ones. This article covers correct `be` / `be-BY`
handling in Cloudflare Workers.

---

## Context

- **BCP 47 tags**: `be` (Belarusian), `be-BY` (Belarus), `be-Latn` (Łacinka — minority
  Latin script, minimal CLDR coverage)
- **CLDR coverage**: `be` and `be-BY` are in CLDR 45; `be-Latn` is in the registry but
  has nearly no data
- **Currency**: Belarusian Ruble (`BYN`), introduced 2016 (replacing `BYR`)
- **Calendar**: Gregorian; week starts Monday
- **Number format**: comma `,` for decimal, space ` ` for grouping
- **Plural rules**: `one`, `few`, `many`, `other` — four categories, distinct from Russian

---

## 1 — Locale Detection and BYR/BYN Guard

```typescript
// src/locale/belarusian.ts

export type BeLocale = "be-BY" | "be";

/**
 * Resolves Belarusian locale from Accept-Language.
 * Explicitly guards against the old BYR currency code (pre-2016 redenomination).
 */
export function resolveBelarusianLocale(
  acceptLanguage: string | null
): BeLocale {
  if (!acceptLanguage) return "be-BY";

  const tags = acceptLanguage
    .split(",")
    .map((s) => s.split(";")[0].trim().toLowerCase());

  for (const tag of tags) {
    if (tag.startsWith("be")) return "be-BY";
  }
  return "be-BY";
}

/** Validates that no code still references the old BYR code (redenominated 2016). */
export function assertBYN(currency: string): void {
  if (currency.toUpperCase() === "BYR") {
    throw new Error(
      "BYR is obsolete since 2016-07-01; use BYN (Belarusian Ruble, ISO 4217)."
    );
  }
}
```

---

## 2 — Date Formatting in Belarusian

```typescript
// src/formatters/belarusian-date.ts
import type { BeLocale } from "../locale/belarusian";

const LONG_OPTS: Intl.DateTimeFormatOptions = {
  weekday: "long",
  year: "numeric",
  month: "long",
  day: "numeric",
};

const SHORT_OPTS: Intl.DateTimeFormatOptions = {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
};

const TIME_OPTS: Intl.DateTimeFormatOptions = {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
};

export function formatBelarusianDate(
  date: Date,
  locale: BeLocale,
  style: "long" | "short" = "long"
): string {
  return new Intl.DateTimeFormat(
    locale,
    style === "long" ? LONG_OPTS : SHORT_OPTS
  ).format(date);
}

export function formatBelarusianDateTime(date: Date, locale: BeLocale): string {
  const datePart = new Intl.DateTimeFormat(locale, SHORT_OPTS).format(date);
  const timePart = new Intl.DateTimeFormat(locale, TIME_OPTS).format(date);
  return `${datePart}, ${timePart}`;
}

// be-BY long  → "нядзеля, 23 жніўня 2026 г."
// be-BY short → "23.08.2026"
// Note: month in genitive case for long form ("жніўня" not "жнівень")
```

---

## 3 — BYN Currency Formatting

```typescript
// src/formatters/belarusian-currency.ts
import type { BeLocale } from "../locale/belarusian";

export function formatBYN(amount: number, locale: BeLocale): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "BYN",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

// be-BY → "1 234,56 Br"  or "1 234,56 BYN"  (CLDR symbol varies by build)

export function formatBelarusianNumber(
  value: number,
  locale: BeLocale,
  fractionDigits = 2
): string {
  return new Intl.NumberFormat(locale, {
    style: "decimal",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}
// be → "1 234,56"  — space grouping, comma decimal

export function formatBelarusianPercent(
  value: number,
  locale: BeLocale
): string {
  return new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}
// be → "12,5 %"
```

---

## 4 — Belarusian Plural Rules (one / few / many / other)

Belarusian plural rules follow a pattern shared with Russian and Ukrainian but with
distinct boundaries. The four-category system must be implemented precisely.

```typescript
// src/i18n/belarusian-plural.ts

/**
 * Belarusian plural categories (CLDR):
 *   one:  n % 10 == 1 && n % 100 != 11
 *   few:  n % 10 in 2..4 && n % 100 not in 12..14
 *   many: n % 10 == 0 || n % 10 in 5..9 || n % 100 in 11..14
 *   other: (fractions)
 */
const BE_PLURAL = new Intl.PluralRules("be");

const BOOK_FORMS = {
  one:   "{n} кніга",
  few:   "{n} кнігі",
  many:  "{n} кніг",
  other: "{n} кнігі",
} as const;

type BePluralForm = keyof typeof BOOK_FORMS;

export function beBookCount(count: number): string {
  const rule = BE_PLURAL.select(count) as BePluralForm;
  const form = BOOK_FORMS[rule] ?? BOOK_FORMS.many;
  return form.replace("{n}", String(count));
}

// count=1  → "1 кніга"
// count=2  → "2 кнігі"
// count=5  → "5 кніг"
// count=11 → "11 кніг"   (11 is 'many', NOT 'one')
// count=21 → "21 кніга"  (21 % 10 == 1 && 21 % 100 != 11)

export function beVerifyPlurals(): void {
  const cases: Array<[number, string]> = [
    [1, "one"], [2, "few"], [5, "many"],
    [11, "many"], [21, "one"], [100, "many"],
  ];
  for (const [n, expected] of cases) {
    const got = BE_PLURAL.select(n);
    if (got !== expected) {
      console.error(`be plural(${n}): expected ${expected}, got ${got}`);
    }
  }
}
```

---

## 5 — Workers Handler with Accept-Language Negotiation

```typescript
// src/handlers/be-handler.ts
import { resolveBelarusianLocale } from "../locale/belarusian";
import { formatBelarusianDate } from "../formatters/belarusian-date";
import { formatBYN } from "../formatters/belarusian-currency";
import { beBookCount } from "../i18n/belarusian-plural";

export async function belarusianHandler(
  request: Request,
  env: Env
): Promise<Response> {
  const locale = resolveBelarusianLocale(
    request.headers.get("Accept-Language")
  );

  const today = formatBelarusianDate(new Date(), locale, "long");
  const examplePrice = formatBYN(1_234.56, locale);
  const bookCount = beBookCount(21);

  const bundle = await env.KV.get<Record<string, string>>(
    `i18n:${locale}`,
    "json"
  );

  return Response.json(
    { locale, today, examplePrice, bookCount, bundle },
    {
      headers: {
        "Content-Language": locale,
        "Vary": "Accept-Language",
      },
    }
  );
}
```

---

## 6 — Comparative Table: be vs ru Plural Rules

A common mistake is treating Belarusian and Russian plural rules as identical. They are
structurally the same **form** but differ in how forms are applied to specific words due
to stress patterns, vowel reduction, and orthographic conventions.

```typescript
// src/i18n/be-ru-comparison.ts

// Demonstrate the difference in noun forms for the same count:
const RU_DAY_FORMS = { one: "день", few: "дня", many: "дней", other: "дней" };
const BE_DAY_FORMS = { one: "дзень", few: "дні",  many: "дзён",  other: "дзён" };

const RU_PLURAL = new Intl.PluralRules("ru");
const BE_PLURAL = new Intl.PluralRules("be");

export function compareDayCount(count: number): { ru: string; be: string } {
  const ruKey = RU_PLURAL.select(count) as keyof typeof RU_DAY_FORMS;
  const beKey = BE_PLURAL.select(count) as keyof typeof BE_DAY_FORMS;
  return {
    ru: `${count} ${RU_DAY_FORMS[ruKey]}`,
    be: `${count} ${BE_DAY_FORMS[beKey]}`,
  };
}

// count=5 → { ru: "5 дней", be: "5 дзён" }
// These differ in the noun form — never reuse Russian strings for Belarusian
```

---

## Anti-patterns

- **Using `ru-BY` as a fallback for Belarusian** — Russian is a separate language;
  even in Belarus where Russian is also official, `be` users expect Belarusian.
- **Reusing Russian plural forms** for Belarusian — while the plural rule categories
  are structurally identical, the noun forms themselves differ.
- **Referencing `BYR`** (old Belarusian ruble) — it was redenominated 1:10000 in 2016;
  all modern prices must use `BYN`.
- **Assuming `be-Latn` (Łacinka) has CLDR formatting support** — it does not; always
  fall back to `be` for `Intl` calls.

---

## Gotchas

- Belarusian month names use the **genitive case** in full date strings: `студзеня,
  лютага, сакавіка...` — never nominative (`студзень`) in a formatted date.
- `Intl.DateTimeFormat("be")` in Workers V8 produces correct Belarusian month names;
  verify they are not falling through to Russian (`января` vs `студзеня`).
- The BYN has 2 decimal places (`kopeks`); unlike the Uzbek Som or Albanian Lek, you
  **must** include centimes for prices.
- `Intl.Collator("be")` sort order differs from Russian; Belarusian has the letter `Ў`
  (short U) which sorts between `У` and `Ф`.

---

## Verification

```typescript
// test/belarusian.test.ts
import { expect, test } from "vitest";
import { beBookCount } from "../src/i18n/belarusian-plural";
import { formatBYN } from "../src/formatters/belarusian-currency";
import { resolveBelarusianLocale } from "../src/locale/belarusian";

test("resolves be-BY from header", () => {
  expect(resolveBelarusianLocale("be,ru;q=0.8")).toBe("be-BY");
});

test("21 is 'one' form", () => {
  expect(beBookCount(21)).toContain("кніга");
});

test("11 is 'many' form (not one)", () => {
  expect(beBookCount(11)).toContain("кніг");
  expect(beBookCount(11)).not.toContain("кніга");
});

test("BYN includes 2 decimal places", () => {
  const result = formatBYN(50, "be-BY");
  // Should contain comma+two digits (e.g. "50,00 BYN")
  expect(result).toMatch(/,\d\d/);
});
```

Run: `npx vitest run test/belarusian.test.ts`

---

## Related

- `ukrainian-locale-workers-intl-cyrillic-collation.md` — parallel East Slavic language
- `serbian-locale-workers-intl-cyrillic-latin-dual.md` — dual-script Slavic pattern
- `pluralization-edge-cases-arabic-slavic.md` — Slavic plural edge cases in depth
- `unicode-collation-d1-sqlite-locale-sort.md` — SQLite collation for Cyrillic locales

---

## Sources

- CLDR 45 `be` locale: https://github.com/unicode-org/cldr/tree/main/common/main
- ICU plural rules `be`: https://unicode.org/cldr/charts/45/supplemental/language_plural_rules.html
- BYN ISO 4217 (effective 2016-07-01): https://www.iso.org/iso-4217-currency-codes.html
- Belarusian alphabet and Łacinka: https://en.wikipedia.org/wiki/Belarusian_alphabet
- Cloudflare Workers runtime APIs: https://developers.cloudflare.com/workers/runtime-apis/web-standards/
