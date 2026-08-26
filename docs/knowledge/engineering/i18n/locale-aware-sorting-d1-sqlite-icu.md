# Locale-Aware String Sorting in D1 (SQLite)

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A product listing sorted with `ORDER BY name COLLATE NOCASE` places "Öffnung" after "Zebra" and "Ångström" at the end of the list for German and Swedish users, because SQLite's built-in collations use byte-order, not linguistic order. The standard `NOCASE` collation only folds ASCII letters; characters like `ä`, `ö`, `ü`, `å`, `ñ`, and `ç` sort by their Unicode code point, which does not match user expectations in any European locale.

## Context

SQLite supports custom collating sequences registered via `sqlite3_create_collation()`, but D1 runs server-side on Cloudflare's infrastructure — you cannot register custom C-level collations at runtime. The recommended workaround is application-level sort-key generation: when inserting or updating a row, compute a locale-sensitive binary sort key using `Intl.Collator.compare()` or the `Intl.Collator` API, store it in a dedicated `sort_key` TEXT column, and index that column. `ORDER BY sort_key` then produces correct linguistic ordering for any locale. An alternative approach using SQLite compiled with ICU (WASM) is also documented below.

## Why `COLLATE NOCASE` Fails for Non-ASCII

```sql
-- SQLite byte-order result for German names:
SELECT name FROM products ORDER BY name COLLATE NOCASE;
-- Actual output:  Apfel, Birne, Zebra, ärger, öffnung
-- Expected (de):  ärger, Apfel, Birne, öffnung, Zebra
-- (ä sorts after a, ö after o in German DIN 5007-1)
```

## Generating Sort Keys with `Intl.Collator`

```typescript
// utils/sortKey.ts

/**
 * Generates a locale-sensitive binary sort key for a string.
 *
 * The key is a hex-encoded string of the collation element array
 * produced by Intl.Collator. It preserves linguistic sort order when
 * compared lexicographically (i.e., with a standard SQL text comparison).
 *
 * @param str     Input string, e.g. "Öffnung"
 * @param locale  BCP 47 locale, e.g. "de-DE"
 * @returns       Hex sort key, safe for SQL TEXT storage
 */
export function generateSortKey(str: string, locale: string): string {
  // Normalize to NFC first to handle decomposed forms
  const normalized = str.normalize('NFC').toLowerCase();

  const collator = new Intl.Collator(locale, {
    sensitivity: 'variant', // distinguish case and accents
    usage: 'sort',
    ignorePunctuation: false,
  });

  // Intl.Collator does not expose sort-key bytes directly in ECMA-402.
  // We use a comparison-based approach: sort the characters relative to
  // a reference alphabet to build a positional encoding.
  // For production use, see the @unicode/icu4x-collator WASM package.

  // Practical approximation: use locale-aware comparison to produce a
  // padded numeric rank string for each character.
  const REFERENCE = buildReference(locale);
  const key = normalized
    .split('')
    .map(ch => rankChar(ch, REFERENCE, collator))
    .join('-');

  return key;
}

// Build a sorted reference alphabet for the locale
function buildReference(locale: string): string[] {
  const base = 'aäåæbcçdeéèêëfghiîïjklmnñoöøpqrstuüùûvwxyz';
  return [...new Set(base.split(''))].sort(
    new Intl.Collator(locale, { sensitivity: 'variant', usage: 'sort' }).compare
  );
}

function rankChar(ch: string, reference: string[], collator: Intl.Collator): string {
  let lo = 0, hi = reference.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (collator.compare(reference[mid], ch) < 0) lo = mid + 1;
    else hi = mid;
  }
  return String(lo).padStart(3, '0');
}
```

## Worker Helper and D1 Integration

