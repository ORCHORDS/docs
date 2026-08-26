# Unicode Collation and String Sorting in D1 SQLite

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You are building a multilingual product catalogue, directory, or search interface on Cloudflare Workers + D1. Sorting breaks in subtle ways:

- A German product list sorts "Ärger" after "Zylinder" instead of at the start of the A section
- A French query `ORDER BY name` puts "école" after "zinc" because `é > z` in raw code-point order
- A Swedish `ORDER BY` puts Ö at position 15 (between N and P) rather than after Å and Ä at the end of the alphabet
- Case-insensitive search via `LIKE '%burger%'` matches "Burger" but not "BÜRGERBRÄU" (German Ü vs U)
- A search for "resume" should match "résumé" (accent-insensitive) but D1's `LIKE` is byte-exact

---

## Context

D1 is Cloudflare's managed SQLite service. SQLite's default collation is `BINARY`: string comparison is byte-by-byte, using UTF-8 code point order. This is correct for ASCII-only data but wrong for any language with diacritics, non-Latin scripts, or locale-specific sort orders.

SQLite supports three built-in collations:

| Collation | Behaviour | Use case |
|---|---|---|
| `BINARY` (default) | Byte-exact, code-point order | Technical keys, UUIDs |
| `NOCASE` | Case-fold ASCII only (`A`=`a`), not `Ä`=`ä` | English-only case-insensitive |
| `RTRIM` | Trims trailing spaces before comparing | Legacy compatibility |

SQLite allows registering **custom collations** via `sqlite3_create_collation()`. However, **D1 does not expose this API**. You cannot add an ICU-backed collation at the database level in D1.

This means all locale-aware sort logic must happen:
1. **At the application layer** (sort results in the Worker after fetching)
2. **Via a pre-computed sort key column** (store a normalised sort key at write time)
3. **Via collation-aware indexing tricks** (limited; see below)

---

## Strategy 1: Application-Layer Sort with Intl.Collator

Fetch the relevant rows from D1, then sort in the Worker using `Intl.Collator`. Practical when the result set is bounded (< 10 000 rows).

```typescript
// src/db/sorted-query.ts
import type { D1Database } from '@cloudflare/workers-types';

interface Product {
  id:   number;
  name: string;
}

/**
 * Fetch all products and sort them in the Worker using Intl.Collator.
 * The ORDER BY in SQL is intentionally omitted to avoid misleading binary sort.
 */
export async function getProductsSortedByName(
  db: D1Database,
  locale: string
): Promise<Product[]> {
  const { results } = await db
    .prepare('SELECT id, name FROM products')
    .all<Product>();

  const collator = new Intl.Collator(locale, {
    sensitivity: 'base',       // 'a' == 'á' == 'A' == 'Á'  (accent+case insensitive)
    // sensitivity: 'accent'   // 'a' == 'A' but 'a' ≠ 'á'  (accent sensitive, case insensitive)
    // sensitivity: 'variant'  // full discrimination
    caseFirst:   'false',      // lower before upper within a letter
    numeric:     true,         // "10" > "9" (natural sort)
    usage:       'sort',
  });

  return results.sort((a, b) => collator.compare(a.name, b.name));
}
```

### Locale-specific collation examples

```typescript
// Swedish: Å Ä Ö come AFTER Z
const sv = new Intl.Collator('sv', { sensitivity: 'base' });
['Österreich', 'Zebra', 'Apple'].sort(sv.compare);
// → ['Apple', 'Zebra', 'Österreich']

// German phonebook: Ä = AE, Ö = OE, Ü = UE (before standard sort)
const deDin = new Intl.Collator('de-u-co-phonebk', { sensitivity: 'base' });
['Müller', 'Mueller', 'Mahler'].sort(deDin.compare);
// → ['Mahler', 'Mueller', 'Müller']  (Mueller and Müller sort together)

// Arabic: sort by Arabic script order (Unicode logical order)
const ar = new Intl.Collator('ar', { sensitivity: 'base' });
['يوسف', 'أحمد', 'محمد'].sort(ar.compare);
// → ['أحمد', 'محمد', 'يوسف']

// Japanese: sort by reading (kana order), not Unicode point
const ja = new Intl.Collator('ja', { sensitivity: 'base' });
['東京', '大阪', 'あいうえお'].sort(ja.compare);
// Kana-aware ordering (CLDR-derived)

// Ukrainian: Ї, Є, І are in the Ukrainian alphabet; sort accordingly
const uk = new Intl.Collator('uk', { sensitivity: 'base' });
['Їжак', 'Іван', 'Єва'].sort(uk.compare);
// → ['Єва', 'Іван', 'Їжак']
```

