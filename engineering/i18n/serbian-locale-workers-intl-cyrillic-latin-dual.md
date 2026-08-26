# Serbian Locale in Cloudflare Workers — Cyrillic/Latin Dual-Script i18n

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Serbian is officially written in both Cyrillic (`sr-Cyrl`) and Latin (`sr-Latn`) scripts
with neither being exclusive — Cyrillic is constitutionally primary but Latin dominates
digital contexts. Workers that do not distinguish the script subtag serve either script
to all users, break collation, and produce ICU plural mismatches for the notoriously
complex Serbian three-gender, two-number system.

---

## Context

- **BCP 47 tags**: `sr` (undetermined → defaults to Cyrillic in CLDR), `sr-Cyrl-RS`,
  `sr-Latn-RS`, `sr-Cyrl-BA` (Bosnia Cyrillic), `sr-Latn-ME` (Montenegro Latin)
- **CLDR coverage**: both `sr-Cyrl` and `sr-Latn` are well-covered in CLDR 45
- **Currency**: Serbian Dinar (`RSD`), symbol `din.` or `RSD`
- **Calendar**: Gregorian; week starts Monday
- **Number format**: comma `,` for decimal, period `.` for grouping in `sr`
- **Plural rules**: three categories — `one`, `few`, `other`; one of the more complex
  Slavic plural systems

---

## 1 — Script-Aware Locale Negotiation

```typescript
// src/locale/serbian.ts

export type SrScript = "Cyrl" | "Latn";
export type SrLocale =
  | "sr-Cyrl-RS" | "sr-Latn-RS"
  | "sr-Cyrl-BA" | "sr-Latn-BA"
  | "sr-Cyrl-ME" | "sr-Latn-ME"
  | "sr";

interface SrResolution {
  locale: SrLocale;
  script: SrScript;
}

/**
 * Resolves the Serbian script from Accept-Language.
 * In digital contexts, Latin is more commonly preferred by users,
 * but Cyrillic is the constitutional default — set your own product default.
 */
export function resolveSerbianLocale(
  acceptLanguage: string | null,
  productDefault: SrScript = "Cyrl"
): SrResolution {
  if (!acceptLanguage) {
    return {
      locale: productDefault === "Cyrl" ? "sr-Cyrl-RS" : "sr-Latn-RS",
      script: productDefault,
    };
  }

  const tags = acceptLanguage
    .split(",")
    .map((s) => s.split(";")[0].trim().toLowerCase());

  for (const tag of tags) {
    if (tag.includes("cyrl") || tag.includes("sr-cy")) {
      return { locale: "sr-Cyrl-RS", script: "Cyrl" };
    }
    if (tag.includes("latn") || tag.includes("sr-la")) {
      return { locale: "sr-Latn-RS", script: "Latn" };
    }
    if (tag.startsWith("sr")) {
      return {
        locale: productDefault === "Cyrl" ? "sr-Cyrl-RS" : "sr-Latn-RS",
        script: productDefault,
      };
    }
  }

  return {
    locale: productDefault === "Cyrl" ? "sr-Cyrl-RS" : "sr-Latn-RS",
    script: productDefault,
  };
}
```

---

## 2 — Date Formatting (Both Scripts)

```typescript
// src/formatters/serbian-date.ts
import type { SrLocale } from "../locale/serbian";

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

export function formatSerbianDate(
  date: Date,
  locale: SrLocale,
  style: "long" | "short" = "long"
): string {
  return new Intl.DateTimeFormat(
    locale,
    style === "long" ? LONG_OPTS : SHORT_OPTS
  ).format(date);
}

// sr-Cyrl-RS long  → "недеља, 23. август 2026."
// sr-Latn-RS long  → "nedelja, 23. avgust 2026."
// sr-Cyrl-RS short → "23.08.2026."  (trailing period — Serbian convention)
```

---

## 3 — Dinar Currency and Number Formatting

```typescript
// src/formatters/serbian-number.ts
import type { SrLocale } from "../locale/serbian";

export function formatDinar(amount: number, locale: SrLocale): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "RSD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amount);
}

// sr-Cyrl-RS → "1.234 RSD"   (period grouping, space before RSD)
// sr-Latn-RS → "1.234 RSD"

export function formatSerbianDecimal(value: number, locale: SrLocale): string {
  return new Intl.NumberFormat(locale, {
    style: "decimal",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}
// sr → "1.234,56"  — period grouping, comma decimal
```

---

## 4 — Serbian Plural Rules (one / few / other)

Serbian has one of the most complex plural systems in Europe. The rules are:
- `one`: n % 10 == 1 && n % 100 != 11
- `few`: n % 10 in 2..4 && n % 100 not in 12..14
- `other`: everything else

```typescript
// src/i18n/serbian-plural.ts

const SR_PLURAL = new Intl.PluralRules("sr");

const ITEM_FORMS_CYRL = {
  one:   "{n} производ",
  few:   "{n} производа",
  other: "{n} производа",
} as const;

const ITEM_FORMS_LATN = {
  one:   "{n} proizvod",
  few:   "{n} proizvoda",
  other: "{n} proizvoda",
} as const;

type SrPluralForms = typeof ITEM_FORMS_CYRL;

export function srItemCount(count: number, script: "Cyrl" | "Latn"): string {
  const forms: SrPluralForms =
    script === "Cyrl" ? ITEM_FORMS_CYRL : ITEM_FORMS_LATN;
  const rule = SR_PLURAL.select(count) as keyof SrPluralForms;
  const tpl = forms[rule] ?? forms.other;
  return tpl.replace("{n}", String(count));
}

// count=1   → "1 proizvod" / "1 производ"
// count=2   → "2 proizvoda" / "2 производа"
// count=5   → "5 proizvoda" / "5 производа"
// count=11  → "11 proizvoda" (NOT one — 11 is in the 'other' range)
// count=21  → "21 proizvod"  (21 % 10 == 1)
```

