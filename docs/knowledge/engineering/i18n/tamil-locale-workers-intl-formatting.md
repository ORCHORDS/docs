# Tamil Locale: Script, Numbers, and Intl Formatting in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

An example.com Worker serves users in Tamil Nadu (India, locale `ta-IN`) and Sri Lanka
(`ta-LK`). Product prices, dates, and list items must display in Tamil conventions:
optional Tamil numeral script (`tamldec` number system), the Indian numbering system
(lakh/crore groupings for `ta-IN`), and the correct calendar era. Naive
`Intl.NumberFormat("en")` output looks foreign and erodes user trust.

## Context

Tamil (`ta`) is a Dravidian language spoken by ~80 million people. Key locale properties:

| Property | `ta-IN` (India) | `ta-LK` (Sri Lanka) |
|----------|----------------|---------------------|
| Currency | INR (₹) | LKR (Rs) |
| Number grouping | Indian (2-2-3) | Western (3-3) |
| Default calendar | gregorian | gregorian |
| Decimal separator | `.` | `.` |
| Time cycle | 12-hour | 12-hour |
| Plural forms | `one`, `other` | `one`, `other` |
| Number system | `latn` default; `tamldec` available | `latn` default |

Tamil has its own numeral glyphs (`tamldec`): ௦ ௧ ௨ ௩ ௪ ௫ ௬ ௭ ௮ ௯. These are
available via the `nu` Unicode locale extension.

The **Indian number system** (also called South Asian grouping) groups the first three
digits from the right, then in pairs: 1,00,00,000 = one crore. `Intl.NumberFormat`
with `"ta-IN"` applies this grouping automatically.

## Currency and Number Formatting

```typescript
// workers/src/tamil-number-format.ts

/**
 * Format a price for Tamil-speaking users.
 * Supports optional Tamil numeral script via the `nu` extension.
 */
export function formatPrice(
  amount: number,
  locale: "ta-IN" | "ta-LK" | string,
  useTamilNumerals = false,
): string {
  const resolvedLocale = useTamilNumerals
    ? `${locale}-u-nu-tamldec`
    : locale;

  const currency = locale === "ta-LK" ? "LKR" : "INR";

  return new Intl.NumberFormat(resolvedLocale, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(amount);
}

// formatPrice(1500000, "ta-IN")               → "₹15,00,000.00"   (Indian grouping)
// formatPrice(1500000, "ta-IN", true)         → "₹௧௫,௦௦,௦௦௦.௦௦"  (Tamil numerals)
// formatPrice(1500000, "ta-LK")               → "Rs. 1,500,000.00" (western grouping)

export function formatCompact(amount: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    notation: "compact",
    compactDisplay: "short",
  }).format(amount);
}

// formatCompact(10000000, "ta-IN") → "1 கோடி"   (crore in Tamil)
// formatCompact(1000000,  "ta-IN") → "10 லட்சம்" (lakh)
```

## Date and Time Formatting

```typescript
// workers/src/tamil-date-format.ts

/**
 * Format a date for Tamil users. The Gregorian calendar is standard;
 * Tamil traditional calendar (Vikram Samvat variant) is not in CLDR.
 */
export function formatDate(
  date: Date,
  locale: string,
  options: Intl.DateTimeFormatOptions = {},
): string {
  const defaults: Intl.DateTimeFormatOptions = {
    year: "numeric",
    month: "long",
    day: "numeric",
  };
  return new Intl.DateTimeFormat(locale, { ...defaults, ...options }).format(date);
}

/**
 * Format a relative time string in Tamil.
 * Tamil RTF uses "other" plural for all counts > 1.
 */
export function formatRelativeTime(
  value: number,
  unit: Intl.RelativeTimeFormatUnit,
  locale: string,
): string {
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  return rtf.format(value, unit);
}

// formatDate(new Date("2026-01-14"), "ta-IN")
//   → "14 ஜனவரி 2026"

// formatRelativeTime(-3, "day", "ta")
//   → "3 நாட்களுக்கு முன்"   (3 days ago)

// formatRelativeTime(-1, "day", "ta")
//   → "நேற்று"               (yesterday — auto style)
```

