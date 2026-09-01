# ICU Collation Tailoring for Locale-Specific Sorting

Sorting strings "alphabetically" is not a single universal operation. Different locales order the same characters differently: Swedish places `å`, `ä`, `ö` after `z`, while German treats `ä` as equivalent to `a` for primary ordering; Czech sorts `ch` as one letter between `h` and `i`; Lithuanian keeps `y` between `i` and `j`. ICU collation tailoring is the mechanism by which the root (DUCET) collation element table is modified per locale to produce these orderings. This article covers how tailoring works, how to apply it correctly in services that sort user-visible lists, and how to keep sort order stable and testable.

## Scope

This article addresses ICU collation customization as defined by the CLDR collation tailorings and UTS #35 collation syntax: the difference between root collation and tailored rules, strength levels, and the practical use of tailorings such as `search`, `phonebook` (German), `traditional` (Spanish), and `eor` (European Ordering Rules). It covers API-level usage and validation. It does not cover the binary-encoding details of collation element tables, ICU data packaging strategy, or database-level collation configuration except as a consumer of the same data.

## Workflow or implementation guidance

Collation order is defined by a two-level model. The Default Unicode Collation Element Table (DUCET) provides root orderings for all code points. Locale tailorings override specific relationships: CLDR defines them in LDML rule syntax (`&a < ä <<< A` style reordering and resetting) and ICU compiles them into collators identified by locale plus collation type, for example `de-DE-u-co-phonebook` or `sv-SE` (default Swedish tailoring).

The strength settings control which differences sort keys encode. Primary strength ignores accents and case ( `a` = `á` = `A`); secondary adds accent sensitivity; tertiary adds case sensitivity; quaternary adds punctuation; identical breaks ties by code point. Choice of strength is a product decision with correctness consequences: a contact list usually wants at least secondary strength, while a search box often wants primary with the `search` collation, which is tailored to ignore more distinctions.

A reliable implementation workflow:

1. Construct collators from locale identifiers that carry the collation type extension where needed. For German phonebook sorting, request `de-DE-u-co-phonebook` explicitly, because the default German ordering treats `ä` near `a` while phonebook ordering clusters `ä` near `a` but also equates `ß` with `ss`.
2. For list endpoints that sort server-side, generate sort keys once per string (`getSortKey` semantics), sort by key bytes, and cache the keys alongside the entities for the request or session lifetime. Repeated comparison callbacks that recompute internal normalization are measurably slower than key-based sorting for lists above a few thousand entries.
3. Paginate with stable tie-breaking: append a unique identifier as the final sort component so equal-sorting strings (for example, two users named `Müller`) keep deterministic pagination order across pages and replicas.
4. For multi-locale products, resolve the collator from the user's resolved locale, not the server default; a French user viewing a shared English document list still expects French conventions for accented names.
5. When merging results from databases that sort with their own collation (for example, ICU-backed column collation or a SQL collation name), ensure the database collation version matches the application's ICU data version, or re-sort the final merged list in the application layer.

A worked example: sorting `["Zebra", "Ärger", "zwo", "Straße"]` with default German collation at secondary strength yields `Ärger` before `Straße` before `Zebra` before `zwo` (case-insensitive tertiary order aside), while phonebook ordering moves `Straße` after `Straße`-as-`Strasse` equivalents cluster and treats `ß` expansion identically. The lesson is that `de` versus `de-u-co-phonebook` is a visible product difference in telephone-directory-like UIs, and the choice must be deliberate and tested.

Numeric ordering deserves mention: `numericOrdering` (also called natural sort) compares digit sequences by numeric value so `file9` sorts before `file10`. It is a collator setting, not a strength, and applies per collator instance.

## Controls

- Pin the ICU version in all deployment environments; collation tailorings occasionally change between CLDR releases, and sort order is user-visible behavior worth changelogging.
- Encode the intended collation type in the locale identifier at the service boundary (`-u-co-...`), so the choice is visible in logs and reproducible from a bug report.
- Snapshot-test representative sort orders per locale family (Germanic with umlauts, Nordic with `åæø`, Iberian with `ñ`/`ch`, Baltic with `y` handling) using fixed input arrays; the expected outputs are frozen fixtures tied to the pinned ICU version.
- Require a deterministic final tie-breaker column in every paginated sorted query to prevent page-boundary duplication under concurrent writes.
- Reject unvalidated collation type strings from client requests; accept an allowlist (default, phonebook, traditional, search, eor) to prevent constructing arbitrary tailorings.

## Validation evidence

- Collation tailorings, the LDML rule syntax that defines them, and the collation type keywords are specified in UTS #35 (LDML), with the underlying root table defined in UTS #10 (Unicode Collation Algorithm), both published by the Unicode Consortium.
- The ICU User Guide collation chapters document the collator API, strength levels, and the bundled tailorings per locale.
- A reproducible check: build a collator for `es` (traditional) and one for `es-u-co-eor`, sort the array `["lápiz", "llama", "lobo", "LM", "ñandú"]`, and observe that traditional Spanish orders `ll` between `l` and `m` while the default modern ordering does not — verifying the tailoring is active and the test harness is meaningful.

## Failure modes and correction

- **Sorting by code point or naive lowercase comparison.** Symptom: accented names cluster at the end of lists in Scandinavian locales and users file "wrong order" bugs. Correct by routing all user-visible sorts through locale-aware collators.
- **Missing collation type for phonebook UIs.** Symptom: German users cannot find `Straße` entries near `Strasse`. Correct by selecting `de-u-co-phonebook` for directory-like surfaces.
- **Strength set too coarse.** Symptom: primary strength collapses `résumé` and `resume` in an admin list, hiding distinctions. Correct by choosing secondary or tertiary per surface and documenting the choice.
- **Version skew between database and application collation.** Symptom: same query returns different orders from read replicas. Correct by pinning matching versions and re-sorting merged results at the application layer.
- **Unstable pagination without a tie-breaker.** Symptom: items repeat or vanish across pages when equal-sorting rows shift. Correct by appending a unique key to the sort specification.

## Limitations

- Collation defines ordering, not equivalence for identity purposes: two strings that sort equal at a given strength are not necessarily identical content, so deduplication logic must not rely on sort-key equality alone.
- Exotic tailorings beyond CLDR's set require hand-written LDML rules, which introduces maintenance burden and version-upgrade review overhead.
- Sort keys are version-stable only within the same ICU data version; persisted sort keys must record the version that produced them.
- Performance-critical paths sorting tens of millions of strings may need precomputed keys or a search index rather than per-request collation.

## Canonical sources

- Unicode Consortium, UTS #10: Unicode Collation Algorithm: https://unicode.org/reports/tr10/
- Unicode Consortium, UTS #35: Unicode Locale Data Markup Language (LDML) — collation: https://unicode.org/reports/tr35/
- Unicode, ICU User Guide — Collation: https://unicode-org.github.io/icu/userguide/collation/
