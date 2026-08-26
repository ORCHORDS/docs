# Unicode common-reference version pinning

**Issue:** Specifications and generated artifacts cite “Unicode” without a version, making conformance claims and test results irreproducible.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

UAX #41 defines common references for Unicode specifications and versions. Record the precise Unicode Standard, UAX/UTS revision, and data-file version used by an implementation or durable artifact.

**Source:** [Unicode Standard Annex #41: Common References](https://unicode.org/reports/tr41/)

## Controls

- cite stable versioned references in conformance documents;
- record data-file checksums/releases in generated artifacts;
- separate latest-edition links from the version actually implemented;
- rerun conformance suites before changing version claims;
- keep Unicode, CLDR, ICU, and TZDB versions distinct.

## Verification

Builds must expose provenance, reproduce tables from pinned inputs, reject mixed-version bundles, and diff normative property changes during upgrade.

## Gotchas

A dated URL alone may not identify every dependency. “Latest Unicode” is not a reproducible contract. CLDR and Unicode releases are related but separately versioned.
