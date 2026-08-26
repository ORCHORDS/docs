# Unicode identifier status and restriction levels

**Issue:** Accepting every Unicode code point in usernames, handles, tenant slugs, or language identifiers creates visually confusable, mixed-script, default-ignorable, and unstable identifiers. ASCII-only rejection is unnecessarily exclusionary, while normalization alone does not address spoofing.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Define an identifier profile using Unicode Security Mechanisms: permitted Identifier_Status/Identifier_Type values, normalization form, script restriction level, length measured in code points and bytes, and explicit exceptions. Store the original display form separately from a canonical comparison key. Run confusable detection as a risk signal and uniqueness check, not an automatic claim that two people are the same.

Version the Unicode data and migration policy. Existing identifiers must not silently change ownership when tables update. Reserve dangerous bidi controls and default ignorables unless a reviewed profile needs them.

## Verification

Test mixed scripts, whole-script confusables, combining sequences, join controls, bidi controls, emoji, normalization equivalents, case mapping, long expansions, Unicode-version upgrades, and collision handling. Include legitimate multilingual fixtures reviewed by native users.

## Gotchas

Restriction levels reduce spoofing risk but do not prove identity. Display fonts affect confusability, and a skeleton is not suitable as the user-visible identifier.

## Sources

- Unicode Consortium, [UTS #39 Unicode Security Mechanisms](https://unicode.org/reports/tr39/)
- Unicode Consortium, [UAX #31 Unicode Identifiers](https://unicode.org/reports/tr31/)
