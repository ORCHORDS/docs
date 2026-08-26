# Intl.Collator Sensitivity Options and Locale-Aware D1 Sorting

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Cloudflare Worker returns a sorted product list from D1. SQLite's default `ORDER BY`
uses byte-order for non-ASCII text, which produces wrong results for accented characters
(é, ñ, ü) and locale-specific letter ordering (e.g. Swedish å, ä, ö come *after* z, not
near a). Post-fetch sorting in JavaScript with `Array.prototype.sort()` and `a < b`
comparisons has the same problem. The fix is `Intl.Collator` with the right `sensitivity`
and `locale` settings — but the options interact in non-obvious ways.

## Context

`Intl.Collator` wraps the Unicode Collation Algorithm (UCA) with locale tailoring from
CLDR. The critical option that most developers misunderstand is **`sensitivity`**:

| `sensitivity` value | Distinguishes | Ignores |
|--------------------|---------------|---------|
| `"base"` | Base letter differences (a ≠ b) | Accents, case |
| `"accent"` | Base + accent differences (a ≠ á) | Case |
| `"case"` | Base + case differences (a ≠ A) | Accents |
| `"variant"` | Base + accent + case + other (full) | Nothing |

The default is implementation-specific (often `"variant"`). For accent-insensitive search
use `"base"`; for case-insensitive search with accent-sensitivity use `"accent"`.

Additional options: `ignorePunctuation`, `numeric` (natural sort), `caseFirst`
(`"upper"` | `"lower"` | `"false"`), and the `kf`/`kn`/`kb` Unicode locale extensions.

Cloudflare Workers run V8, which has full ICU support — all `Intl.Collator` options work
correctly in the Workers runtime.

## Sensitivity Options in Practice

```typescript
// workers/src/collator-examples.ts

const words = ["résumé", "resume", "Resume", "RESUME", "résumé"];

// base: treat accents and case as equivalent
const base = new Intl.Collator("en", { sensitivity: "base" });
const baseGroups = words.filter((w, i, arr) =>
  arr.findIndex((x) => base.compare(w, x) === 0) === i,
);
// baseGroups → ["résumé"] — all four collapse to one

// accent: distinguish accented from unaccented, ignore case
const accent = new Intl.Collator("en", { sensitivity: "accent" });
// accent.compare("résumé", "resume") → non-zero (different)
// accent.compare("resume", "Resume") → 0    (same — case ignored)

// case: distinguish case but not accents
const caseOnly = new Intl.Collator("en", { sensitivity: "case" });
// caseOnly.compare("résumé", "resume") → 0    (accents ignored)
// caseOnly.compare("resume", "Resume") → non-zero (case differs)

// variant: distinguish everything (full UCA)
const variant = new Intl.Collator("en", { sensitivity: "variant" });
// variant.compare("résumé", "résumé") → 0
// variant.compare("résumé", "resume") → non-zero
// variant.compare("resume", "Resume") → non-zero
```

## Natural Sort and Numeric Collation

```typescript
// workers/src/natural-sort.ts

/**
 * Sort file names or version strings in natural (numeric) order.
 * Without numeric:true, "item10" sorts before "item9".
 */
export function naturalSort(items: string[], locale = "en"): string[] {
  const collator = new Intl.Collator(locale, {
    numeric: true,
    sensitivity: "base",
  });
  return [...items].sort((a, b) => collator.compare(a, b));
}

// naturalSort(["item2", "item10", "item1", "item20"])
//   → ["item1", "item2", "item10", "item20"]  (numeric order)
// Without numeric: ["item1", "item10", "item2", "item20"] (lexicographic)

/**
 * Sort with punctuation ignored (useful for titles with leading articles).
 */
export function sortIgnorePunctuation(items: string[], locale = "en"): string[] {
  const collator = new Intl.Collator(locale, {
    ignorePunctuation: true,
    sensitivity: "base",
  });
  return [...items].sort((a, b) => collator.compare(a, b));
}
```

