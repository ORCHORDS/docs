# Uzbek Locale in Cloudflare Workers — Central Asian i18n

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You serve Uzbekistan (`UZ`) users and need to format dates, numbers, and currency in
Uzbek (`uz`). The language has two active orthographies — Latin (`uz-Latn-UZ`, the
official script since 1993) and Cyrillic (`uz-Cyrl-UZ`, still in wide use) — and
`Intl` implementations handle them differently. Workers deployed without script-aware
locale negotiation produce either garbled output or silent fallbacks to English.

---

## Context

- **BCP 47 tags**: `uz` (undetermined script), `uz-Latn-UZ` (official), `uz-Cyrl-UZ` (legacy)
- **CLDR coverage**: `uz` is in CLDR; `uz-Cyrl` has partial data
- **Currency**: Uzbekistani Som (`UZS`), ISO 4217
- **Calendar**: Gregorian; week starts Monday per ISO 8601 / CLDR
- **Decimal / group separators**: period `.` for decimal, space ` ` for grouping in `uz-Latn-UZ`
- **V8 (Node 18+) and SpiderMonkey**: both carry `uz` CLDR data; Cloudflare Workers V8 version ≥ 10.x supports `uz-Latn-UZ`

---

## 1 — Detecting and Negotiating the Uzbek Script Subtag

```typescript
// src/locale/uzbek.ts
import { Negotiator } from "@negotiator/accept-language"; // or manual parse

const UZ_TAGS = ["uz-Latn-UZ", "uz-Cyrl-UZ", "uz-UZ", "uz"] as const;
type UzTag = (typeof UZ_TAGS)[number];

/**
 * Resolves the best Uzbek script variant from the Accept-Language header.
 * Falls back to uz-Latn-UZ (the official orthography) when no preference is stated.
 */
export function resolveUzbekLocale(acceptLanguage: string | null): UzTag {
  if (!acceptLanguage) return "uz-Latn-UZ";

  const preferred = acceptLanguage
    .split(",")
    .map((s) => s.split(";")[0].trim().toLowerCase());

  for (const tag of preferred) {
    if (tag.startsWith("uz-cyrl")) return "uz-Cyrl-UZ";
    if (tag.startsWith("uz-latn") || tag === "uz" || tag === "uz-uz") {
      return "uz-Latn-UZ";
    }
  }
  return "uz-Latn-UZ";
}
```

---

## 2 — Date Formatting in Uzbek Latin and Cyrillic

```typescript
// src/formatters/uzbek-date.ts

const LOCALE_DATE_OPTIONS: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "long",
  day: "numeric",
};

const LOCALE_DATETIME_OPTIONS: Intl.DateTimeFormatOptions = {
  ...LOCALE_DATE_OPTIONS,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
};

export function formatUzbekDate(
  date: Date,
  locale: string,
  includeTime = false
): string {
  const options = includeTime ? LOCALE_DATETIME_OPTIONS : LOCALE_DATE_OPTIONS;
  try {
    return new Intl.DateTimeFormat(locale, options).format(date);
  } catch {
    // V8 may not have uz-Cyrl data; fall back to uz-Latn-UZ
    return new Intl.DateTimeFormat("uz-Latn-UZ", options).format(date);
  }
}

// Example outputs (Workers V8):
// uz-Latn-UZ → "23-avgust, 2026-yil"
// uz-Cyrl-UZ → "23 август 2026 й." (if supported, else falls back)
```

---

## 3 — Number and Currency Formatting

```typescript
// src/formatters/uzbek-number.ts

export function formatUzbekNumber(
  value: number,
  locale: string,
  style: "decimal" | "currency" | "percent" = "decimal"
): string {
  const opts: Intl.NumberFormatOptions =
    style === "currency"
      ? { style: "currency", currency: "UZS", maximumFractionDigits: 0 }
      : style === "percent"
        ? { style: "percent", maximumFractionDigits: 1 }
        : { style: "decimal" };

  try {
    return new Intl.NumberFormat(locale, opts).format(value);
  } catch {
    return new Intl.NumberFormat("uz-Latn-UZ", opts).format(value);
  }
}

// uz-Latn-UZ currency: "1 234 567 UZS"  (space grouping)
// uz-Latn-UZ decimal:  "1 234 567,89"   — note: CLDR uses comma for decimal in some builds
// Always verify against your Workers V8 CLDR snapshot
```

---

## 4 — Plural Rules for Uzbek

Uzbek uses a **two-form** plural system (`one` / `other`) identical in structure to
English, making it simpler than Arabic or Slavic languages.

```typescript
// src/i18n/uzbek-plural.ts

const UZ_PLURAL = new Intl.PluralRules("uz");

const UZ_MESSAGES: Record<Intl.LDMLPluralRule, string> = {
  one:   "{count} ta mahsulot",
  other: "{count} ta mahsulot", // Uzbek: same form for all counts
  zero:  "{count} ta mahsulot",
  two:   "{count} ta mahsulot",
  few:   "{count} ta mahsulot",
  many:  "{count} ta mahsulot",
};

export function uzbekProductCount(count: number): string {
  const rule = UZ_PLURAL.select(count);
  return UZ_MESSAGES[rule].replace("{count}", String(count));
}
// Note: "ta" is the Uzbek numeral classifier; it does NOT inflect.
```

