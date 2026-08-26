# Unicode Identifier Profile and Versioning with UAX #31

**Issue:** A product admits “Unicode letters” into slugs, handles, or programming-like identifiers using a broad regular expression, then normalization changes validity, new Unicode versions change the accepted set, or invisible syntax characters enter identifiers.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Define and version an identifier profile, not merely an allow-list. Base general-purpose identifiers on `XID_Start` followed by `XID_Continue`; UAX #31 recommends the XID properties because they incorporate normalization closure. State the chosen Unicode version, normalization form, additions/removals, join-control policy, maximum code points/graphemes, and comparison rule.

Normalize once at the input boundary, validate the normalized output, and store both a stable canonical key and the user-facing spelling where the product permits it. Keep authorization IDs separate from display names. If upgrading Unicode data expands validity, run collision and spoofing analysis before accepting new code points, and grandfather already issued identifiers explicitly.

## Verification

Test combining marks, canonically equivalent strings, compatibility characters, leading digits, connector punctuation, format controls, ZWJ/ZWNJ contexts, mixed direction, empty-after-processing input, maximum length, and strings whose properties changed between pinned Unicode versions. Confirm every service uses the same profile artifact and canonical comparison key.

## Gotchas

UAX #31 defines syntax and stability machinery, not complete spoof protection; apply UTS #39 where visual impersonation matters. A language runtime's identifier grammar is not automatically suitable for account handles. Normalizing after uniqueness lookup creates collisions and normalization alone does not make confusable strings equal.

## Sources

- [Unicode Standard Annex #31 — Unicode Identifiers and Syntax](https://www.unicode.org/reports/tr31/)
- [Unicode Technical Standard #39 — Unicode Security Mechanisms](https://www.unicode.org/reports/tr39/)
