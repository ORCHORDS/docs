# database-collation-locale-indexing

**Issue:** Applications get localized sorting and case-insensitive search right in the browser (Intl.Collator) and then get it wrong in the database. The database's collation decides how ORDER BY sorts user names, how = and LIKE compare strings, and whether indexes can serve those queries. Defaults are traps: PostgreSQL's glibc-based collations silently change sort order across OS upgrades and corrupt indexes; MySQL's utf8mb4_0900_ai_ci gives accent- and case-insensitive equality that surprises teams expecting binary comparison; and none of the defaults match what the UI shows the user. The engineering problem is choosing collation providers per column or per database, keeping linguistic behavior stable across library upgrades, emulating the case/accent-insensitive behavior users expect from search, and knowing which operations (LIKE, pattern matching) stop working with nondeterministic collations.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Provider choice and stability

1. **glibc collations are a corruption risk.** PostgreSQL on Linux defaults to glibc collations whose sort order changes between glibc releases; after an OS upgrade, B-tree indexes on text columns can become silently corrupt — lookups miss rows that are present. This is the best-documented reason to move off libc providers for linguistic columns.
2. **ICU is the stable cross-platform choice.** ICU collations in PostgreSQL (provider icu) behave identically across operating systems and version their rules explicitly; PostgreSQL records the ICU version used at index creation and warns when it drifts, giving a reindex signal instead of silent corruption. Prefer ICU for any column whose sort order users can see.
3. **C/ucs_basic for machine-handled text.** Identifiers, tokens, enum-like code columns, and locale-independent keys should use the C collation (or the PG17+ built-in ucs_basic provider, which is stable by construction). These columns never need linguistic ordering, so deterministic byte ordering removes an entire class of upgrade risk.
4. **MySQL: always utf8mb4, know your ai_ci.** MySQL 8's default utf8mb4_0900_ai_ci is accent-insensitive and case-insensitive: 'Muller' matches 'Müller' and 'STRASSE' matches 'straße' in some cases. That is often what product wants for search but surprising for uniqueness constraints — a UNIQUE index on email under ai_ci folds cases silently. Choose utf8mb4_bin or a cs (case-sensitive) variant deliberately for exact-match columns.
5. **Version pinning and reindex discipline.** Both engines expose collation versioning: run REINDEX after glibc/ICU upgrades when warned, and include an index-integrity check (amcheck for PostgreSQL) in post-upgrade runbooks for any text index built on a linguistic collation.

## Nondeterministic collations and case/accent-insensitive search

1. **PG 12+ nondeterministic ICU collations.** Create a collation with deterministic = false and strength primary/secondary to make 'a' = 'A' = 'á' true in equality and unique constraints, emulating MySQL's ai_ci behavior. This gives correct linguistic deduplication at the database layer instead of app-side normalization.
2. **LIKE stops working.** Nondeterministic collations do not support LIKE and some pattern operators on those columns. Plan the architecture: either keep a deterministic shadow column for LIKE queries, or serve prefix/substring search through a trigram index (pg_trgm GIN on a normalized column) or full-text search rather than LIKE on the nondeterministic column.
3. **Functional indexes for search normalization.** A common compromise: keep the base column deterministic ICU for sorting, and add an expression index on lower(unaccent(col)) or a normalized column for search. This preserves LIKE and gives controllable behavior, at the cost of the app owning the normalization pipeline (including NFC normalization first, since unaccent on decomposed text behaves differently).
4. **Match the UI collator.** Users see Intl.Collator ordering in the frontend (case-insensitive, accent-aware, locale-sensitive). A database ORDER BY under a generic collation will disagree for edge cases (Swedish å vs z, German ä sorting). Accept divergence for lists that are paged server-side, or sort client-side per page only when the full result set is small; for large datasets, pick the ICU collation closest to the dominant locale and document the difference.

## Multi-locale schema strategies

1. **Per-column collation for locale-partitioned data.** When a table stores names from one dominant locale (a Japanese user table), a single ja-JP ICU collation on that column gives correct ordering for that population. International mixed tables cannot be sorted correctly for everyone with one collation — decide on a canonical display order (typically en-US root collation) and sort per-user views client-side where it matters.
2. **Store locale next to the text.** Keep a locale column beside user-generated text so downstream jobs can pick collations, segmenters, and analyzers per row. Without it, choosing the right collation for sorting or FTS later requires guessing from content.
3. **Normalization at the boundary.** Normalize all text to NFC on write (both engines store UTF-8; the failure is logically-equivalent strings looking unequal to byte-based comparisons). Enforce in the API layer or via triggers/checks, because nondeterministic collations mask but do not fix mixed normalization.
4. **Migration ordering.** Changing a collation on a populated column rewrites indexes and locks tables: plan ALTER ... TYPE with care, batch it, and verify index rebuilds completed before declaring the migration done. Test the migration on a production-size dataset, since collation changes on large text indexes are among the longest-running schema migrations.

## Verification

1. **Collation fixture tests.** Seed a fixture table with linguistic edge cases per locale (German umlauts, Swedish åäö order, Turkish dotless i, CJK full/half-width forms, decomposed vs composed accents) and assert ORDER BY and equality results match expectations in CI against the same engine and collation as production.
2. **The Turkish-i regression test.** The canonical bug: case-folding 'I' under Turkish locale must yield 'ı', not 'i'. Any case-insensitive uniqueness or email comparison logic (app or DB) gets an explicit test for Turkish users.
3. **Post-upgrade index validation.** After any OS or engine upgrade touching ICU/glibc, run index validation and spot-check sorted queries against pre-upgrade snapshots; silent corruption means the query returns wrong rows with zero errors raised.
4. **Document the collation matrix.** Record which columns use which collation and why (machine keys = C, display names = ICU per locale, search = normalized expression index). Six months later this table is the difference between a deliberate change and an accidental regression.
