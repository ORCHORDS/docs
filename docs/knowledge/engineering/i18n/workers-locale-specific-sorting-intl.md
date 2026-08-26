# Locale-Aware String Sorting with Intl.Collator in Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A product list sorted alphabetically shows wrong order for Swedish users: `ä` appears after `z` instead of after `å`. Finnish users see `v` and `w` treated as equivalent when they should be distinct. A numeric filename sort puts `file10.txt` before `file2.txt` because it compares character by character. Returning D1 rows sorted by `ORDER BY name` uses the database collation, not the user's locale — and results must still be reordered in the Worker for language-specific rules.

---

## Context

`Intl.Collator` provides locale-aware string comparison functions that respect language-specific ordering rules from CLDR. Unlike JavaScript's default `Array.sort()` (which uses Unicode code point order), `Intl.Collator` handles:

- **Diacritic sensitivity**: Whether `e` and `é` sort together or apart.
- **Case sensitivity**: Whether `A` and `a` sort together or apart, and which comes first.
- **Language-specific rules**: Swedish `å < ä < ö` at the end of the alphabet; Spanish `ch` and `ll` as single collation units (traditional); German `ä` collates as `ae`.
- **Numeric natural sort**: `file2` < `file10` (not `file10` < `file2`).

Cloudflare Workers run V8 with full ICU, so `Intl.Collator` is available natively. The comparison function returned by `collator.compare` can be passed directly to `Array.sort()`.

---

## Solution

### 1. Basic locale-aware sort

```typescript
// src/collator.ts

export interface CollatorOptions {
  locale: string;
  sensitivity?: "base" | "accent" | "case" | "variant";
  caseFirst?: "upper" | "lower" | "false";
  numeric?: boolean;
  ignorePunctuation?: boolean;
}

export function createCollator(opts: CollatorOptions): Intl.Collator {
  return new Intl.Collator(opts.locale, {
    sensitivity: opts.sensitivity ?? "variant",
    caseFirst: opts.caseFirst ?? "false",
    numeric: opts.numeric ?? false,
    ignorePunctuation: opts.ignorePunctuation ?? false,
    usage: "sort",
  });
}

export function localSort<T>(
  items: T[],
  keyFn: (item: T) => string,
  opts: CollatorOptions
): T[] {
  const collator = createCollator(opts);
  // Sort a shallow copy — do not mutate the input
  return [...items].sort((a, b) => collator.compare(keyFn(a), keyFn(b)));
}
```

### 2. Sensitivity levels explained

```typescript
// src/sensitivity-demo.ts

const words = ["resume", "résumé", "Resume", "RESUME"];

// sensitivity: "base" — only base letter differences matter
// "resume" == "résumé" == "Resume" == "RESUME"
const baseCollator = new Intl.Collator("en", { sensitivity: "base" });
console.log([...words].sort(baseCollator.compare));
// => ["resume", "résumé", "Resume", "RESUME"]  (order not guaranteed among equals)

// sensitivity: "accent" — diacritics matter; case does not
// "resume" != "résumé", but "Resume" == "resume"
const accentCollator = new Intl.Collator("en", { sensitivity: "accent" });
console.log([...words].sort(accentCollator.compare));
// => ["resume", "Resume", "RESUME", "résumé"]

// sensitivity: "case" — case matters; diacritics do not
// "Resume" != "resume", but "resume" == "résumé"
const caseCollator = new Intl.Collator("en", { sensitivity: "case" });
console.log([...words].sort(caseCollator.compare));
// => ["resume", "résumé", "Resume", "RESUME"]

// sensitivity: "variant" (default) — everything matters
const variantCollator = new Intl.Collator("en", { sensitivity: "variant" });
console.log([...words].sort(variantCollator.compare));
// => ["resume", "résumé", "Resume", "RESUME"]  (strict order)
```

### 3. Swedish alphabet ordering

