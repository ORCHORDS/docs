# CLDR transform ID versioning

**Issue:** CLDR transforms and transliterators are identified by source/target/variant and direction. Treating a transform name as a timeless algorithm makes indexes and stored transliterations change across data upgrades.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Pin CLDR/ICU version, canonicalize transform IDs, validate direction and filters, and store original text alongside derived output. Rebuild search/display derivatives on upgrade; never overwrite authoritative names. Bound expansion and processing time.

## Verification

Test forward/reverse, aliases, variants, contextual rules, normalization, unmapped characters, expansion limits, version changes, and round-trip expectations.

## Gotchas

Reverse transforms are not necessarily inverses and transliteration is not translation or identity normalization.

## Sources

- Unicode Consortium, [UTS #35 Transforms](https://unicode.org/reports/tr35/tr35-general.html#Transforms)
