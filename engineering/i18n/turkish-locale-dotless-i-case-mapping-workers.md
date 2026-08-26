# Turkish Locale: Dotless-I Case Mapping in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Cloudflare Worker serving Turkish (`tr`) users normalises user-submitted strings with
`toUpperCase()` or `toLowerCase()` before storing them in D1. Searches break because
`"istanbul".toUpperCase()` returns `"ISTANBUL"` in the default V8 locale instead of
`"İSTANBUL"` (capital dotted-I). Similarly, `"I".toLowerCase()` yields `"i"` globally
but must yield `"ı"` (dotless-i) in a Turkish context.

## Context

Turkish (and its close relative Azerbaijani, `az`) is the canonical example of a
**locale-sensitive case mapping** language. The Latin alphabet used in Turkey since 1928
has four i-variants:

| Character | Name | Lower | Upper |
|-----------|------|-------|-------|
| `i` | dotted lowercase i | `i` | `İ` (U+0130) |
| `ı` | dotless lowercase i | `ı` | `I` (U+0049) |

JavaScript's built-in `String.prototype.toUpperCase()` always maps `i → I`, which is
correct for English but wrong for Turkish. The locale-aware methods
`toLocaleLowerCase("tr")` and `toLocaleUpperCase("tr")` fix this. V8 (used in Cloudflare
Workers) implements these correctly, but they must be called explicitly with the locale
tag, because the *environment* locale inside a Worker is effectively `und` (undetermined).

BCP 47 tags: `tr` (Turkey), `tr-CY` (Turkish spoken in Cyprus), `az` (Azerbaijani —
shares the same i-pair behaviour).

## Locale-Sensitive Case Conversion in Workers

```typescript
// workers/src/case-utils.ts

/**
 * Perform locale-aware case conversion.
 * Always pass an explicit locale — Workers have no ambient locale.
 */
export function toUpper(str: string, locale: string): string {
  return str.toLocaleUpperCase(locale);
}

export function toLower(str: string, locale: string): string {
  return str.toLocaleLowerCase(locale);
}

// Demonstrate the difference
const word = "istanbul";
console.log(toUpper(word, "en")); // "ISTANBUL"   ← wrong for Turkish
console.log(toUpper(word, "tr")); // "İSTANBUL"   ← correct
console.log(toUpper(word, "az")); // "İSTANBUL"   ← Azerbaijani behaves the same

const capital = "I";
console.log(toLower(capital, "en")); // "i"   ← wrong for Turkish
console.log(toLower(capital, "tr")); // "ı"   ← correct dotless i
```

## Storing Normalised Text in D1

Case-folding before storage lets searches match regardless of capitalisation. For Turkish
content the fold must be locale-aware.

```typescript
// workers/src/d1-store.ts
import { Env } from "./types";

/**
 * Insert a Turkish product name into D1 with a locale-folded search column.
 * The fold_name column is used for case-insensitive lookups.
 */
export async function upsertProduct(
  db: D1Database,
  name: string,
  locale: string,
): Promise<void> {
  const foldedName = name.toLocaleLowerCase(locale);

  await db
    .prepare(
      `INSERT INTO products (name, fold_name, locale)
       VALUES (?1, ?2, ?3)
       ON CONFLICT(name) DO UPDATE SET fold_name = ?2`,
    )
    .bind(name, foldedName, locale)
    .run();
}

/**
 * Search products with locale-aware case folding applied to the query term.
 */
export async function searchProducts(
  db: D1Database,
  query: string,
  locale: string,
): Promise<{ name: string }[]> {
  const foldedQuery = query.toLocaleLowerCase(locale);

  const { results } = await db
    .prepare(
      `SELECT name FROM products
       WHERE fold_name LIKE ?1
       ORDER BY name`,
    )
    .bind(`%${foldedQuery}%`)
    .all<{ name: string }>();

  return results;
}
```

## Intl.Collator for Turkish Sorting

`Intl.Collator` with `locale: "tr"` orders the dotless-ı and dotted-i as distinct
letters in the Turkish alphabet — ı comes before i, and both come between h and j.

```typescript
// workers/src/sort-utils.ts

export function sortTurkish(items: string[]): string[] {
  const collator = new Intl.Collator("tr", {
    sensitivity: "variant", // distinguish ı vs i
    caseFirst: "lower",
  });
  return [...items].sort((a, b) => collator.compare(a, b));
}

// Expected order in Turkish alphabet:
// ... h, ı, i, j ...
const cities = ["İzmir", "Istanbul", "Ankara", "ısparta"];
console.log(sortTurkish(cities));
// → ["Ankara", "ısparta", "Istanbul", "İzmir"]
```

## Detecting Turkish from the Request

Workers receive the `Accept-Language` header and the `cf.country` property from the
Cloudflare request context. Both can signal Turkish.