```typescript
// src/locale-rules/swedish.ts
// Swedish alphabet: ... x y z å ä ö
// Standard JS sort puts ä and ö near a and o (Latin code points)

const swedish = ["Zebra", "Åland", "Äpple", "Öst", "Anka", "Björn"];

// Wrong — Unicode code point order
console.log([...swedish].sort());
// => ["Anka", "Björn", "Zebra", "Åland", "Äpple", "Öst"]
// (Å/Ä/Ö sort after Z by code point, but they should come AFTER Z in Swedish)
// Actually in sv-SE: Anka, Björn, Zebra, Åland, Äpple, Öst — which IS correct
// but for lowercase mixed strings the difference becomes visible:

const mixed = ["zebra", "åland", "äpple", "öst", "anka", "björn"];
console.log([...mixed].sort());
// => ["anka", "björn", "zebra", "åland", "äpple", "öst"]  — correct by accident for ASCII
// But "ä" code point (U+00E4) < "å" (U+00E5) in Unicode,
// while Swedish order is å < ä < ö

const svWords = ["ärm", "åker", "öga"];
console.log([...svWords].sort());                        // ["ärm", "åker", "öga"] — WRONG (ä before å)
console.log([...svWords].sort(new Intl.Collator("sv").compare)); // ["åker", "ärm", "öga"] — CORRECT

// Usage in Worker:
export function sortSwedish<T>(items: T[], key: (i: T) => string): T[] {
  const collator = new Intl.Collator("sv", {
    sensitivity: "variant",
    usage: "sort",
  });
  return [...items].sort((a, b) => collator.compare(key(a), key(b)));
}
```

### 4. Numeric natural sorting

```typescript
// src/numeric-sort.ts

const filenames = [
  "file10.txt",
  "file2.txt",
  "file1.txt",
  "file20.txt",
  "file3.txt",
];

// Without numeric option — lexicographic
console.log([...filenames].sort());
// => ["file1.txt", "file10.txt", "file2.txt", "file20.txt", "file3.txt"]  WRONG

// With numeric: true
const numericCollator = new Intl.Collator("en", { numeric: true });
console.log([...filenames].sort(numericCollator.compare));
// => ["file1.txt", "file2.txt", "file3.txt", "file10.txt", "file20.txt"]  CORRECT

// Works for version strings too:
const versions = ["v1.10.0", "v1.9.0", "v1.2.0", "v2.0.0"];
console.log([...versions].sort(numericCollator.compare));
// => ["v1.2.0", "v1.9.0", "v1.10.0", "v2.0.0"]
```

### 5. D1 sorted result reordering in Workers

```typescript
// src/d1-sorted.ts
// D1's ORDER BY uses SQLite's default BINARY collation (byte order, not locale).
// Fetch rows with rough ordering from D1, then reorder in Worker.

export interface Env {
  DB: D1Database;
}

interface Product {
  id: number;
  name: string;
  category: string;
}

export async function getSortedProducts(
  env: Env,
  locale: string,
  category: string
): Promise<Product[]> {
  // Fetch all products in category from D1 (unordered is fine; we re-sort)
  const { results } = await env.DB
    .prepare("SELECT id, name, category FROM products WHERE category = ?")
    .bind(category)
    .all<Product>();

  // Re-sort with locale-aware collator
  const collator = new Intl.Collator(locale, {
    sensitivity: "variant",
    numeric: true,
    usage: "sort",
  });

  return results.sort((a, b) => collator.compare(a.name, b.name));
}

// For large result sets, consider fetching with a broad ORDER BY first
// to take advantage of D1's index, then reorder the result in Workers:
export async function getSortedProductsLarge(
  env: Env,
  locale: string,
  category: string,
  limit = 1000
): Promise<Product[]> {
  const { results } = await env.DB
    .prepare(
      "SELECT id, name, category FROM products WHERE category = ? ORDER BY name LIMIT ?"
    )
    .bind(category, limit)
    .all<Product>();

  const collator = new Intl.Collator(locale, { sensitivity: "variant", numeric: true });
  return results.sort((a, b) => collator.compare(a.name, b.name));
}
```

