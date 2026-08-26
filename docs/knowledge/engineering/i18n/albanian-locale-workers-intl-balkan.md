# Albanian Locale in Cloudflare Workers — Balkan i18n

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You operate across Albania (`AL`) and Kosovo (`XK`) and need to render dates, currencies
(Lek `ALL` vs Euro `EUR` in Kosovo), and user-facing strings in Albanian (`sq`). The
language has two mutually intelligible main dialects — Gheg (north, Kosovo) and Tosk
(south, official standard) — but a single written standard. Workers without locale-aware
routing silently serve English number formats or use the wrong currency for Kosovo users.

---

## Context

- **BCP 47 tags**: `sq` (undetermined region), `sq-AL` (Albania), `sq-XK` (Kosovo), `sq-MK` (North Macedonia)
- **CLDR coverage**: `sq`, `sq-AL`, `sq-XK` — all present in CLDR 45
- **Currencies**: Albanian Lek (`ALL`) for `sq-AL`; Euro (`EUR`) for `sq-XK`
- **Calendar**: Gregorian; week starts Monday
- **Number format**: comma `,` for decimal, space ` ` for grouping in `sq`
- **Plural rules**: Albanian uses a complex two-form system (`one` / `other`) with
  specific ordinal forms

---

## 1 — Region-Aware Albanian Locale Resolution

```typescript
// src/locale/albanian.ts

export type SqLocale = "sq-AL" | "sq-XK" | "sq-MK" | "sq";
export type SqCurrency = "ALL" | "EUR";

const SQ_REGION_MAP: Record<string, SqLocale> = {
  AL: "sq-AL",
  XK: "sq-XK",
  MK: "sq-MK",
};

/**
 * Resolves Albanian locale from Accept-Language header.
 * Uses Cloudflare's cf.country geo-hint as a secondary signal.
 */
export function resolveAlbanianLocale(
  acceptLanguage: string | null,
  cfCountry?: string
): SqLocale {
  if (acceptLanguage) {
    const tags = acceptLanguage.split(",").map((s) => s.split(";")[0].trim());
    for (const tag of tags) {
      const lc = tag.toLowerCase();
      if (lc === "sq-xk" || lc === "sq_xk") return "sq-XK";
      if (lc === "sq-mk" || lc === "sq_mk") return "sq-MK";
      if (lc.startsWith("sq")) return "sq-AL";
    }
  }
  if (cfCountry) {
    return SQ_REGION_MAP[cfCountry.toUpperCase()] ?? "sq-AL";
  }
  return "sq-AL";
}

export function sqCurrency(locale: SqLocale): SqCurrency {
  return locale === "sq-XK" ? "EUR" : "ALL";
}
```

---

## 2 — Date Formatting for Albania and Kosovo

```typescript
// src/formatters/albanian-date.ts
import type { SqLocale } from "../locale/albanian";

const LONG_OPTS: Intl.DateTimeFormatOptions = {
  weekday: "long",
  year: "numeric",
  month: "long",
  day: "numeric",
};

const SHORT_OPTS: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
};

export function formatAlbanianDate(
  date: Date,
  locale: SqLocale,
  style: "long" | "short" = "long"
): string {
  return new Intl.DateTimeFormat(locale, style === "long" ? LONG_OPTS : SHORT_OPTS).format(
    date
  );
}

// sq-AL long  → "e diel, 23 gusht 2026"
// sq-AL short → "23.08.2026"
// sq-XK long  → "e diel, 23 gusht 2026"  (same format, different currency context)
```

---

## 3 — Currency Formatting: Lek vs Euro

```typescript
// src/formatters/albanian-currency.ts
import type { SqLocale } from "../locale/albanian";
import { sqCurrency } from "../locale/albanian";

export function formatAlbanianCurrency(
  amount: number,
  locale: SqLocale
): string {
  const currency = sqCurrency(locale);

  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    // ALL has 2 decimal places in ISO 4217 but 0 in practice; EUR uses 2
    minimumFractionDigits: currency === "ALL" ? 0 : 2,
    maximumFractionDigits: currency === "ALL" ? 0 : 2,
  }).format(amount);
}

// sq-AL  → "1 234 L"  or "1 234 Lekë"  (CLDR may vary)
// sq-XK  → "1 234,00 €"

export function formatAlbanianPercent(value: number, locale: SqLocale): string {
  return new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}
// sq → "12,5%"  (note comma decimal)
```

---

## 4 — Albanian Plural Rules

Albanian has a two-category plural (`one` / `other`) for cardinal numbers. Ordinals
are formed separately with suffixes, not handled by `Intl.PluralRules` ordinal mode
in all engines.

```typescript
// src/i18n/albanian-plural.ts

const SQ_CARDINAL = new Intl.PluralRules("sq");
const SQ_ORDINAL  = new Intl.PluralRules("sq", { type: "ordinal" });

const MESSAGES = {
  item: {
    one:   "1 artikull",
    other: "{n} artikuj",
  },
} as const;

export function sqItemCount(count: number): string {
  const rule = SQ_CARDINAL.select(count);
  const tpl = MESSAGES.item[rule as "one" | "other"] ?? MESSAGES.item.other;
  return tpl.replace("{n}", String(count));
}

// Albanian ordinal suffixes (cardinal 1 → "i parë", 2 → "i dytë", etc.)
// These are NOT derivable from Intl.PluralRules — use a lookup table:
const SQ_ORDINALS: Record<number, string> = {
  1: "i parë",   2: "i dytë",   3: "i tretë",
  4: "i katërt", 5: "i pestë",  6: "i gjashtë",
};

export function sqOrdinal(n: number): string {
  return SQ_ORDINALS[n] ?? `i ${n}-të`;
}
```

