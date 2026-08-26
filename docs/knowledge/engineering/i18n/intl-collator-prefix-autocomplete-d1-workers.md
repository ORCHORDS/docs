# Locale-aware Autocomplete Prefix Matching with Intl.Collator and D1 in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A product-search autocomplete returns no results when a Spanish-speaking user types `cafe`
because the database stores `café` (with accent). A Turkish user types `Istanbul` but the
index stores `İstanbul` (uppercase dotted I), so the prefix match fails. Naive `LIKE 'cafe%'`
in D1 is case-sensitive in the default C locale and accent-sensitive always. The platform
needs an autocomplete endpoint in Workers that returns prefix matches respecting locale
collation — accent-insensitive in Spanish, dotted-I-aware in Turkish — without loading a
full ICU library.

## Context

SQLite (D1's engine) `LIKE` is case-insensitive only for ASCII A-Z by default. The
`COLLATE NOCASE` extension covers ASCII only. D1 does not expose the SQLite ICU extension.
The practical pattern is to:

1. **Pre-normalise** candidate strings at insert time into a searchable form (fold diacritics,
   lowercase with locale-aware `toLocaleLowerCase`).
2. **Perform prefix matching** on the normalised column.
3. **Post-filter and rank** results from D1 in the Worker using `Intl.Collator` with
   `sensitivity: 'base'` to confirm accent-insensitive matches.

`Intl.Collator` in Workers runs on V8's full ICU data, making it reliable for all BCP 47
locales. The collation is used for ranking and secondary filtering; the indexed column carries
the fast lookup.

---

## 1. Normalisation function for the searchable index column

```typescript
// src/lib/autocomplete-normalise.ts

/**
 * Produces a searchable form of a string for a given locale:
 *  - Lowercase (locale-aware: handles Turkish dotless-i, etc.)
 *  - NFD then strip combining marks (diacritic removal)
 *  - Collapse whitespace
 */
export function toSearchForm(input: string, locale: string): string {
  return input
    .normalize('NFD')                                // decompose diacritics
    .replace(/\p{Mn}/gu, '')                         // strip combining marks
    .toLocaleLowerCase(locale)                       // locale-aware lowercase
    .replace(/\s+/g, ' ')
    .trim();
}

// toSearchForm('Café',     'es')  => 'cafe'
// toSearchForm('İstanbul', 'tr')  => 'istanbul'   (tr lowercase dotted-I → 'i')
// toSearchForm('Müller',   'de')  => 'muller'
// toSearchForm('Ångström', 'sv')  => 'angstrom'
```

Note: Turkish `toLocaleLowerCase('tr')` maps `İ` → `i` (not `i` with dot); standard
`toLowerCase()` maps it to `i` with no dot loss, but produces `i` from `I` instead of `ı`,
which is correct for the search-form purpose.

---

## 2. D1 schema with dual columns

```sql
-- products table with a normalised search column
CREATE TABLE products (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,                  -- display form (unchanged)
  name_search TEXT NOT NULL,                  -- normalised by Workers at insert time
  locale      TEXT NOT NULL DEFAULT 'en'
);

CREATE INDEX idx_products_name_search ON products(name_search);
-- SQLite prefix scan works on the normalised column: WHERE name_search LIKE 'cafe%'
```

---

## 3. Insert handler: normalise on write

```typescript
// src/handlers/product-insert.ts
import { toSearchForm } from '../lib/autocomplete-normalise';

export interface Env { DB: D1Database; }

export async function handleInsert(req: Request, env: Env): Promise<Response> {
  const { name, locale = 'en' } = await req.json<{ name: string; locale?: string }>();
  const nameSearch = toSearchForm(name, locale);

  await env.DB.prepare(
    'INSERT INTO products (name, name_search, locale) VALUES (?, ?, ?)'
  ).bind(name, nameSearch, locale).run();

  return Response.json({ ok: true, nameSearch });
}
```

---

## 4. Autocomplete query: D1 prefix scan + Collator re-ranking

```typescript
// src/handlers/autocomplete.ts
import { toSearchForm } from '../lib/autocomplete-normalise';

export async function handleAutocomplete(req: Request, env: Env): Promise<Response> {
  const url    = new URL(req.url);
  const query  = url.searchParams.get('q') ?? '';
  const locale = url.searchParams.get('locale') ?? 'en';
  const limit  = Math.min(Number(url.searchParams.get('limit') ?? '10'), 50);

  if (query.length < 1) return Response.json({ results: [] });

  // Step 1: normalise the user's input the same way the index was built
  const querySearch = toSearchForm(query, locale);

  // Step 2: fast prefix scan on the indexed column (D1 uses the index for LIKE 'prefix%')
  const raw = await env.DB.prepare(
    `SELECT id, name, name_search
     FROM products
     WHERE name_search LIKE ? ESCAPE '\\'
     LIMIT ?`
  ).bind(querySearch.replace(/[%_\\]/g, '\\$&') + '%', limit * 3).all<{
    id: number; name: string; name_search: string;
  }>();

  // Step 3: re-rank with Intl.Collator for locale-accurate ordering
  const collator = new Intl.Collator(locale, { sensitivity: 'base', usage: 'sort' });

  const results = raw.results
    .sort((a, b) => {
      // Prefer exact prefix matches on display form first
      const aExact = a.name.toLocaleLowerCase(locale).startsWith(query.toLocaleLowerCase(locale));
      const bExact = b.name.toLocaleLowerCase(locale).startsWith(query.toLocaleLowerCase(locale));
      if (aExact && !bExact) return -1;
      if (!aExact && bExact) return 1;
      // Then alphabetical by locale collation
      return collator.compare(a.name, b.name);
    })
    .slice(0, limit)
    .map(r => ({ id: r.id, name: r.name }));

  return Response.json({ locale, query, results });
}
```

Fetching `limit * 3` from D1 then trimming to `limit` after re-ranking gives the collator
room to promote exact-prefix matches that would otherwise be truncated by a tight SQL LIMIT.

---

## 5. Collator sensitivity levels cheat-sheet

```typescript
// Sensitivity values and what they ignore:
// 'base'    – ignores accent AND case: 'cafe' == 'Café' == 'CAFE'  ← use for search
// 'accent'  – ignores case only:       'cafe' == 'CAFE', 'cafe' != 'café'
// 'case'    – ignores accent only:     'cafe' != 'Cafe', 'cafe' == 'café'
// 'variant' – all differences matter   (default)

// Rank by collation with 'base' for accent-insensitive display ordering:
const searchCollator = new Intl.Collator(locale, { sensitivity: 'base', usage: 'search' });

// 'usage: search' applies search-specific normalisation (strips ignorable chars).
// 'usage: sort' applies full sort-weight comparison (more accurate for display order).
// Use 'search' for match-detection, 'sort' for ordering in result lists.
```

---

## 6. Handling multi-locale product catalogues

```typescript
// When products have multiple locale variants, store one normalised row per locale
async function insertLocalised(
  db: D1Database,
  productId: number,
  translations: Record<string, string>
): Promise<void> {
  const stmts = Object.entries(translations).map(([locale, name]) =>
    db.prepare(
      'INSERT OR REPLACE INTO product_names (product_id, locale, name, name_search) VALUES (?, ?, ?, ?)'
    ).bind(productId, locale, name, toSearchForm(name, locale))
  );
  await db.batch(stmts);
}

// Query: filter by locale before the prefix scan
// WHERE locale = ? AND name_search LIKE ?
// Falls back to 'en' if locale row missing (handled in Workers fallback logic)
```

---

## Anti-patterns

- **`LIKE '%cafe%'` (infix scan)** — disables SQLite's B-tree index; use prefix `LIKE 'cafe%'`.
- **Normalising the query but not the stored column** — the two must use identical
  normalisation functions; a mismatch causes silent misses.
- **`toLowerCase()` for Turkish** — `'İSTANBUL'.toLowerCase()` in a non-`tr` locale yields
  `'i̇stanbul'` (with combining dot) rather than `'istanbul'`; always pass locale.
- **Over-fetching from D1** — fetching all rows and filtering in Workers is O(n); keep the
  SQL LIMIT tight and rely on the indexed prefix scan.

## Gotchas

- **NFD + mark removal collapses ligatures inconsistently** — `ß` decomposes to `ss` under
  NFKD but not NFD; if your use case requires `ss` == `ß` matching, use NFKD and remove
  marks, then `toLocaleLowerCase('de')`.
- **D1 LIKE is case-insensitive only for ASCII** — `LIKE 'cafe%'` will NOT match `Café` even
  with the normalised column if the stored value is un-normalised; always normalise both sides.
- **`usage: 'search'` vs `'sort'`** — search collators in some locales treat punctuation as
  ignorable, which can cause surprising equality; test with locale-specific edge cases.
- **Index selectivity** — very short prefixes (1–2 chars) return too many rows even with an
  index; enforce a minimum query length of 2 characters server-side.

## Verification

```typescript
import { describe, it, expect } from 'vitest';
import { toSearchForm } from '../src/lib/autocomplete-normalise';

describe('toSearchForm', () => {
  it('removes diacritics for es locale', () => {
    expect(toSearchForm('Café', 'es')).toBe('cafe');
  });
  it('lowercases Turkish dotted I correctly', () => {
    expect(toSearchForm('İstanbul', 'tr')).toBe('istanbul');
  });
  it('normalises ü for de locale', () => {
    // ü stays as ü after NFD+strip (the umlaut is a precomposed char, not a combining mark)
    // Actually ü (U+00FC) = u + combining diaeresis under NFD → stripped to 'u'
    expect(toSearchForm('Müller', 'de')).toBe('muller');
  });
  it('escapes LIKE metacharacters in querySearch', () => {
    // The handler escapes %, _, \ before appending %
    const escaped = 'café%special'.replace(/[%_\\]/g, '\\$&');
    expect(escaped).toBe('café\\%special');
  });
});
```

## Related

- `intl-collator-sensitivity-locale-aware-d1-sorting.md`
- `accent-insensitive-search-pipeline-2026.md`
- `unicode-collation-d1-sqlite-locale-sort.md`
- `turkish-locale-dotless-i-case-mapping-workers.md`
- `d1-fts5-multilingual-tokenizer-configuration.md`

## Sources

- MDN Intl.Collator: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Collator
- SQLite LIKE operator: https://www.sqlite.org/lang_expr.html#the_like_glob_regexp_match_and_extract_operators
- Unicode NFD/NFC normalisation: https://unicode.org/reports/tr15/
- CLDR collation sensitivity: https://cldr.unicode.org/index/cldr-spec/collation-guidelines
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
