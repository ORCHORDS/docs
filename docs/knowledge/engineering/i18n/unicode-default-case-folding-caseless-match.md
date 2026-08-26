# Unicode default case folding for caseless matching

**Issue:** Identifiers and lookup keys are compared with lowercase transformations. Matches change by language, multi-code-point folds are lost, and visually similar strings become accidentally equal or unexpectedly different.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Semantic boundary

Unicode case folding supports caseless matching; it is not the same operation as locale-sensitive lowercasing for display. The Unicode Standard defines default caseless matching and related canonical/compatibility procedures. The Unicode Character Database publishes mappings in `CaseFolding.txt`.

Choose the equality contract before choosing an API:

- **Display casing:** use locale-aware case mapping and preserve original text.
- **Default caseless lookup:** use full default case folding with the normalization required by the chosen Unicode procedure.
- **Identifier security:** apply the identifier profile, normalization, script, and confusable rules for that namespace in addition to case folding.
- **Search:** may need locale collation, tokenization, accent policy, and ranking rather than binary folded equality.

A case-folded value is a derived key. Never replace the original user string with it.

## Implementation controls

1. Pin a Unicode data/runtime version and record it with persisted derived keys. Mappings can evolve between Unicode versions.
2. Prefer the platform's explicit full case-fold operation. Generic `toLowerCase()` or database `LOWER()` is not a portable substitute.
3. Apply normalization and folding in the order specified by the selected Unicode matching definition. Do not invent “NFC then lowercase” and label it Unicode caseless matching.
4. Use full mappings where the namespace permits length-changing results. Simple mappings exist for constrained implementations and can produce a different equivalence relation.
5. Decide explicitly whether Turkic-specific mappings are in scope. Do not switch behavior from request locale for a global account or tenant identifier.
6. Store a uniqueness key together with algorithm/version metadata; enforce uniqueness atomically on that key.
7. When upgrading Unicode, recompute into a shadow column, detect newly colliding values, resolve them, then switch reads and constraints.

## Verification

Build conformance fixtures from the pinned UCD and add product cases for ASCII, Greek sigma forms, German sharp s, Turkic dotted/dotless I, combining marks, supplementary-plane characters, empty input, and strings whose fold expands. Verify symmetry, idempotence of the chosen transformation, and equality before/after storage round trips.

Run collision analysis against production-shaped data before changing Unicode or database versions. Log only bounded hashes or test identifiers when values can contain personal data.

## Gotchas

- Case folding does not remove accents and does not solve homoglyph spoofing.
- Locale-sensitive casing can be correct for UI and wrong for a global key.
- Database collations have independent version and tailoring behavior.
- Equal folded keys do not imply equal grapheme sequences or user intent.

## Sources

- [Unicode Standard 17.0, Chapter 3 — Conformance (Caseless Matching)](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/)
- [Unicode 17.0 CaseFolding.txt](https://www.unicode.org/Public/17.0.0/ucd/CaseFolding.txt)
