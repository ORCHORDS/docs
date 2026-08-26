# accent-insensitive-search-pipeline-2026

**Issue:** Users searching "jose" could not find records stored as "José"; filtering "Düsseldorf" by typing "dusseldorf" returned nothing; and the same name existed twice in the database in different Unicode normalizations (NFC vs NFD), so even exact-match search missed duplicates. The frontend fixed it with a `normalize('NFD')`-strip helper, but server-side filtering, uniqueness checks, and autocomplete each implemented their own (or no) folding, so behavior differed per surface. Accent-insensitive search is a cross-layer pipeline: input normalization, folding, storage, and indexing must all agree — one JavaScript snippet in the UI is not a design.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Normalization before folding

1. **Normalize to a single form first, everywhere.** The same visual string "é" can be one code point (NFC, U+00E9) or two (NFD, `e` + combining acute). `===`, `includes`, and SQL equality all fail across forms. Pick NFC for storage (W3C recommendation), apply `String.prototype.normalize('NFC')` at every write boundary, and normalize incoming queries too.
2. **Fold by decomposing and stripping marks.** The canonical frontend pattern is `s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()` (Unicode property escapes catch all combining marks, superior to the older `[\u0300-\u036f]` range that misses marks outside the Latin block). Note that `unorm`-style helpers and npm packages like `remove-accents` implement the same idea with tables.
3. **Order matters: normalize → strip → downcase.** Downcasing before NFD decomposition misses precomposed lowercase-accented forms in some pipelines; do decomposition-based folding first, then case-fold, then trim.
4. **Not everything folds cleanly.** `ß` never loses its accent (it has none) and does not become "ss" under diacritic stripping; `ø`, `đ`, `ł` are base letters, not accented characters — naive stripping leaves them in place (searching "smor" for "smør" fails). If your product needs those folded, use a lookup-table folder (e.g. `any-ascii`, ICU `Latin-ASCII` transform) instead of pure mark-stripping.

## Frontend filtering vs backend search

1. **Client-side filter: fold both sides per keystroke.** For in-memory lists (autocomplete over already-loaded data), precompute a folded index (`foldedName` field) at data-build time and compare `foldedName.includes(fold(query))` — folding on every keystroke over every item is O(n) work you can avoid.
2. **`Intl.Collator` for short in-memory comparisons.** `new Intl.Collator(locale, { sensitivity: 'base' }).compare(a, b)` treats "Jose" and "José" as equal *for comparison* (it cannot produce a folded key for substring search). Fine for dedup checks; not sufficient for `includes`-style matching.
3. **PostgreSQL: `unaccent` with an immutable wrapper and an index.** `CREATE EXTENSION unaccent;` gives the dictionary, but `unaccent()` is STABLE, not IMMUTABLE, so a functional index requires wrapping it in an `IMMUTABLE` function; or add `unaccent` into a custom text search configuration's mapping. For structured (non-full-text) search, the portable pattern is an application-maintained `search_folding` column with a btree/trigram index.
4. **MySQL: collation does the work.** `utf8mb4_0900_ai_ci` (accent-insensitive, case-insensitive) makes `LIKE` and `=` match "jose" against "José" with no folding code — but then equality checks are also accent-blind, which can silently break exact-match features; choose per column, not server-wide.
5. **Precomputed folded column as the portable default.** Storing `fold(first_name) || ' ' || fold(last_name)` in a dedicated indexed column (updated by the same code path that writes the record) works identically across Postgres/MySQL/SQLite/DynamoDB and keeps the folding rules in one place — your application — instead of spread across DB engines.

## Correctness and performance caveats

1. **Accent-blindness is wrong for some languages.** In Danish/Norwegian/Swedish, `å`, `æ`, `ø` are distinct letters, not "a with decoration" — folding them makes "hånd" collide with "hand" and users notice. Make accent-insensitivity a per-locale or per-user setting (or default it off for da/no/sv/tr/lt) rather than global.
2. **Turkish i breaks naive folding.** `.toLowerCase()` maps `I`→`ı` in tr-TR contexts and `İ` decomposes into `i` + dot-above which mark-stripping then removes — the collision behavior differs from English. Fold with an explicit non-Turkish locale for keys, and test the `Çınaraltı`/`ÇINARALTI` pair.
3. **Cross-script search needs transliteration, not folding.** Folding only removes marks within Latin; matching "Dostoevsky" to "Достоевский" requires a transliterated search key (see `transliteration-vs-translation-2026`). Layer it: normalize → transliterate → fold for the search key.
4. **Index the fold, not the query-time computation.** `WHERE unaccent(name) ILIKE …` without an index is a full table scan; either index the immutable-wrapped expression or maintain the folded column. For typo tolerance, combine with `pg_trgm` over the folded column.
5. **Keep folding rules versioned and test them.** Unicode normalization and CLDR tables change between runtime/library upgrades (and Postgres `unaccent` rules change across major versions), so snapshot folding behavior in unit tests: "José"→"jose", "Düsseldorf"→"dusseldorf", "İstanbul"→"istanbul" (or document that it doesn't), "smør"→"smør" (documented non-fold).