## Detecting Tamil Users in a Worker

```typescript
// workers/src/locale-routing.ts
import { detectLocale } from "./locale-detect";

export async function handleRequest(request: Request): Promise<Response> {
  const locale = detectTamilLocale(request);
  const headers = new Headers({ "Content-Language": locale });

  // Route to locale-specific KV namespace key
  // e.g. translations:ta-IN:homepage
  return new Response(null, { headers });
}

function detectTamilLocale(request: Request): string {
  const cf = (request as any).cf as IncomingRequestCfProperties | undefined;

  // India → prefer ta-IN; Sri Lanka → ta-LK
  if (cf?.country === "IN") {
    const acceptLang = request.headers.get("Accept-Language") ?? "";
    if (acceptLang.toLowerCase().includes("ta")) return "ta-IN";
  }
  if (cf?.country === "LK") return "ta-LK";

  // Header-only fallback
  const acceptLang = request.headers.get("Accept-Language") ?? "";
  const tags = acceptLang.split(",").map((s) => s.split(";")[0].trim());
  const taTag = tags.find((t) => t.toLowerCase().startsWith("ta"));
  if (taTag) return taTag.includes("LK") ? "ta-LK" : "ta-IN";

  return "ta"; // generic Tamil fallback
}
```

## Storing Tamil Content in D1

Tamil uses Unicode block U+0B80–U+0BFF. SQLite stores all text as UTF-8, so no schema
change is needed, but collation and FTS tokenisation require attention.

```typescript
// workers/src/d1-tamil.ts

/**
 * Insert a Tamil product description into D1.
 * Use NFC normalisation before storage to ensure consistent codepoint sequences.
 */
export async function upsertProductTamil(
  db: D1Database,
  id: string,
  nameTa: string,
  descriptionTa: string,
): Promise<void> {
  // Tamil combining characters (e.g. ் pulli) can appear in different NFC forms
  const normName = nameTa.normalize("NFC");
  const normDesc = descriptionTa.normalize("NFC");

  await db
    .prepare(
      `INSERT INTO products (id, name_ta, description_ta)
       VALUES (?1, ?2, ?3)
       ON CONFLICT(id) DO UPDATE
         SET name_ta = ?2, description_ta = ?3`,
    )
    .bind(id, normName, normDesc)
    .run();
}

/**
 * Full-text search over Tamil descriptions using FTS5 unicode61 tokeniser.
 * The unicode61 tokeniser handles Tamil grapheme clusters better than ascii.
 */
export async function searchTamilProducts(
  db: D1Database,
  query: string,
): Promise<{ id: string; name_ta: string }[]> {
  const { results } = await db
    .prepare(
      `SELECT p.id, p.name_ta
       FROM products p
       JOIN products_fts f ON p.id = f.rowid
       WHERE products_fts MATCH ?1
       ORDER BY rank`,
    )
    .bind(query.normalize("NFC"))
    .all<{ id: string; name_ta: string }>();
  return results;
}
```

D1 schema setup:
```sql
CREATE VIRTUAL TABLE products_fts USING fts5(
  name_ta,
  description_ta,
  content=products,
  tokenize='unicode61 remove_diacritics 0'
);
```

## ICU Plural Rules for Tamil

Tamil plural is simpler than many South Asian languages: only `one` (count = 1) and
`other`. No special dual, few, or many categories.

```typescript
// workers/src/tamil-messages.ts

const MESSAGES_TA: Record<string, string> = {
  cartItems:
    "{count, plural, one {# பொருள்} other {# பொருட்கள்}}",
  daysLeft:
    "{count, plural, one {# நாள் மட்டுமே உள்ளது} other {# நாட்கள் உள்ளன}}",
};

import MessageFormat from "@formatjs/intl-messageformat";

export function formatCartMessage(count: number): string {
  const mf = new MessageFormat(MESSAGES_TA.cartItems, "ta");
  return mf.format({ count }) as string;
}

// formatCartMessage(1)  → "1 பொருள்"
// formatCartMessage(5)  → "5 பொருட்கள்"
```