## Locale-Specific Collation Tailoring

```typescript
// workers/src/locale-sort.ts

type LocaleSort = {
  locale: string;
  collation?: string; // Unicode co extension value
  caseFirst?: "upper" | "lower" | "false";
};

function makeCollator({ locale, collation, caseFirst }: LocaleSort): Intl.Collator {
  // Build locale with optional collation extension
  const tag = collation ? `${locale}-u-co-${collation}` : locale;
  return new Intl.Collator(tag, {
    sensitivity: "variant",
    caseFirst: caseFirst ?? "false",
  });
}

// Swedish: å, ä, ö sort AFTER z (not near a/o)
export const svCollator = makeCollator({ locale: "sv" });

// German phonebook (phone book) order: ä = ae, ö = oe, ü = ue
export const dePhoCollator = makeCollator({ locale: "de", collation: "phonebk" });

// German standard: ä near a (not phonebook expansion)
export const deStdCollator = makeCollator({ locale: "de", collation: "standard" });

// Spanish traditional: ch and ll are single letters (older ordering)
export const esTradCollator = makeCollator({ locale: "es", collation: "trad" });

// Usage
const germanWords = ["Müller", "Mueller", "Muller"];
console.log(germanWords.sort((a, b) => dePhoCollator.compare(a, b)));
// Phonebook: Mueller = Müller, Muller < them
```

## Applying Collation to D1 Results in a Worker

Since D1/SQLite does not support arbitrary Unicode collations at query time, fetch rows
from D1 unsorted (or with a pre-computed sort key) and sort in the Worker.

```typescript
// workers/src/sorted-list-handler.ts
import { Env } from "./types";

interface Product {
  id: string;
  name: string;
}

export async function getSortedProducts(
  db: D1Database,
  locale: string,
): Promise<Product[]> {
  // Fetch without ORDER BY — let the Worker sort
  const { results } = await db
    .prepare("SELECT id, name FROM products WHERE locale = ?1 LIMIT 500")
    .bind(locale)
    .all<Product>();

  const collator = new Intl.Collator(locale, {
    sensitivity: "base",
    numeric: false,
    ignorePunctuation: true,
  });

  return results.slice().sort((a, b) => collator.compare(a.name, b.name));
}

/**
 * Alternative: pre-compute a normalised sort key at insert time.
 * Store it in D1 so ORDER BY works correctly for the common single-locale case.
 */
export async function upsertWithSortKey(
  db: D1Database,
  product: Product,
  locale: string,
): Promise<void> {
  // A sort key is the collation "weight" approximated by NFD + lowercase
  // This is an approximation — use Worker-side sort for full accuracy.
  const sortKey = product.name
    .normalize("NFD")
    .toLowerCase()
    .replace(/[̀-ͯ]/g, ""); // strip combining marks for ASCII key

  await db
    .prepare(
      `INSERT INTO products (id, name, locale, sort_key)
       VALUES (?1, ?2, ?3, ?4)
       ON CONFLICT(id) DO UPDATE SET sort_key = ?4`,
    )
    .bind(product.id, product.name, locale, sortKey)
    .run();
}
```

## caseFirst Option

```typescript
// workers/src/case-first.ts

/**
 * Uppercase-first: A, B, C ... a, b, c
 * Lowercase-first: a, b, c ... A, B, C
 * Default ("false"): locale-dependent (usually lowercase-first)
 */
export function sortWithCaseFirst(
  items: string[],
  locale: string,
  caseFirst: "upper" | "lower" | "false" = "false",
): string[] {
  const collator = new Intl.Collator(locale, {
    sensitivity: "variant",
    caseFirst,
  });
  return [...items].sort((a, b) => collator.compare(a, b));
}

// sortWithCaseFirst(["banana", "Apple", "cherry", "apricot"], "en", "upper")
// → ["Apple", "apricot", "banana", "cherry"]  (uppercase A before lowercase a)

// sortWithCaseFirst(["banana", "Apple", "cherry", "apricot"], "en", "lower")
// → ["apricot", "Apple", "banana", "cherry"]  (lowercase a before uppercase A)
```

