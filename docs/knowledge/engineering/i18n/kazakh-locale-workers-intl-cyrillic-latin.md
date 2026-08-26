# Kazakh Locale in Cloudflare Workers — Cyrillic/Latin Dual-Script i18n

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Kazakhstan officially adopted a Latin-based Kazakh alphabet in 2017 (still rolling out),
while the majority of published content and OS settings remain Cyrillic (`kk-Cyrl-KZ`).
Your Workers API must serve both scripts simultaneously, route to the correct translation
bundle, and produce valid `Intl` output without silent fallbacks to Russian (`ru`).

---

## Context

- **BCP 47 tags**: `kk` (defaults to Cyrillic), `kk-Cyrl-KZ` (explicit Cyrillic), `kk-Latn-KZ` (new Latin)
- **CLDR coverage**: `kk` (Cyrillic) is well-covered in CLDR 45; `kk-Latn` has minimal data
- **Currency**: Kazakhstani Tenge (`KZT`), symbol `₸`
- **Calendar**: Gregorian; week starts Monday
- **Number separators**: space ` ` for grouping, comma `,` for decimal in `kk`
- **Plural rules**: two forms (`one` / `other`) — same structure as Uzbek

---

## 1 — Script-Aware Locale Resolution

```typescript
// src/locale/kazakh.ts

export type KkLocale = "kk-Cyrl-KZ" | "kk-Latn-KZ" | "kk";

/**
 * Parses Accept-Language and returns the appropriate Kazakh locale tag.
 * Defaults to kk-Cyrl-KZ (current majority script).
 */
export function resolveKazakhLocale(acceptLanguage: string | null): KkLocale {
  if (!acceptLanguage) return "kk-Cyrl-KZ";

  const tags = acceptLanguage
    .split(",")
    .map((s) => s.split(";")[0].trim().toLowerCase());

  for (const tag of tags) {
    if (tag.startsWith("kk-latn")) return "kk-Latn-KZ";
    if (tag.startsWith("kk-cyrl") || tag === "kk" || tag.startsWith("kk-kz")) {
      return "kk-Cyrl-KZ";
    }
  }
  return "kk-Cyrl-KZ";
}

/**
 * Maps a locale to its script name for feature flags / analytics.
 */
export function kkScriptName(locale: KkLocale): "Cyrillic" | "Latin" {
  return locale === "kk-Latn-KZ" ? "Latin" : "Cyrillic";
}
```

---

## 2 — Date and Time Formatting

```typescript
// src/formatters/kazakh-date.ts
import type { KkLocale } from "../locale/kazakh";

const SHORT_DATE: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
};

const LONG_DATE: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "long",
};

export function formatKazakhDate(
  date: Date,
  locale: KkLocale,
  style: "short" | "long" = "long"
): string {
  const opts = style === "short" ? SHORT_DATE : LONG_DATE;
  try {
    return new Intl.DateTimeFormat(locale, opts).format(date);
  } catch {
    // kk-Latn-KZ may have no CLDR data in the Workers V8 snapshot
    return new Intl.DateTimeFormat("kk-Cyrl-KZ", opts).format(date);
  }
}

// kk-Cyrl-KZ long → "жексенбі, 23 тамыз 2026 ж."
// kk-Cyrl-KZ short → "23.08.2026"
```

---

## 3 — Tenge Currency Formatting

```typescript
// src/formatters/kazakh-currency.ts
import type { KkLocale } from "../locale/kazakh";

export function formatTenge(amount: number, locale: KkLocale): string {
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: "KZT",
      maximumFractionDigits: 0, // Tenge has no widely-used fractional unit (tiyn)
    }).format(amount);
  } catch {
    return new Intl.NumberFormat("kk", {
      style: "currency",
      currency: "KZT",
      maximumFractionDigits: 0,
    }).format(amount);
  }
}

// kk-Cyrl-KZ → "1 234 567 ₸"
// Note: space grouping separator

export function formatKazakhDecimal(value: number, locale: KkLocale): string {
  return new Intl.NumberFormat(locale, {
    style: "decimal",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}
// kk → "1 234,56"  (space + comma)
```

---

## 4 — Plural Rules

```typescript
// src/i18n/kazakh-plural.ts

const KK_PLURAL = new Intl.PluralRules("kk");

/**
 * Kazakh plural: one (n === 1) / other (all remaining).
 * Noun forms do NOT change; only the numeral changes (Turkic agglutination).
 */
export function kkItemCount(count: number, word: string): string {
  // In Kazakh, the noun stays in the base form after numerals
  return `${count} ${word}`;
}

// The plural rule is straightforward, but possessive suffixes after numerals
// follow vowel harmony — handle via a lookup table, not Intl alone.
const HARMONY_SUFFIX: Record<string, string> = {
  // back vowel words → -дар/-лар
  кітап: `кітаптар`,
  // front vowel words → -дер/-лер
  үй: `үйлер`,
};

export function kkNounPlural(singular: string): string {
  return HARMONY_SUFFIX[singular] ?? `${singular}лар`;
}
```