---

## 5 — Workers Middleware: Script Routing + KV Bundles

```typescript
// src/middleware/sr-middleware.ts
import { resolveSerbianLocale } from "../locale/serbian";

export async function srMiddleware(
  request: Request,
  env: Env
): Promise<Response> {
  const { locale, script } = resolveSerbianLocale(
    request.headers.get("Accept-Language"),
    "Latn" // digital-context default
  );

  // Cache key includes script to prevent cross-script cache poisoning
  const cacheKey = new Request(
    `${new URL(request.url).pathname}?script=${script}`,
    request
  );

  const cache = caches.default;
  let response = await cache.match(cacheKey);

  if (!response) {
    const bundle = await env.TRANSLATIONS.get(`sr:${locale}`, "json");
    response = Response.json(bundle ?? {}, {
      headers: {
        "Content-Language": locale,
        "Vary": "Accept-Language",
        "Cache-Control": "s-maxage=3600",
        "X-Script": script,
      },
    });
    env.ctx.waitUntil(cache.put(cacheKey, response.clone()));
  }

  return response;
}
```

---

## 6 — Collation: Cyrillic and Latin Sort Orders

```typescript
// src/utils/serbian-collation.ts

const SR_CYRL_COLLATOR = new Intl.Collator("sr-Cyrl-RS", {
  sensitivity: "variant",
  usage: "sort",
});

const SR_LATN_COLLATOR = new Intl.Collator("sr-Latn-RS", {
  sensitivity: "variant",
  usage: "sort",
});

export function sortSerbian(
  items: string[],
  script: "Cyrl" | "Latn"
): string[] {
  const collator = script === "Cyrl" ? SR_CYRL_COLLATOR : SR_LATN_COLLATOR;
  return [...items].sort((a, b) => collator.compare(a, b));
}

// Serbian Latin has digraphs: LJ, NJ, DŽ — sort AFTER their base letters
// e.g.: ... D < Dž < E ... L < Lj < M ... N < Nj < O
// Intl.Collator("sr-Latn") handles this correctly via CLDR tailoring.
// DO NOT use a JS default sort() for Serbian Latin — digraphs will be misordered.
```

---

## Anti-patterns

- **Using `sr-RS` without a script subtag** when you need to control the output script —
  `sr-RS` defaults to Cyrillic in CLDR but the fallback behaviour is implementation-defined
  in some engines.
- **Treating Serbian Latin as a simple ASCII variant** — it has digraph letters (Lj, Nj,
  Dž) that require CLDR collation tailoring.
- **Using `hr` (Croatian) as a "close enough" fallback** — Croatian and Serbian share
  much vocabulary but have distinct plural rules, date formats, and official terminology.
- **Forgetting the trailing period after Serbian dates** — `23. август 2026.` — the
  period is part of the ordinal suffix convention.

---

## Gotchas

- Serbian month names in Latin are **not capitalised**: `januar, februar, mart...`
- The plural rule for `21`, `31`, `41`... is `one` (because `n % 10 == 1 AND n % 100 != 11`);
  many developers hard-code only 1 as `one` — this is wrong for Serbian.
- `Intl.PluralRules("sr")` and `Intl.PluralRules("sr-Latn-RS")` return identical
  categories — the plural rules are the same regardless of script.
- The RSD grouping separator is a **period** `.`, not a space — reverse of what most
  Western Europeans expect.

---

## Verification

```typescript
// test/serbian.test.ts
import { expect, test } from "vitest";
import { resolveSerbianLocale } from "../src/locale/serbian";
import { srItemCount } from "../src/i18n/serbian-plural";

test("detects Cyrillic from Accept-Language", () => {
  const { script } = resolveSerbianLocale("sr-Cyrl,sr;q=0.9");
  expect(script).toBe("Cyrl");
});

test("21 uses 'one' plural form", () => {
  const result = srItemCount(21, "Latn");
  expect(result).toBe("21 proizvod");
});

test("11 uses 'other' plural form (not one)", () => {
  const result = srItemCount(11, "Latn");
  expect(result).toBe("11 proizvoda");
});

test("2 uses 'few' plural form", () => {
  const result = srItemCount(2, "Cyrl");
  expect(result).toContain("производа");
});
```

Run: `npx vitest run test/serbian.test.ts`

---

## Related

- `albanian-locale-workers-intl-balkan.md` — co-regional Balkan language
- `ukrainian-locale-workers-intl-cyrillic-collation.md` — Cyrillic collation patterns
- `pluralization-edge-cases-arabic-slavic.md` — Slavic plural edge cases
- `cldr-likely-subtags-maximize-inference-boundary.md` — `sr` → `sr-Cyrl-RS` inference

---

## Sources

- CLDR 45 `sr` and `sr-Latn` locale data: https://github.com/unicode-org/cldr/tree/main/common/main
- ICU plural rules `sr`: https://unicode.org/cldr/charts/45/supplemental/language_plural_rules.html
- Serbian alphabet collation tailoring: https://unicode.org/reports/tr10/
- BCP 47 `sr` subtag registry: https://www.iana.org/assignments/language-subtag-registry
- Cloudflare Workers Intl: https://developers.cloudflare.com/workers/runtime-apis/web-standards/