---

## Strategy 2: Pre-Computed Sort Key Column

For large datasets where loading all rows is impractical, generate a **collation sort key** at write time and store it in an indexed column. Then use `ORDER BY sort_key_en` in D1.

### Generating sort keys with `Intl.Collator`

`Intl.Collator` does not expose sort keys directly in JavaScript (unlike ICU's `getSortKey()` in C++). Instead, use Unicode normalisation as a proxy:

```typescript
// src/utils/sort-key.ts

/**
 * Produce a locale-aware sort key string suitable for lexicographic
 * byte-order comparison (which is what SQLite BINARY does).
 *
 * Strategy:
 *  1. Decompose to NFD (canonical decomposition)
 *  2. Strip combining diacritical marks (Unicode category Mn)
 *  3. Fold to lowercase
 *  4. Normalise to NFC
 *
 * This approximates CLDR "base" sensitivity sort order.
 * It is NOT perfect for all locales (e.g. Swedish Å/Ä/Ö are still
 * misplaced) but is correct for most Western European languages.
 */
export function makeBaseSortKey(value: string): string {
  return value
    .normalize('NFD')
    .replace(/\p{Mn}/gu, '')   // remove combining marks
    .toLowerCase()
    .normalize('NFC');
}

/**
 * For Swedish/Finnish: special-case Å→A, Ä→A, Ö→O is WRONG for sorting.
 * Instead, append a tie-breaker so Å/Ä/Ö sort after Z.
 *
 * A simple approach: replace each Nordic letter with a surrogate
 * that sorts after Z in ASCII.
 */
export function makeSwedishSortKey(value: string): string {
  return value
    .toLowerCase()
    .replace(/å/g, 'zza')
    .replace(/ä/g, 'zzb')
    .replace(/ö/g, 'zzc');
}
```

### D1 schema with sort key columns

```sql
-- migrations/0003_add_sort_keys.sql

ALTER TABLE products ADD COLUMN sort_key_base TEXT GENERATED ALWAYS AS (
  -- SQLite does not support UDFs in generated columns.
  -- Compute sort_key_base from the application layer and store it explicitly.
  NULL
) STORED;
-- Note: Generated columns that call UDFs are NOT possible in D1.
-- Instead, manage sort_key_* as regular columns updated at write time.

ALTER TABLE products ADD COLUMN sort_key_base TEXT;
ALTER TABLE products ADD COLUMN sort_key_sv   TEXT;

CREATE INDEX idx_products_sort_base ON products (sort_key_base);
CREATE INDEX idx_products_sort_sv   ON products (sort_key_sv);
```

### Writing with sort keys

```typescript
// src/db/products-write.ts

export async function insertProduct(
  db: D1Database,
  name: string,
  price: number
): Promise<void> {
  const sortKeyBase = makeBaseSortKey(name);
  const sortKeySv   = makeSwedishSortKey(name);

  await db
    .prepare(`
      INSERT INTO products (name, price, sort_key_base, sort_key_sv)
      VALUES (?, ?, ?, ?)
    `)
    .bind(name, price, sortKeyBase, sortKeySv)
    .run();
}
```

### Reading with locale-aware ORDER BY

```typescript
// src/db/products-read.ts

export async function getProductsSorted(
  db: D1Database,
  locale: string
): Promise<Product[]> {
  // Choose the right pre-computed sort key column for the locale
  const sortColumn = getSortKeyColumn(locale);

  const { results } = await db
    .prepare(`SELECT id, name, price FROM products ORDER BY ${sortColumn} ASC`)
    .all<Product>();

  return results;
}

function getSortKeyColumn(locale: string): string {
  const base = locale.split('-')[0];
  const LOCALE_SORT_MAP: Record<string, string> = {
    sv: 'sort_key_sv',
    fi: 'sort_key_sv', // Finnish has same Å/Ä/Ö tail rule
    // Add more as needed
  };
  // Whitelist to prevent SQL injection
  const col = LOCALE_SORT_MAP[base] ?? 'sort_key_base';
  return col; // safe: only values from a known whitelist
}
```

---

## Strategy 3: Accent-Insensitive LIKE with NFD Normalisation

D1's `LIKE` operator is byte-exact. For accent-insensitive search, store a normalised `search_key` column and query against it:

```typescript
// src/db/search.ts

export async function searchProducts(
  db: D1Database,
  query: string
): Promise<Product[]> {
  // Normalise the query with the same transformation used at write time
  const normalizedQuery = makeBaseSortKey(query);

  const { results } = await db
    .prepare(`
      SELECT id, name, price
      FROM products
      WHERE search_key LIKE ?
      ORDER BY sort_key_base ASC
      LIMIT 50
    `)
    .bind(`%${normalizedQuery}%`)
    .all<Product>();

  return results;
}
```

Schema:

```sql
ALTER TABLE products ADD COLUMN search_key TEXT;
CREATE INDEX idx_products_search ON products (search_key);
```

Update at write time:

```typescript
const searchKey = makeBaseSortKey(name); // e.g. "ecole" from "école"
await db.prepare('UPDATE products SET search_key = ? WHERE id = ?').bind(searchKey, id).run();
```

---

## Strategy 4: Paginated Sort in the Worker

For medium-sized datasets (< 100 000 rows), use D1's keyset pagination and sort all rows in the Worker:

```typescript
// src/db/paginated-sort.ts

const PAGE_SIZE = 1000;

export async function* fetchAllProductsInPages(
  db: D1Database
): AsyncGenerator<Product[]> {
  let cursor = 0;
  while (true) {
    const { results } = await db
      .prepare('SELECT id, name FROM products WHERE id > ? ORDER BY id ASC LIMIT ?')
      .bind(cursor, PAGE_SIZE)
      .all<Product>();

    if (results.length === 0) break;
    yield results;
    cursor = results[results.length - 1].id;
  }
}

export async function getAllProductsSortedByLocale(
  db: D1Database,
  locale: string
): Promise<Product[]> {
  const collator = new Intl.Collator(locale, { sensitivity: 'base', numeric: true });
  const all: Product[] = [];

  for await (const page of fetchAllProductsInPages(db)) {
    all.push(...page);
  }

  return all.sort((a, b) => collator.compare(a.name, b.name));
}
```

---

## Practical Decision Matrix

| Dataset size | Locales | Recommended strategy |
|---|---|---|
| < 5 000 rows | Any | Application-layer sort (Strategy 1) |
| 5 000–100 000 rows | 1–3 | Pre-computed sort key per locale (Strategy 2) |
| 5 000–100 000 rows | Many | Base sort key + app-layer final sort |
| > 100 000 rows | Any | Sort key columns + DB pagination |
| Search / LIKE | Any | Normalised `search_key` column (Strategy 3) |

---

## Anti-Patterns

- **Using `ORDER BY name COLLATE NOCASE` for non-ASCII.** `NOCASE` in SQLite only case-folds ASCII letters (A–Z). It does not handle `ä`, `ü`, `ö`, `é`, or any non-Latin character. `'é' COLLATE NOCASE` still sorts after `'z'`.
- **Calling `toLowerCase()` and comparing.** JavaScript's `toLowerCase()` is locale-agnostic for Unicode: `'I'.toLowerCase()` is `'i'` but in Turkish, it should be `'ı'` (dotless i). Use `Intl.Collator` with the correct locale for case-insensitive comparison.
- **Storing sort keys generated in one locale for all locales.** A key generated for `de` is wrong for `sv`. Use one column per locale (or accept the imprecision of a base/generic key for most locales).
- **Regenerating sort keys on every read.** Sort keys are stable for a given input string and locale. Compute once at write time; re-compute only on migration.
- **SQL injection via column names.** If you select the sort column name based on the request locale, use an explicit allowlist (`if (locale === 'sv') col = 'sort_key_sv'`), never string interpolation of untrusted input.

---

## Gotchas

- **SQLite FTS5 (full-text search) in D1 does not support ICU tokenizers.** FTS5 with the default `unicode61` tokenizer strips diacritics during indexing, which gives approximate accent-insensitivity. Use FTS5 for full-text, pre-computed `search_key` for LIKE-style prefix search.
- **`Intl.Collator` `sensitivity: 'base'` treats `a` = `á` = `A` = `Á`.** This is too coarse for some applications (e.g. a French dictionary where `é` ≠ `e`). Use `sensitivity: 'accent'` to distinguish diacritics but ignore case.
- **Sort key stability across V8 versions.** `Intl.Collator` outputs depend on the ICU version bundled with V8. A Workers runtime upgrade may change sort order for edge cases (e.g. newly added CLDR tailoring rules). Pin ICU-sensitive operations to a collation test suite and run it on each Workers runtime bump.
- **D1 `TEXT` columns use UTF-8 storage.** Sort keys are strings; if your sort key generation produces non-UTF-8 bytes, D1 will reject the insert. Always output valid UTF-8 from `makeBaseSortKey()`.
- **The `numeric: true` Collator option** treats embedded digit sequences numerically (`"item10" > "item9"`). This is almost always desirable for product/version strings but may sort `"v1.10"` unexpectedly if the dot is not treated as a separator.

---

## Verification

```typescript
// test/collation.test.ts
import { describe, it, expect } from 'vitest';
import { makeBaseSortKey, makeSwedishSortKey } from '../src/utils/sort-key';

describe('makeBaseSortKey', () => {
  it('strips diacritics', () => {
    expect(makeBaseSortKey('école')).toBe('ecole');
    expect(makeBaseSortKey('Ärger')).toBe('arger');
  });

  it('lowercases', () => {
    expect(makeBaseSortKey('ZEBRA')).toBe('zebra');
  });
});

describe('makeSwedishSortKey', () => {
  it('sorts Ö after Z', () => {
    const words = ['Öl', 'Zebra', 'Apfel'].map(makeSwedishSortKey);
    const sorted = [...words].sort();
    expect(sorted).toEqual([
      makeSwedishSortKey('Apfel'),
      makeSwedishSortKey('Zebra'),
      makeSwedishSortKey('Öl'),
    ]);
  });
});

// Integration test: query D1 and verify order
import { env } from 'cloudflare:test';

describe('D1 sort', () => {
  it('returns products in Swedish alphabetical order', async () => {
    const products = await getProductsSorted(env.DB, 'sv');
    const names    = products.map((p) => p.name);
    const sorted   = [...names].sort(new Intl.Collator('sv').compare);
    expect(names).toEqual(sorted);
  });
});
```

---

## Related

- `database-collation-locale-indexing.md`
- `unicode-collation-2026.md`
- `unicode-normalization-nfc-nfd.md`
- `d1-schema-locale-preferences-content-translations-2026.md`
- `collation-sorting-unicode.md`
- `accent-insensitive-search-pipeline-2026.md`

---

## Sources

- [SQLite: Collating Sequences](https://www.sqlite.org/datatype3.html#collating_sequences)
- [Cloudflare D1 documentation](https://developers.cloudflare.com/d1/)
- [Intl.Collator MDN](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Collator)
- [Unicode CLDR: Collation](https://cldr.unicode.org/index/cldr-spec/collation-guidelines)
- [SQLite FTS5 unicode61 tokenizer](https://www.sqlite.org/fts5.html#unicode61_tokenizer)
- [ICU User Guide: Collation](https://unicode-org.github.io/icu/userguide/collation/)