---

## 5 — Workers Handler with Dual-Script Routing

```typescript
// src/handlers/kk-content.ts
import { resolveKazakhLocale, kkScriptName } from "../locale/kazakh";
import { formatTenge } from "../formatters/kazakh-currency";
import { formatKazakhDate } from "../formatters/kazakh-date";

export async function kkContentHandler(request: Request): Promise<Response> {
  const locale = resolveKazakhLocale(request.headers.get("Accept-Language"));
  const script = kkScriptName(locale);

  const data = {
    locale,
    script,
    formattedDate: formatKazakhDate(new Date(), locale, "long"),
    formattedPrice: formatTenge(89_900, locale),
  };

  return Response.json(data, {
    headers: {
      "Content-Language": locale,
      "Vary": "Accept-Language",
      "X-Script-Variant": script,
    },
  });
}
```

---

## 6 — KV Bundle Strategy for Latin Transition Period

```typescript
// src/translations/kk-loader.ts

/**
 * During the Latin rollout, only a subset of keys exist in kk-Latn-KZ.
 * Merge Cyrillic base with Latin overrides so Latin users see translated
 * content where available, and Cyrillic text elsewhere.
 */
export async function loadKazakhBundle(
  kv: KVNamespace,
  locale: "kk-Cyrl-KZ" | "kk-Latn-KZ"
): Promise<Record<string, string>> {
  const cyrl =
    (await kv.get<Record<string, string>>("i18n:kk-Cyrl-KZ", "json")) ?? {};

  if (locale === "kk-Cyrl-KZ") return cyrl;

  const latn =
    (await kv.get<Record<string, string>>("i18n:kk-Latn-KZ", "json")) ?? {};

  // Latin keys override Cyrillic; untranslated keys show Cyrillic text
  return { ...cyrl, ...latn };
}
```

---

## Anti-patterns

- **Using `ru-KZ` as a fallback for Kazakh** — Russian is a separate language; serving
  Russian to a Kazakh-preferring user is a localization failure.
- **Assuming `kk-Latn-KZ` is fully supported** by the Workers V8 CLDR snapshot — wrap
  every `Intl` call for `kk-Latn-KZ` in try/catch.
- **Hardcoding the `₸` symbol** — use `Intl.NumberFormat` with `currency: "KZT"`;
  some locales render it differently.
- **Ignoring vowel harmony** for suffix generation — Turkish/Uzbek rules do NOT
  apply to Kazakh; use Kazakh-specific suffix tables.

---

## Gotchas

- The CLDR `kk` tag resolves to `kk-Cyrl-KZ` via likely-subtags; `kk-Latn-KZ` does
  NOT maximize from bare `kk`.
- Kazakhstan's official Latin alphabet has gone through multiple revisions
  (2017, 2018, 2023); user-generated content may use any variant — avoid character-level
  sorting without a tested Collator.
- `Intl.Collator("kk")` sorts Cyrillic; there is currently no standard Collator for
  the new Latin orthography.
- The Tiyn (1/100 Tenge) is legal tender but rarely used; use `maximumFractionDigits: 0`
  for prices.

---

## Verification

```typescript
// test/kazakh.test.ts
import { expect, test } from "vitest";
import { resolveKazakhLocale } from "../src/locale/kazakh";
import { formatTenge } from "../src/formatters/kazakh-currency";

test("defaults to Cyrillic when no header", () => {
  expect(resolveKazakhLocale(null)).toBe("kk-Cyrl-KZ");
});

test("detects Latin preference", () => {
  expect(resolveKazakhLocale("kk-Latn;q=1.0,kk;q=0.9")).toBe("kk-Latn-KZ");
});

test("Tenge has no decimal places", () => {
  const result = formatTenge(50_000, "kk-Cyrl-KZ");
  expect(result).not.toMatch(/,\d\d/);
  expect(result).toContain("₸");
});
```

Run: `npx vitest run test/kazakh.test.ts`

---

## Related

- `uzbek-locale-workers-intl-central-asian.md` — parallel dual-script Turkic language
- `ukrainian-locale-workers-intl-cyrillic-collation.md` — Cyrillic collation patterns
- `cldr-likely-subtags-maximize-inference-boundary.md` — `kk` → `kk-Cyrl-KZ` inference
- `language-detection-workers-accept-language.md` — Accept-Language negotiation

---

## Sources

- CLDR 45 `kk` locale: https://github.com/unicode-org/cldr/tree/main/common/main
- Kazakhstan Latin alphabet decree 2023: https://akorda.kz
- ICU plural rules `kk`: https://unicode.org/cldr/charts/45/supplemental/language_plural_rules.html
- KZT ISO 4217: https://www.iso.org/iso-4217-currency-codes.html
- Cloudflare Workers Intl support: https://developers.cloudflare.com/workers/runtime-apis/web-standards/