## Anti-patterns

- **Using `"en-IN"` for Indian Tamil users**: produces INR with Indian grouping but in
  English script — Tamil users still see Latin digits and English month names.
- **Hardcoding "lakhs" or "crores" as strings**: use `Intl.NumberFormat` compact
  notation; it handles the scaling and the Tamil word automatically.
- **Applying `tamldec` numerals everywhere**: some UI contexts (e.g. input fields,
  search boxes) work better with Latin digits; reserve Tamil numerals for display only.
- **Skipping NFC normalisation**: Tamil combining characters like the pulli (்) can
  occur as precomposed or decomposed codepoints; inconsistent storage causes false
  search misses.

## Gotchas

- `Intl.NumberFormat("ta-IN")` applies Indian grouping (2-2-3) but `Intl.NumberFormat("ta-LK")`
  uses western grouping (3-3). The two locales are not interchangeable.
- Compact notation in `"ta-IN"` labels 100,000 as "1 லட்சம்" (lakh) and 10,000,000 as
  "1 கோடி" (crore). These labels come from CLDR and may change across runtime CLDR
  versions.
- The Tamil calendar (திருவள்ளுவர் ஆண்டு) is not in the CLDR `ca` extension. Use
  Gregorian with Tamil locale for safe cross-platform rendering.
- Tamil script in right-to-left contexts (if mixed with Arabic/Hebrew) requires correct
  `dir` attributes on container elements; Tamil itself is LTR.
- `Intl.Segmenter("ta")` is available in Workers but Tamil grapheme clusters (vowel
  signs attached to consonant base) must be treated as single user-perceived characters.

## Verification

```typescript
// tests/tamil-format.test.ts
import { describe, expect, it } from "vitest";
import { formatPrice, formatCompact } from "../src/tamil-number-format";
import { formatDate, formatRelativeTime } from "../src/tamil-date-format";

describe("Tamil number formatting", () => {
  it("applies Indian grouping for ta-IN", () => {
    expect(formatPrice(1500000, "ta-IN")).toBe("₹15,00,000.00");
  });

  it("applies Tamil numeral script when requested", () => {
    const result = formatPrice(100, "ta-IN", true);
    // Should contain Tamil digit ௧ (U+0BE7)
    expect(result).toMatch(/[௧-௯]/);
  });

  it("compact notation uses lakh for 100000 in ta-IN", () => {
    expect(formatCompact(100000, "ta-IN")).toContain("லட்சம்");
  });
});

describe("Tamil date formatting", () => {
  it("renders month name in Tamil", () => {
    const d = new Date("2026-01-01T00:00:00Z");
    const result = formatDate(d, "ta-IN");
    expect(result).toMatch(/ஜனவரி/); // January in Tamil
  });
});
```

## Related

- `devanagari-hindi-locale-workers-intl-formatting.md` — Hindi/Devanagari formatting
- `punjabi-gurmukhi-locale-workers-intl-formatting.md` — Punjabi/Gurmukhi formatting
- `bengali-bangla-locale-intl-workers-formatting.md` — Bengali locale
- `indic-script-rendering.md` — Indic script rendering overview
- `number-system-locale-workers-d1.md` — Custom numeral systems via `nu` extension
- `compact-number-notation-locales-2026.md` — Compact notation across locales
- `d1-fts5-multilingual-tokenizer-configuration.md` — FTS5 tokeniser configuration

## Sources

- CLDR locale data for `ta` — https://github.com/unicode-org/cldr/tree/main/common/main
- CLDR plural rules for Tamil — https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
- Unicode Tamil block (U+0B80–U+0BFF) — https://www.unicode.org/charts/PDF/U0B80.pdf
- MDN `Intl.NumberFormat` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- Cloudflare Workers: `IncomingRequestCfProperties` — https://developers.cloudflare.com/workers/runtime-apis/request/
- ICU User Guide: Formatting Numbers — https://unicode-org.github.io/icu/userguide/format_parse/numbers/
