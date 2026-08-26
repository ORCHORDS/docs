# Romanian Locale: Intl Formatting, Plurals, and Workers Integration

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Cloudflare Worker serving Romanian (`ro`) users returns prices in `"25.5"` format
instead of `"25,5"` (Romanian decimal separator is comma), sorts city names incorrectly
(ș and ț treated as s and t), and generates wrong plural forms for item counts.
Additionally, `"ș"` (comma-below) and `"ş"` (cedilla-below) are visually similar but
technically distinct Unicode characters — mixing them causes search and matching bugs.

## Context

Romanian (`ro`, `ro-RO`) is a Romance language spoken by ~24 million people, primarily
in Romania and Moldova (`ro-MD`). Key locale properties:

| Property | `ro-RO` | `ro-MD` (Moldova) |
|----------|---------|-------------------|
| Currency | RON (lei) | MDL (leu moldovenesc) |
| Decimal separator | `,` | `,` |
| Thousands separator | `.` | `.` |
| Date format | `dd.MM.yyyy` | `dd.MM.yyyy` |
| Calendar | Gregorian | Gregorian |
| Time format | 24-hour | 24-hour |
| Plural forms | `one`, `few`, `other` | same |

**Plural rules for Romanian** are distinctive among Romance languages. Romanian uses the
`few` category (like Slavic languages) for counts 2–19:
- `one`: 1 (only exactly 1)
- `few`: 0, 2–19, 101–119, 201–219 … (ends in 01–19, or is 0)
- `other`: 20, 100, 120–199, 1000 …

**The ș/ţ issue**: Romanian letters with comma-below (ș U+015F, ț U+021B) are correct;
cedilla-below variants (ş U+015E, ţ U+0163) originate from older typewriter encodings
and remain common in legacy data. A search for "București" may miss results stored as
"Bucureşti" vs "BucureŞti". CLDR normalises both in NFKD but explicit
correction is best practice.

## Number and Currency Formatting

```typescript
// workers/src/romanian-number-format.ts

/**
 * Format currency for Romanian users.
 * RON uses comma decimal, dot thousands: "1.500,00 lei"
 */
export function formatRON(amount: number): string {
  return new Intl.NumberFormat("ro-RO", {
    style: "currency",
    currency: "RON",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

// formatRON(1500.5) → "1.500,50 lei"
// formatRON(0.99)   → "0,99 lei"

export function formatMDL(amount: number): string {
  return new Intl.NumberFormat("ro-MD", {
    style: "currency",
    currency: "MDL",
  }).format(amount);
}

/**
 * Parse a Romanian-format number string to a JavaScript float.
 * Reverses the decimal comma / thousands dot convention.
 */
export function parseRomanianNumber(input: string): number {
  // Remove thousands separator (.) and replace decimal comma with dot
  const normalised = input
    .replace(/\./g, "")  // remove dot thousands separators
    .replace(",", ".");  // replace comma decimal with dot
  return parseFloat(normalised);
}

// parseRomanianNumber("1.500,50") → 1500.5
// parseRomanianNumber("0,99")     → 0.99
```

## Date and Time Formatting

```typescript
// workers/src/romanian-date-format.ts

/**
 * Romanian date format: DD.MM.YYYY (24-hour clock)
 */
export function formatDateRO(date: Date): string {
  return new Intl.DateTimeFormat("ro-RO", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}
// formatDateRO(new Date("2026-08-23")) → "23.08.2026"

export function formatDateTimeLong(date: Date): string {
  return new Intl.DateTimeFormat("ro-RO", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}
// → "duminică, 23 august 2026, 14:30"

export function formatRelativeRO(
  value: number,
  unit: Intl.RelativeTimeFormatUnit,
): string {
  const rtf = new Intl.RelativeTimeFormat("ro", { numeric: "auto" });
  return rtf.format(value, unit);
}
// formatRelativeRO(-1, "day") → "ieri"
// formatRelativeRO(-3, "day") → "acum 3 zile"
// formatRelativeRO(1,  "day") → "mâine"
```

## Romanian Plural Rules in ICU MessageFormat