---

## 5 — Cloudflare Workers Middleware: Uzbek Locale Routing

```typescript
// src/middleware/uz-locale.ts
import { resolveUzbekLocale } from "../locale/uzbek";

export async function uzbekLocaleMiddleware(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const acceptLang = request.headers.get("Accept-Language");
  const locale = resolveUzbekLocale(acceptLang);

  // Propagate via header so downstream handlers / KV key builders can read it
  const modifiedRequest = new Request(request, {
    headers: {
      ...Object.fromEntries(request.headers),
      "X-Resolved-Locale": locale,
      "X-Script": locale.includes("Cyrl") ? "Cyrillic" : "Latin",
    },
  });

  const response = await fetch(modifiedRequest);

  return new Response(response.body, {
    status: response.status,
    headers: {
      ...Object.fromEntries(response.headers),
      "Content-Language": locale,
      "Vary": "Accept-Language",
    },
  });
}
```

---

## 6 — KV Translation Store with Script-Aware Keys

```typescript
// src/translations/kv-loader.ts

export async function loadUzTranslations(
  kv: KVNamespace,
  locale: "uz-Latn-UZ" | "uz-Cyrl-UZ"
): Promise<Record<string, string>> {
  // Store separate JSON blobs per script variant
  const key = `translations:${locale}`;
  const cached = await kv.get<Record<string, string>>(key, "json");
  if (cached) return cached;

  // Fallback: load Latin, then overlay Cyrillic overrides
  const latin = await kv.get<Record<string, string>>(
    "translations:uz-Latn-UZ",
    "json"
  );
  const cyrl =
    locale === "uz-Cyrl-UZ"
      ? await kv.get<Record<string, string>>("translations:uz-Cyrl-UZ", "json")
      : null;

  return { ...(latin ?? {}), ...(cyrl ?? {}) };
}
```

---

## Anti-patterns

- **Using bare `uz` without a script subtag** when your KV keys or translation files
  distinguish Latin vs Cyrillic — bare `uz` defaults to Latin in V8 but is
  implementation-defined.
- **Hardcoding Cyrillic month names** in string literals — use `Intl.DateTimeFormat`
  and let CLDR supply them; the V8 snapshot in Workers may differ from Node.
- **Assuming UZS uses two decimal places** — the Som has no minor unit in practice;
  set `maximumFractionDigits: 0`.
- **Forgetting `Vary: Accept-Language`** on cached responses — CDN may serve Latin
  output to Cyrillic users.

---

## Gotchas

- `uz-Cyrl-UZ` CLDR data in V8 is **incomplete**; always wrap `Intl` calls in
  try/catch and fall back to `uz-Latn-UZ`.
- The Uzbek Latin orthography changed in 1995 (e.g., `sh` vs old `ş`); user-supplied
  content may use either; do not rely on character-level matching for search.
- `Intl.Collator("uz")` sort order may not match Uzbek alphabet order in all V8
  builds — test with the specific Workers runtime version.
- The Som currency code was redenominated in 1994; legacy content may use the old code.

---

## Verification

```typescript
// test/uzbek-locale.test.ts
import { expect, test } from "vitest";
import { formatUzbekDate, formatUzbekNumber } from "../src/formatters";
import { resolveUzbekLocale } from "../src/locale/uzbek";

test("resolves uz-Cyrl-UZ from header", () => {
  expect(resolveUzbekLocale("uz-Cyrl,uz;q=0.9")).toBe("uz-Cyrl-UZ");
});

test("formats UZS currency without decimals", () => {
  const result = formatUzbekNumber(1_234_567, "uz-Latn-UZ", "currency");
  expect(result).not.toMatch(/\.\d\d/); // no cents
});

test("date format falls back for uz-Cyrl when unavailable", () => {
  const d = new Date("2026-08-23");
  const result = formatUzbekDate(d, "uz-Cyrl-UZ");
  expect(typeof result).toBe("string");
  expect(result.length).toBeGreaterThan(5);
});
```

Run: `npx vitest run test/uzbek-locale.test.ts`

---

## Related

- `azerbaijani-locale-workers-intl-turkic.md` — sister Turkic language, similar plural rules
- `kazakh-locale-workers-intl-cyrillic-latin.md` — dual-script pattern, same region
- `cldr-likely-subtags-maximize-inference-boundary.md` — how `uz` maximizes to `uz-Latn-UZ`
- `language-detection-workers-accept-language.md` — Accept-Language parsing

---

## Sources

- CLDR 45 `uz` locale data: https://github.com/unicode-org/cldr/tree/main/common/main
- ICU4C `uz` plural rules: https://unicode.org/cldr/charts/45/supplemental/language_plural_rules.html
- BCP 47 script subtags: https://www.iana.org/assignments/language-subtag-registry
- Uzbek Latin alphabet (1995): https://en.wikipedia.org/wiki/Uzbek_alphabet
- Cloudflare Workers Runtime — V8 CLDR snapshot: https://developers.cloudflare.com/workers/runtime-apis/web-standards/