## Anti-patterns

- **`Array.sort()` without a comparator on non-ASCII strings**: uses UTF-16 code unit
  order — wrong for virtually every accented or non-Latin alphabet.
- **`localeCompare()` without options**: calls the system locale collator with
  unspecified sensitivity — produces inconsistent results across Workers regions.
- **`ORDER BY name COLLATE NOCASE` in D1**: SQLite NOCASE is ASCII-only; it does not
  fold accented characters.
- **Building a sort key with `.toLowerCase()` and stripping diacritics**: produces
  only an approximation — works for single-language ASCII-like scripts but breaks for
  Swedish (å ≠ a), German phonebook (ä = ae), or Thai.
- **Creating a new `Intl.Collator` on every comparison call**: constructing a collator
  is relatively expensive. Create it once and reuse across the sort.

## Gotchas

- `sensitivity: "base"` comparison returns `0` for `"a"` vs `"á"` — both compare equal
  at base level. Do not use this for deduplication; use it only for display sorting.
- `ignorePunctuation: true` also ignores spaces in some locales. Verify output before
  deploying to production.
- Swedish `"sv"` collation puts å, ä, ö after z — this differs from `"en"` which
  interleaves them near a and o. Always use a locale-specific collator.
- The `co` Unicode extension (e.g. `"de-u-co-phonebk"`) is supported in V8 but
  `Intl.supportedValuesOf("collation")` may not list locale-specific tailorings —
  test them with a known pair before shipping.
- `numeric: true` compares embedded number sequences; `ignorePunctuation` affects
  whether hyphens in strings like `"v1-2"` are treated as separators.
- Collation results are CLDR-version-dependent. Workers runtime upgrades may change
  sort order silently for edge cases.

## Verification

```typescript
// tests/collator.test.ts
import { describe, expect, it } from "vitest";
import { naturalSort, sortIgnorePunctuation } from "../src/natural-sort";
import { svCollator } from "../src/locale-sort";

describe("Intl.Collator", () => {
  it("natural sort orders numerically", () => {
    expect(naturalSort(["z10", "z2", "z1"])).toEqual(["z1", "z2", "z10"]);
  });

  it("Swedish sorts å after z", () => {
    // "z" should come before "å" in Swedish collation
    expect(svCollator.compare("z", "å")).toBeLessThan(0);
  });

  it("base sensitivity treats e and é as equal", () => {
    const col = new Intl.Collator("fr", { sensitivity: "base" });
    expect(col.compare("e", "é")).toBe(0);
  });

  it("accent sensitivity distinguishes e and é", () => {
    const col = new Intl.Collator("fr", { sensitivity: "accent" });
    expect(col.compare("e", "é")).not.toBe(0);
  });
});
```

## Related

- `collation-sorting-unicode.md` — Unicode Collation Algorithm overview
- `unicode-collation-d1-sqlite-locale-sort.md` — D1/SQLite collation strategies
- `accent-insensitive-search-pipeline-2026.md` — Accent-insensitive search
- `database-collation-locale-indexing.md` — Database-level collation and indexing
- `turkish-locale-dotless-i-case-mapping-workers.md` — Turkish case-sensitive collation
- `d1-fts5-multilingual-tokenizer-configuration.md` — FTS5 for full-text search

## Sources

- MDN: `Intl.Collator` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Collator
- Unicode Collation Algorithm (UCA) — https://www.unicode.org/reports/tr10/
- CLDR Collation — https://cldr.unicode.org/index/cldr-spec/collation-guidelines
- Unicode Locale Extensions (`co`, `kf`, `kn`, `kb`) — https://unicode.org/reports/tr35/#u_Extension
- V8 ICU integration — https://v8.dev/blog/i18n
- Cloudflare Workers runtime V8 — https://developers.cloudflare.com/workers/reference/security-model/