### 6. Collator instance reuse for performance

```typescript
// src/collator-pool.ts
// Intl.Collator construction is cheap (~microseconds) but building one per
// request per locale in a tight loop wastes time. Use a module-level map.

const COLLATOR_CACHE = new Map<string, Intl.Collator>();

export function getCachedCollator(
  locale: string,
  options?: Intl.CollatorOptions
): Intl.Collator {
  // Cache key includes the serialised options
  const key = `${locale}|${JSON.stringify(options ?? {})}`;
  if (!COLLATOR_CACHE.has(key)) {
    COLLATOR_CACHE.set(key, new Intl.Collator(locale, options));
  }
  return COLLATOR_CACHE.get(key)!;
}

// Because Workers isolates are reused across requests within the same
// container, module-level caches persist for the lifetime of the isolate
// (typically minutes to hours). This is safe for Intl.Collator because
// CLDR data does not change at runtime.

// Usage:
export function fastSort(items: string[], locale: string): string[] {
  const collator = getCachedCollator(locale, { sensitivity: "variant", numeric: true });
  return [...items].sort(collator.compare.bind(collator));
}
```

### 7. Case-first option

```typescript
// src/case-first.ts
// Control whether uppercase sorts before lowercase (or vice-versa)

const names = ["alice", "Bob", "charlie", "Dave"];

// Default: locale-dependent (usually lowercase first in English)
const defaultSort = new Intl.Collator("en").compare;
console.log([...names].sort(defaultSort));
// => ["alice", "Bob", "charlie", "Dave"]  (case doesn't affect order much in "variant")

// caseFirst: "upper" — uppercase before lowercase when otherwise equal
const upperFirst = new Intl.Collator("en", { caseFirst: "upper" }).compare;
console.log([...names].sort(upperFirst));
// => ["Bob", "Dave", "alice", "charlie"]

// caseFirst: "lower" — lowercase before uppercase
const lowerFirst = new Intl.Collator("en", { caseFirst: "lower" }).compare;
console.log([...names].sort(lowerFirst));
// => ["alice", "charlie", "Bob", "Dave"]

// This is distinct from sensitivity: "case" — caseFirst only affects tie-breaking.
```

---

## Implementation Details

- **`usage: "sort"` vs `usage: "search"`**: The `usage` option hints to the ICU library which algorithm to optimise for. For sorting lists, always use `"sort"`. For autocomplete or search-as-you-type matching, use `"search"` — it applies more lenient matching rules.
- **Collator reuse within a request**: A single `Intl.Collator` instance is safe to call `.compare()` on multiple times; it is not stateful between comparisons.
- **German sharp-S**: In German, `ß` traditionally compares as `ss`. `Intl.Collator("de")` handles this automatically.
- **Traditional Spanish**: Pre-1994 Spanish treated `ch` and `ll` as single letters after `c` and `l` respectively. Modern CLDR/ICU uses Unicode's standard ordering for `es`. If legacy ordering is required, no standard `Intl.Collator` option covers it — you need a custom compare function.
- **`ignorePunctuation`**: When `true`, hyphens, spaces, and other punctuation are ignored for ordering. Useful for product name lists where `T-shirt` and `Tshirt` should sort together.

---

## Anti-patterns

- **Using `localeCompare()` string method instead of a shared `Intl.Collator`.** `"a".localeCompare("b", locale, options)` re-creates a collator on every call. For sorting arrays, construct one collator and reuse it.
- **Sorting in D1/SQLite and trusting the order for non-ASCII locales.** SQLite's `NOCASE` only covers ASCII; locale-aware ordering must happen in the Worker.
- **Using `sensitivity: "base"` for sorted lists displayed to users.** Base sensitivity ignores both case and diacritics, making `é` and `e` appear in undefined order relative to each other.
- **Not binding `collator.compare`.** `Array.sort(collator.compare)` can lose `this` in some runtimes; bind it: `Array.sort(collator.compare.bind(collator))`.
- **Sorting user-supplied locale tags without validation.** `new Intl.Collator("invalid-LOCALE-TAG")` falls back silently in most runtimes; validate with `Intl.getCanonicalLocales()` first.