```typescript
// workers/src/romanian-messages.ts
// Romanian: one (=1), few (0, 2-19, ends in 01-19), other

const MESSAGES_RO: Record<string, string> = {
  // Products in cart
  cartItems: `{count, plural,
    one   {# produs}
    few   {# produse}
    other {# de produse}
  }`,

  // Days remaining
  daysLeft: `{count, plural,
    one   {mai este # zi}
    few   {mai sunt # zile}
    other {mai sunt # de zile}
  }`,

  // Comments
  commentCount: `{count, plural,
    one   {# comentariu}
    few   {# comentarii}
    other {# de comentarii}
  }`,
};

import MessageFormat from "@formatjs/intl-messageformat";

export function formatCart(count: number): string {
  const mf = new MessageFormat(MESSAGES_RO.cartItems, "ro");
  return mf.format({ count }) as string;
}

// formatCart(1)   → "1 produs"
// formatCart(5)   → "5 produse"     (few: 2-19)
// formatCart(15)  → "15 produse"    (few: ends in 15)
// formatCart(20)  → "20 de produse" (other)
// formatCart(101) → "101 produse"   (few: ends in 101 which is 01 → wait, 101 ends in 01-19?)
// Actually: 101 → CLDR says few for n % 100 in 1..19 → 101 % 100 = 1 → ONE category
// Let's clarify: 102 % 100 = 2 → FEW, 120 % 100 = 20 → OTHER
```

## Normalising ș/ț vs ş/ţ in Workers

```typescript
// workers/src/romanian-normalize.ts

/**
 * Correct legacy Romanian characters with cedilla-below to proper comma-below.
 *
 * ş (U+015E LATIN SMALL LETTER S WITH CEDILLA)     → ș (U+0219 ...WITH COMMA BELOW)
 * Ş (U+015E LATIN CAPITAL LETTER S WITH CEDILLA)   → Ș (U+0218 ...WITH COMMA BELOW)
 * ţ (U+0163 LATIN SMALL LETTER T WITH CEDILLA)     → ț (U+021B ...WITH COMMA BELOW)
 * Ţ (U+0162 LATIN CAPITAL LETTER T WITH CEDILLA)   → Ț (U+021A ...WITH COMMA BELOW)
 */
export function normaliseRomanianChars(text: string): string {
  return text
    .replace(/Ş/g, "Ș") // Ş → Ș
    .replace(/ş/g, "ș") // ş → ș
    .replace(/Ţ/g, "Ț") // Ţ → Ț
    .replace(/ţ/g, "ț") // ţ → ț
    .normalize("NFC");
}

/**
 * Apply normalisation before storing Romanian content in D1.
 */
export async function upsertRomanianContent(
  db: D1Database,
  id: string,
  content: string,
): Promise<void> {
  const cleaned = normaliseRomanianChars(content);
  await db
    .prepare(`INSERT INTO content (id, body) VALUES (?1, ?2)
              ON CONFLICT(id) DO UPDATE SET body = ?2`)
    .bind(id, cleaned)
    .run();
}
```

## Locale Routing for Romanian and Moldovan Users

```typescript
// workers/src/romanian-routing.ts

export function detectRomanianLocale(request: Request): string {
  const cf = (request as any).cf as IncomingRequestCfProperties | undefined;

  if (cf?.country === "RO") return "ro-RO";
  if (cf?.country === "MD") return "ro-MD"; // Moldova — Romanian is official language

  const acceptLang = request.headers.get("Accept-Language") ?? "";
  const tags = acceptLang.split(",").map((s) => s.split(";")[0].trim().toLowerCase());

  const roTag = tags.find((t) => t.startsWith("ro"));
  if (!roTag) return "";

  // ro-MD vs ro-RO preference
  if (roTag === "ro-md") return "ro-MD";
  return "ro-RO";
}

export async function handleRomanianRequest(
  request: Request,
  env: { KV: KVNamespace },
): Promise<Response | null> {
  const locale = detectRomanianLocale(request);
  if (!locale) return null;

  const translations = await env.KV.get<Record<string, string>>(
    `translations:${locale}`,
    "json",
  );
  if (!translations) return null;

  return new Response(JSON.stringify(translations), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Content-Language": locale,
    },
  });
}
```

## Anti-patterns

- **Using `.` as decimal separator in Romanian number inputs**: Romanian users type
  `1.500` to mean one thousand five hundred, not 1.5. Validate and parse with locale
  context.
- **Treating `ro` as a simple two-form plural language**: Romanian has three plural
  forms — omitting `few` causes wrong inflection for all counts 2–19 (the most common
  range for e-commerce item counts).
- **Storing cedilla-below variants without normalisation**: legacy Windows/ISO-8859-2
  data uses ş/ţ; mixing with comma-below ș/ț corrupts search indexes.
- **Using `"ro"` for Moldova**: `ro-MD` has MDL as currency and may carry localization
  differences in formal/governmental contexts — always resolve to the full subtag.

## Gotchas

- The CLDR few-plural rule for Romanian: `n % 100 in 2..19` — so 102 is `few`, but 101
  is `one`, and 120 is `other`. The boundary at 100–119 surprises many developers.
- `Intl.NumberFormat("ro-RO")` uses U+002E (FULL STOP) as the thousands separator and
  U+002C (COMMA) as decimal — do not strip all punctuation when parsing.
- Romanian `Intl.DateTimeFormat` month names are lowercase unless at the start of a
  sentence: `"23 august 2026"` is correct; `"23 August 2026"` is a capitalisation
  error in running prose.
- `Intl.Collator("ro")` sorts ș and ş as equivalent by default at `"base"` sensitivity
  but distinguishes them at `"variant"`. For search, `"base"` is appropriate.
- Moldova's official ISO 3166-1 code is `MD`, but Romanian is the language there (not
  Moldovan, which was a Soviet-era designation). Use `ro-MD` not `mo` (grandfathered
  tag, deprecated).

## Verification

```typescript
// tests/romanian.test.ts
import { describe, expect, it } from "vitest";
import { formatRON, parseRomanianNumber } from "../src/romanian-number-format";
import { formatCart } from "../src/romanian-messages";
import { normaliseRomanianChars } from "../src/romanian-normalize";

describe("Romanian number formatting", () => {
  it("uses comma decimal and dot thousands", () => {
    expect(formatRON(1500.5)).toMatch(/1\.500,50/);
  });

  it("parses Romanian number string correctly", () => {
    expect(parseRomanianNumber("1.500,50")).toBeCloseTo(1500.5);
  });
});

describe("Romanian plurals", () => {
  it("uses few for 5", () => {
    expect(formatCart(5)).toBe("5 produse");
  });

  it("uses one for 1", () => {
    expect(formatCart(1)).toBe("1 produs");
  });

  it("uses other for 20", () => {
    expect(formatCart(20)).toBe("20 de produse");
  });
});

describe("Romanian character normalisation", () => {
  it("converts cedilla-below to comma-below", () => {
    expect(normaliseRomanianChars("Bucureşti")).toBe("București");
  });
});
```

## Related

- `polish-locale-genitive-month-names-workers-intl.md` — Polish, another Slavic-adjacent
  language with genitive forms
- `ukrainian-locale-workers-intl-cyrillic-collation.md` — Cyrillic collation
- `Intl-PluralRules-2026.md` — Plural rules overview
- `icu-plural-rules-20-locales.md` — Plural rules across 20 locales
- `intl-collator-sensitivity-locale-aware-d1-sorting.md` — Collator sensitivity
- `localized-numeric-input-parsing.md` — Parsing locale-formatted user input

## Sources

- CLDR plural rules for `ro` — https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
- Unicode Romanian characters — U+0218–U+021B — https://www.unicode.org/charts/PDF/U0200.pdf
- MDN `Intl.NumberFormat` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- CLDR locale data for `ro` — https://github.com/unicode-org/cldr/tree/main/common/main
- BCP 47 subtag registry — https://www.iana.org/assignments/language-subtag-registry
- ICU User Guide: Plural Rules — https://unicode-org.github.io/icu/userguide/format_parse/messages/
