# Non-Latin Numeral Systems in Cloudflare Workers and D1 Storage

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Arabic-language pages on example project display ticket counts and prices using Eastern Arabic
numerals (٠١٢٣٤٥٦٧٨٩) in the UI but the underlying D1 queries use the wrong collation
when filtering by these displayed values. Hindi users expect Devanagari numerals
(०१२३४५६७८९) for displayed quantities but the `Intl.NumberFormat` call emits Latin
digits because the locale tag is missing the `-u-nu-` Unicode extension. Sorting
numeric strings stored as text in D1 fails for non-Latin digit sequences.

## Context

example project (example.com) is a Next.js static export on Cloudflare Pages backed by a
Cloudflare Workers API with D1 (SQLite at the edge) and R2. The platform supports
Arabic (`ar-SA`, `ar-EG`), Hindi (`hi-IN`), and Bengali (`bn-BD`) locales. Each of
these has a preferred numeral system that differs from the Latin `latn` system. The
Workers API must produce correctly localised number strings while D1 must store and
sort them correctly.

---

## Numeral Systems and Unicode Extensions

Unicode locale extensions use the `-u-nu-` subtag to specify the numbering system.
CLDR defines over 70 numbering systems; the table below covers those relevant to example project

| Locale tag          | System name  | Digits        | Example (1234) |
|---------------------|--------------|---------------|----------------|
| ar-SA               | arab         | ٠١٢٣٤٥٦٧٨٩   | ١٢٣٤           |
| ar-EG               | arab         | same as ar-SA | ١٢٣٤           |
| hi-IN               | deva         | ०१२३४५६७८९   | १२३४           |
| bn-BD               | beng         | ০১২৩৪৫৬৭৮৯   | ১২৩৪           |
| fa-IR               | arabext      | ۰۱۲۳۴۵۶۷۸۹   | ۱۲۳۴           |
| ur-PK               | arabext      | same as fa-IR | ۱۲۳۴           |
| en-US               | latn         | 0123456789    | 1,234          |
| zh-Hans-CN          | latn (default)| 0123456789  | 1,234          |

The locale tag alone does not always trigger the non-Latin numbering system.
`ar-SA` *defaults* to `arab` in most ICU builds, but `hi-IN` defaults to `latn`
unless the `-u-nu-deva` extension is appended.

```typescript
// Workers: always explicitly declare the numbering system
export function getNumberFormatter(
  locale: string,
  numberingSystem?: string
): Intl.NumberFormat {
  const tag = numberingSystem
    ? `${locale}-u-nu-${numberingSystem}`
    : locale;
  return new Intl.NumberFormat(tag, {
    useGrouping: true,
  });
}

// Usage
const hindiFormatter = getNumberFormatter("hi-IN", "deva");
hindiFormatter.format(1234); // "१,२३४"

const arabicFormatter = getNumberFormatter("ar-SA"); // arab is default
arabicFormatter.format(1234); // "١٬٢٣٤"
```

---

## Resolving the Numbering System from Locale

example project stores user locale preferences as BCP 47 tags in a KV namespace. The Worker
must derive the default numbering system from the locale without a lookup table for
every locale — use `Intl.NumberFormat().resolvedOptions()`.

```typescript
const LOCALE_NUMBERING_OVERRIDES: Record<string, string> = {
  "hi-IN": "deva",
  "bn-BD": "beng",
  "bn-IN": "beng",
  "mr-IN": "deva",  // Marathi — Devanagari by convention
  "ne-NP": "deva",  // Nepali
};

export function resolveNumberingSystem(locale: string): string {
  if (LOCALE_NUMBERING_OVERRIDES[locale]) {
    return LOCALE_NUMBERING_OVERRIDES[locale];
  }
  // Let ICU resolve the default
  const resolved = new Intl.NumberFormat(locale).resolvedOptions();
  return resolved.numberingSystem; // "arab", "latn", etc.
}
```

| Locale  | resolvedOptions().numberingSystem | Matches user expectation? |
|---------|-----------------------------------|---------------------------|
| ar-SA   | arab                              | Yes                        |
| hi-IN   | latn                              | No — override to deva      |
| bn-BD   | latn                              | No — override to beng      |
| fa-IR   | arabext                           | Yes                        |
| en-US   | latn                              | Yes                        |

---

## D1 Storage Strategy for Non-Latin Numbers

D1 is SQLite and stores numbers as `INTEGER` or `REAL` types regardless of display
locale. Never store the *formatted* numeral string as the canonical value.

```sql
-- Schema: always store as INTEGER
CREATE TABLE tickets (
  id        INTEGER PRIMARY KEY,
  quantity  INTEGER NOT NULL,       -- store as 1234, never "١٢٣٤"
  price     INTEGER NOT NULL,       -- store cents: 499900
  locale    TEXT    NOT NULL        -- "ar-SA", "hi-IN" etc.
);
```

