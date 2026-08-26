# CLDR emoji collation order boundary

**Issue:** Sorting emoji by code point, UTF encoding, or localized display label yields unstable and unintuitive order, especially for sequences, modifiers, and newly assigned characters.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

When a product needs an emoji picker or curated emoji ordering, use the applicable CLDR emoji collation data and a pinned Unicode release. Do not use this presentation order as a database key or canonical identity.

## Controls

- Store emoji as normalized sequence data without destructive splitting.
- Key identity by the complete sequence, including variation selectors and modifiers where semantically relevant.
- Pin Unicode emoji and CLDR versions in generated assets.
- Define placement of unknown/new sequences deterministically.
- Separate collation order from grouping, search keywords, and recently-used ranking.
- Preserve explicit user/favorites order.
- Avoid locale label sorting as a substitute for emoji collation.
- Rebuild and diff picker indices during Unicode upgrades.

## Verification

Cover single code points, ZWJ sequences, flags, keycaps, skin-tone modifiers, variation presentation, unknown future sequences, and mixed emoji/text lists. Compare generated order to CLDR collation test material and verify stable migration of favorites.

## Gotchas

Emoji collation is for ordering, not grapheme segmentation or validity. Vendor rendering differs. New Unicode versions can intentionally move or add entries, so snapshot drift requires review rather than silent acceptance.

## Sources

- [Unicode LDML Collation](https://unicode.org/reports/tr35/tr35-collation.html)
- [Unicode Emoji Technical Standard](https://www.unicode.org/reports/tr51/)
- [CLDR collation data](https://github.com/unicode-org/cldr/tree/main/common/collation)