---

## 5 — Workers Handler: Kosovo vs Albania Routing

```typescript
// src/handlers/sq-handler.ts
import { resolveAlbanianLocale, sqCurrency } from "../locale/albanian";
import { formatAlbanianDate } from "../formatters/albanian-date";
import { formatAlbanianCurrency } from "../formatters/albanian-currency";

export async function sqHandler(request: Request): Promise<Response> {
  const cf = (request as any).cf as { country?: string } | undefined;
  const locale = resolveAlbanianLocale(
    request.headers.get("Accept-Language"),
    cf?.country
  );

  const payload = {
    locale,
    currency: sqCurrency(locale),
    today: formatAlbanianDate(new Date(), locale, "long"),
    examplePrice: formatAlbanianCurrency(4_999, locale),
  };

  return Response.json(payload, {
    headers: {
      "Content-Language": locale,
      "Vary": "Accept-Language",
    },
  });
}
```

---

## 6 — Definite Article Suffixation (Post-positive)

Albanian is unusual in that the definite article is a **suffix** on the noun, not a
separate word. Translation strings must account for this — never concatenate bare nouns
with appended UI text.

```typescript
// src/i18n/albanian-nouns.ts

/**
 * Albanian nouns have different definite forms depending on gender and ending.
 * This is a simplified lookup; a full implementation uses CLDR grammatical features.
 */
const DEFINITE_FORMS: Record<string, string> = {
  // Masculine: -i or -u suffix
  libër:    "libri",   // book
  kompjuter: "kompjuteri",
  // Feminine: -a or -ja suffix
  faqe:     "faqja",  // page
  datë:     "data",
};

export function sqDefinite(noun: string): string {
  return DEFINITE_FORMS[noun] ?? `${noun}-i`; // fallback masculine
}

// ANTI-PATTERN: `"Shikoni " + noun` — wrong form
// CORRECT:       `"Shikoni " + sqDefinite(noun)`
```

---

## Anti-patterns

- **Using `sq` without a region tag** when currency matters — bare `sq` gives no
  guidance on whether to use ALL or EUR; always derive currency from the region.
- **Copying Serbian or Greek plural rules** — Albanian has its own CLDR plural category
  that differs from neighbouring Balkan languages.
- **Treating Gheg and Tosk as different locales** — BCP 47 has no dialect subtag for
  them; use a single `sq` tag and handle dialectal vocabulary at the content layer.
- **Appending translated strings naively** — Albanian post-positive articles require
  that noun forms are looked up, not concatenated.

---

## Gotchas

- Kosovo's ISO 3166-1 alpha-2 code is `XK` — it is a user-assigned (non-standard) code.
  Some libraries reject it; test your geolocation and locale libraries explicitly.
- Cloudflare's `request.cf.country` will return `"XK"` for Kosovo — this works
  correctly with `resolveAlbanianLocale`.
- `Intl.NumberFormat("sq-XK")` in Workers V8 may fall back to `sq`; verify the
  currency symbol renders correctly in your target runtime.
- Albanian month names: `janar, shkurt, mars, prill, maj, qershor, korrik, gusht,
  shtator, tetor, nëntor, dhjetor` — not abbreviated in the same pattern as English.

---

## Verification

```typescript
// test/albanian.test.ts
import { expect, test } from "vitest";
import { resolveAlbanianLocale, sqCurrency } from "../src/locale/albanian";
import { formatAlbanianCurrency } from "../src/formatters/albanian-currency";

test("Kosovo resolves to sq-XK and EUR", () => {
  const locale = resolveAlbanianLocale(null, "XK");
  expect(locale).toBe("sq-XK");
  expect(sqCurrency(locale)).toBe("EUR");
});

test("Albania resolves to ALL", () => {
  const locale = resolveAlbanianLocale("sq-AL,sq;q=0.9");
  expect(sqCurrency(locale)).toBe("ALL");
});

test("ALL currency has no decimal places in output", () => {
  const result = formatAlbanianCurrency(1500, "sq-AL");
  expect(result).not.toMatch(/,\d\d$/);
});
```

Run: `npx vitest run test/albanian.test.ts`

---

## Related

- `serbian-locale-workers-intl-cyrillic-latin-dual.md` — neighbouring dual-script Balkan language
- `macedonian-locale-workers-intl-south-slavic.md` — also spoken by Albanians in North Macedonia (`sq-MK`)
- `locale-negotiation-accept-language.md` — Accept-Language parsing
- `cloudflare-workers-geolocation-locale-routing.md` — `cf.country` routing patterns

---

## Sources

- CLDR 45 `sq` locale: https://github.com/unicode-org/cldr/tree/main/common/main
- Albanian grammar (definite article): https://en.wikipedia.org/wiki/Albanian_grammar
- IANA language subtag `sq`: https://www.iana.org/assignments/language-subtag-registry
- Kosovo ISO 3166 user-assigned code: https://www.iso.org/obp/ui/#iso:pub:PUB500001
- Cloudflare geolocation: https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