```typescript
// Worker: format on read, parse to integer on write
export function parseLocalizedNumber(
  input: string,
  locale: string
): number {
  // Normalise non-Latin digits to ASCII before parseInt
  const ascii = input
    .replace(/[٠-٩]/g, d => String(d.codePointAt(0)! - 0x0660))  // arab
    .replace(/[۰-۹]/g, d => String(d.codePointAt(0)! - 0x06F0))  // arabext
    .replace(/[०-९]/g, d => String(d.codePointAt(0)! - 0x0966))  // deva
    .replace(/[০-৯]/g, d => String(d.codePointAt(0)! - 0x09E6))  // beng
    .replace(/[,،٬\s]/g, "");  // remove thousands separators
  const parsed = parseInt(ascii, 10);
  if (isNaN(parsed)) throw new RangeError(`Cannot parse: ${input}`);
  return parsed;
}
```

D1 text collation (`NOCASE`) does not understand non-Latin digit ordering. Always sort
by the integer column, not by the formatted string.

```typescript
// Correct: sort by integer column
const rows = await env.DB.prepare(
  "SELECT id, quantity FROM tickets ORDER BY quantity DESC LIMIT 10"
).all();

// Wrong: sort by formatted text
// SELECT id, formatted_qty FROM tickets ORDER BY formatted_qty DESC
// ← "٩" < "١٠" in UTF-8 byte order, yielding incorrect sort
```

---

## KV Caching Numbering System Metadata

The per-locale numbering system derivation call is cheap but becomes a hot path at
scale. Cache the derived system in KV with a long TTL.

```typescript
const NS_KV_TTL = 86400; // 1 day

export async function cachedNumberingSystem(
  locale: string,
  kv: KVNamespace
): Promise<string> {
  const key = `ns:${locale}`;
  const cached = await kv.get(key);
  if (cached) return cached;
  const ns = resolveNumberingSystem(locale);
  await kv.put(key, ns, { expirationTtl: NS_KV_TTL });
  return ns;
}
```

---

## Anti-patterns

- Storing user-facing numeral strings in D1 as canonical values — breaks filtering,
  sorting, and aggregation.
- Using `locale.includes("ar")` to detect Arabic numerals — Persian (`fa`) and Urdu
  (`ur`) also use extended Arabic digits but with a different code block (U+06F0–U+06F9
  vs U+0660–U+0669); the check misses Perso-Arabic digits.
- Appending `-u-nu-latn` to all locales to force Latin digits — removes the localisation
  feature users in affected regions expect and may violate accessibility requirements in
  some countries.
- Relying on `Number()` to parse non-Latin digit strings — `Number("١٢٣٤")` returns
  `NaN` in all JS environments.
- Displaying `Intl.NumberFormat` output directly to screen readers without testing —
  non-Latin digits read back as individual digit names in some screen readers.

---

## Gotchas

- `Intl.NumberFormat` with `style: "decimal"` and `ar-SA` locale groups thousands with
  an Arabic comma `٬` (U+066C), not U+002C — downstream systems that split on `,` will
  break.
- Cloudflare Workers ICU data may not include all CLDR numbering systems; test `bn-BD`
  with `beng` extension in the actual Workers runtime, not just in Node.
- D1 `LIKE` queries against columns that might contain non-Latin digits require explicit
  normalisation before the query — SQLite LIKE does not normalise Unicode.
- The `-u-nu-` extension is case-sensitive in some older ICU versions; always use
  lowercase (`deva`, not `Deva`).
- Font support: Devanagari and Bengali digits require a font that covers those code
  points; Cloudflare Pages must serve the appropriate font subset or digits render as
  tofu boxes on mobile.

---

## Verification

```typescript
// vitest
import { describe, it, expect } from "vitest";
import { getNumberFormatter, parseLocalizedNumber } from "../src/numbers";

describe("Devanagari numerals", () => {
  it("formats 1234 in Devanagari for hi-IN", () => {
    expect(getNumberFormatter("hi-IN", "deva").format(1234)).toBe("१,२३४");
  });
  it("parses Devanagari string back to integer", () => {
    expect(parseLocalizedNumber("१,२३४", "hi-IN")).toBe(1234);
  });
});

describe("Arabic-Indic numerals", () => {
  it("formats 1234 for ar-SA", () => {
    const result = getNumberFormatter("ar-SA").format(1234);
    expect(result).toMatch(/[١-٩]/); // contains Arabic-Indic digit
  });
  it("parses Arabic-Indic string", () => {
    expect(parseLocalizedNumber("١٬٢٣٤", "ar-SA")).toBe(1234);
  });
});
```

---

## Related

- `number-currency-formatting-2026.md`
- `locale-aware-number-currency-formatting.md`
- `intl-numberformat-explicit-rounding-policy.md`
- `database-collation-locale-indexing.md`
- `unicode-locale-extensions-calendar-numbering-and-time-zone.md`

---

## Sources

- CLDR Numbering Systems: https://cldr.unicode.org/translation/number-currency-formats/number-symbols
- Unicode Common Locale Data Repository — numbering system data: https://github.com/unicode-org/cldr/blob/main/common/supplemental/numberingSystems.xml
- MDN Intl.NumberFormat numberingSystem option: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat
- Cloudflare D1 — SQLite at the edge: https://developers.cloudflare.com/d1/
- Unicode Standard — Arabic numerals code charts: https://www.unicode.org/charts/PDF/U0600.pdf
