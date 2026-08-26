# UTS #46 IDNA processing mode contract

**Issue:** Services convert the same Unicode domain with different IDNA processing modes, accepting or displaying inconsistent hostnames.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

UTS #46 defines compatibility processing around IDNA2008, including mapping, validation, and transitional/nontransitional choices. Pin one reviewed mode per boundary and compare canonical ASCII forms where hostname identity matters.

**Source:** [Unicode Technical Standard #46: Unicode IDNA Compatibility Processing](https://unicode.org/reports/tr46/)

## Controls

- use a maintained IDNA library, never hand-written Punycode alone;
- specify transitional behavior, STD3 rules, and error handling explicitly;
- retain user input separately from the validated A-label when audit/display requires it;
- apply bidi/contextual validation and label/DNS length limits;
- use a separate confusable-display policy.

## Verification

Run Unicode's IDNA test data for the pinned version, including deviation characters, joiners, bidi labels, disallowed code points, dots, empty labels, and overlength names. Cross-service outputs must match.

## Gotchas

Punycode encodability is not IDNA validity. UTS #46 mapping can change input before validation. DNS resolution does not prove a Unicode display form is safe.