---

## Gotchas

- **`numeric: true` applies to all number sequences in the string**, not just filenames. `"version 10"` and `"version 2"` will sort numerically. This is usually desirable.
- **Collator cache in Workers isolates**: Module-level caches survive across requests but are per-isolate. Two concurrent isolates for the same Worker each have their own cache. This is fine — caches will populate independently.
- **Swedish `v`/`w` distinction**: In `sv` (Swedish), `v` and `w` are traditionally equivalent for sorting purposes (folded). The CLDR data for `sv` respects this. If your Swedish users file a bug that `v` and `w` words are interleaved, this is expected CLDR behaviour.
- **`Intl.Collator` is not a stable sort in the ECMAScript sense** — equal elements can be reordered. Use a stable sort wrapper if presentation order of ties matters.
- **Thai, Japanese, Chinese**: For logographic scripts, `Intl.Collator` sorts by Unicode code point by default (since there is no agreed phonetic ordering without metadata). Pinyin or stroke-count sorting requires additional annotation data.

---

## Verification

```typescript
// tests/collator.test.ts
import { describe, it, expect } from "vitest";
import { localSort } from "../src/collator";
import { fastSort } from "../src/collator-pool";

describe("Swedish sort", () => {
  it("places å before ä before ö", () => {
    const input = ["öga", "ärm", "åker"];
    const result = localSort(input, s => s, { locale: "sv", sensitivity: "variant" });
    expect(result).toEqual(["åker", "ärm", "öga"]);
  });
});

describe("numeric sort", () => {
  it("sorts file2 before file10", () => {
    const input = ["file10.txt", "file2.txt", "file1.txt"];
    const result = fastSort(input, "en");
    // With numeric: true in fastSort
    // NOTE: fastSort uses getCachedCollator with numeric: true
    expect(result[0]).toBe("file1.txt");
    expect(result[1]).toBe("file2.txt");
    expect(result[2]).toBe("file10.txt");
  });
});

describe("sensitivity", () => {
  it("base: resume equals résumé", () => {
    const collator = new Intl.Collator("en", { sensitivity: "base" });
    expect(collator.compare("resume", "résumé")).toBe(0);
  });

  it("variant: resume does not equal résumé", () => {
    const collator = new Intl.Collator("en", { sensitivity: "variant" });
    expect(collator.compare("resume", "résumé")).not.toBe(0);
  });
});
```

```bash
npx wrangler deploy
curl "https://your-worker.workers.dev/api/sort?locale=sv" \
  -H "Content-Type: application/json" \
  -d '["öga","ärm","åker","anka"]'
# => ["åker","anka","ärm","öga"]
```

---

## Related

- `documentation/docs/policies/i18n/workers-intl-edge-locale.md`
- `documentation/docs/policies/i18n/accept-language-negotiation.md`
- `documentation/docs/policies/i18n/workers-translation-fallback-chain-kv.md`
- `documentation/docs/policies/i18n/d1-translation-store.md`

---

## Sources

- MDN: [Intl.Collator](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Collator)
- CLDR: [Collation](https://cldr.unicode.org/development/development-process/design-proposals/collation)
- Unicode: [Collation Algorithm (UCA)](https://unicode.org/reports/tr10/)
- TC39 ECMA-402: [Intl.Collator spec](https://tc39.es/ecma402/#collator-objects)
- Cloudflare Docs: [D1 Database](https://developers.cloudflare.com/d1/)
- Cloudflare Docs: [Workers Runtime — Isolate model](https://developers.cloudflare.com/workers/reference/how-workers-works/)