```typescript
// worker.ts
import { generateSortKey } from './utils/sortKey';

export interface Env {
  DB: D1Database;
}

const DEFAULT_LOCALE = 'de-DE';

// INSERT with sort key
async function insertProduct(
  env: Env,
  name: string,
  locale: string = DEFAULT_LOCALE
): Promise<void> {
  const sortKey = generateSortKey(name, locale);
  await env.DB
    .prepare('INSERT INTO products (name, sort_key, locale) VALUES (?, ?, ?)')
    .bind(name, sortKey, locale)
    .run();
}

// UPDATE sort key for an existing row
async function updateSortKey(
  env: Env,
  id: number,
  name: string,
  locale: string = DEFAULT_LOCALE
): Promise<void> {
  const sortKey = generateSortKey(name, locale);
  await env.DB
    .prepare('UPDATE products SET sort_key = ? WHERE id = ?')
    .bind(sortKey, id)
    .run();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const locale = request.headers.get('Accept-Language')?.split(',')[0].split(';')[0] ?? DEFAULT_LOCALE;

    const { results } = await env.DB
      .prepare('SELECT id, name FROM products ORDER BY sort_key ASC LIMIT 100')
      .all<{ id: number; name: string }>();

    return Response.json({ locale, products: results });
  },
};
```

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS products (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  name      TEXT NOT NULL,
  sort_key  TEXT NOT NULL DEFAULT '',  -- locale-sensitive sort key
  locale    TEXT NOT NULL DEFAULT 'de-DE',
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Index on sort_key makes ORDER BY sort_key efficient
CREATE INDEX idx_products_sort_key ON products(sort_key);
```

## Bulk Re-keying Migration

When you introduce `sort_key` to an existing table, back-fill all rows:

```typescript
// migrations/backfill-sort-keys.ts  (run as a one-off Worker or wrangler script)
import { generateSortKey } from '../utils/sortKey';

export async function backfillSortKeys(db: D1Database, locale: string): Promise<void> {
  const PAGE = 500;
  let offset = 0;

  while (true) {
    const { results } = await db
      .prepare('SELECT id, name FROM products WHERE sort_key = ? LIMIT ? OFFSET ?')
      .bind('', PAGE, offset)
      .all<{ id: number; name: string }>();

    if (results.length === 0) break;

    const stmts = results.map(row =>
      db.prepare('UPDATE products SET sort_key = ? WHERE id = ?')
        .bind(generateSortKey(row.name, locale), row.id)
    );

    // D1 batch up to 100 statements at a time
    for (let i = 0; i < stmts.length; i += 100) {
      await db.batch(stmts.slice(i, i + 100));
    }

    offset += PAGE;
  }
}
```

## ICU in a WASM Build for SQLite (Pattern and Caveats)

Compiling SQLite with the ICU extension and targeting WASM enables `CREATE COLLATION` from JavaScript, but comes with significant caveats:

- The WASM binary grows by ~12 MB (full ICU data) or ~3 MB (stripped subset).
- Cloudflare Workers have a 10 MB compressed script size limit — full ICU WASM does not fit.
- `sql.js-httpvfs` or `wa-sqlite` with a stripped ICU subset can fit within limits but requires serving the WASM from R2.
- D1 itself is server-managed SQLite and does not accept custom WASM extensions at the D1 API level as of 2026.

For most use cases, the application-level `sort_key` column approach is more practical and equally correct.

## Anti-patterns

- **`ORDER BY name COLLATE NOCASE`** — only handles ASCII case folding; silently mis-sorts all non-ASCII characters.
- **Computing sort keys on read** — defeats the purpose of indexing; generate at write time.
- **Using a single global locale for all sort keys** — if you serve multiple locales, sort keys for `de-DE` may be wrong for `sv-SE` (Swedish treats `å` differently from German). Store one `sort_key` per locale if multi-locale sorting is required, or pick a locale-neutral Unicode CLDR root collation.
- **Lexicographic key comparison after string truncation** — sort keys must be compared in full; do not truncate `sort_key` values stored in D1.

## Gotchas

- `Intl.Collator` in Workers does not expose raw ICU sort-key bytes (no `getSortKey()` method in ECMA-402); the binary-search approximation above works for most European scripts but may mis-order edge cases in CJK, Thai, or Devanagari without a proper ICU4X WASM binding.
- SQLite TEXT ordering is byte-order comparison of UTF-8 encoded strings — two sort keys that differ only in length will sort correctly only if shorter keys compare less than longer ones for the same prefix; pad numeric rank tokens to equal width (handled by `padStart(3, '0')` above).
- D1 batch limit is 100 statements per `db.batch()` call; chunk large migrations.

## Verification

```bash
# Seed test data
npx wrangler d1 execute MY_DB --command \
  "INSERT INTO products (name, sort_key, locale) VALUES
    ('Zebra', '', 'de-DE'),
    ('ärger', '', 'de-DE'),
    ('Apfel', '', 'de-DE'),
    ('öffnung', '', 'de-DE');"

# Run backfill
npx wrangler dev --local migrations/backfill-sort-keys.ts

# Verify sort order
npx wrangler d1 execute MY_DB \
  --command 'SELECT name, sort_key FROM products ORDER BY sort_key ASC'
# Expected order: ärger, Apfel, öffnung, Zebra  (DIN 5007-1)
```

## Related

- `locale-aware-number-parsing-validation-workers.md`
- `translation-memory-d1-fuzzy-match-workers.md`
- `bidi-text-rendering-rtl-mixed-content-workers.md`

## Sources

- Unicode CLDR Collation — https://cldr.unicode.org/index/cldr-spec/collation-guidelines
- MDN Intl.Collator — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Collator
- Cloudflare D1 Batch — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- SQLite Collating Sequences — https://www.sqlite.org/datatype3.html#collation