```typescript
// workers/src/locale-detect.ts

export function detectLocale(request: Request): string {
  const cf = (request as any).cf as IncomingRequestCfProperties | undefined;

  // Country-based override: Turkey or Turkish-speaking Cyprus
  if (cf?.country === "TR") return "tr-TR";
  if (cf?.country === "CY") {
    // Cyprus has both Greek and Turkish speakers; fall through to header
  }

  const acceptLanguage = request.headers.get("Accept-Language") ?? "";
  const tags = acceptLanguage
    .split(",")
    .map((s) => s.split(";")[0].trim().toLowerCase());

  if (tags.some((t) => t.startsWith("tr"))) return "tr";
  if (tags.some((t) => t.startsWith("az"))) return "az";

  return "en"; // fallback
}
```

## ICU MessageFormat: No Plural Complexity for Turkish

Turkish has only **one plural form** (no special plural for 2–10 like Slavic languages).
ICU plural category for `tr` is `one` (when count = 1) and `other` (all else). This
makes Turkish templates simpler than Arabic or Polish.

```typescript
// workers/src/messages-tr.ts
// Using @formatjs/intl-messageformat (or compatible runtime)
import MessageFormat from "@formatjs/intl-messageformat";

const messages: Record<string, string> = {
  itemCount:
    "{count, plural, one {# ürün} other {# ürün}}", // same surface form
  // Turkish does not change the noun form; the number already conveys plurality
};

export function formatItemCount(count: number): string {
  const mf = new MessageFormat(messages.itemCount, "tr");
  return mf.format({ count }) as string;
}

// formatItemCount(1)  → "1 ürün"
// formatItemCount(42) → "42 ürün"
```

## Anti-patterns

- **`str.toUpperCase()` / `str.toLowerCase()` on Turkish user input**: always silent and
  wrong — produces Anglicised case mappings that break search and display.
- **Assuming `I` ↔ `i` is universal**: any algorithm (slug generation, username
  normalisation, search-term folding) that hard-codes this mapping will break for
  Turkish and Azerbaijani.
- **Storing both raw and folded in the same column**: keeps the surface form but makes
  searches locale-dependent at query time rather than insert time.
- **Using `UPPER()` / `LOWER()` in D1 SQL**: SQLite's `UPPER`/`LOWER` are ASCII-only;
  they do not apply locale-aware case mapping.

## Gotchas

- `"i".toLocaleUpperCase("tr")` returns `"İ"` (U+0130, Latin capital I with dot above),
  not `"I"` (U+0049). JSON keys processed this way can silently collide with other keys
  if compared without the same locale.
- Usernames that look identical visually may differ if one was entered with `i` and the
  other with `ı`. Enforce NFC normalisation *before* folding.
- The Cloudflare Workers runtime sets V8's default locale to something neutral; do not
  rely on `toUpperCase()` behaving as Turkish even when running tests inside Turkey.
- `Intl.Collator("tr")` is available in Workers but `Intl.Locale("tr").collations` may
  return an empty array — use `Intl.supportedValuesOf("collation")` to check runtime
  support rather than locale-level introspection.
- `az` (Azerbaijani) shares the same dotless-i behaviour. If your app serves Azerbaijan,
  apply the same logic under the `az` locale tag.

## Verification

```typescript
// tests/turkish-case.test.ts
import { describe, expect, it } from "vitest";
import { toUpper, toLower } from "../src/case-utils";

describe("Turkish case mapping", () => {
  it("uppercases dotted-i correctly", () => {
    expect(toUpper("istanbul", "tr")).toBe("İSTANBUL");
  });

  it("lowercases capital I to dotless-ı", () => {
    expect(toLower("ISTANBUL", "tr")).toBe("ıstanbul");
  });

  it("does not confuse dotless and dotted when round-tripping", () => {
    const original = "İstanbul";
    const folded = original.toLocaleLowerCase("tr"); // "istanbul" (dotted i)
    expect(folded[0]).toBe("i"); // U+0069 dotted
    expect(folded).not.toBe("ıstanbul"); // NOT dotless
  });
});
```

Run with `vitest run` or `wrangler dev --test`.

## Related

- `azerbaijani-locale-workers-intl-turkic.md` — Azerbaijani shares i-pair behaviour
- `unicode-default-case-folding-caseless-match.md` — Unicode default case-folding
- `unicode-locale-case-mapping-2026.md` — locale-specific case mapping overview
- `collation-sorting-unicode.md` — Unicode collation algorithm
- `intl-collator-sensitivity-locale-aware-d1-sorting.md` — Collator sensitivity options
- `d1-fts5-multilingual-tokenizer-configuration.md` — FTS5 tokeniser for D1

## Sources

- Unicode Technical Report #21: Case Mappings — https://unicode.org/reports/tr21/
- CLDR plural rules for `tr` — https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
- MDN: `String.prototype.toLocaleUpperCase()` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/String/toLocaleUpperCase
- Cloudflare Workers Runtime APIs: `IncomingRequestCfProperties` — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- BCP 47 language tag for Turkish — https://www.iana.org/assignments/language-subtag-registry
