# Unicode property and value alias governance

**Issue:** A data pipeline persists informal Unicode property labels or numeric enum positions, then breaks when runtimes, generated tables, or Unicode versions differ.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

UAX #44 defines the Unicode Character Database, including normative property and property-value aliases. Generate tables from a pinned release and use recognized aliases at parsing boundaries; do not infer semantics from display names or enum order.

**Source:** [Unicode Standard Annex #44: Unicode Character Database](https://unicode.org/reports/tr44/)

## Controls

- record the Unicode version with generated artifacts;
- resolve aliases through PropertyAliases.txt and PropertyValueAliases.txt from that release;
- serialize stable textual identifiers rather than library-specific integers;
- distinguish missing, unknown, and defaulted values;
- regenerate and diff tables during upgrades.

## Verification

Test long and short aliases, loose matching only where specified, unknown values, newly assigned code points, and cross-service version mismatch. Golden tests assert generated table provenance and deterministic output.

## Gotchas

Property stability rules differ by property. Alias equivalence does not mean two properties have identical semantics. UCD updates must be reviewed, not silently consumed at runtime.
