# Intl.supportedValuesOf capability enumeration

**Issue:** A settings UI ships a stale hard-coded list of calendars, collations, currencies, numbering systems, time zones, or units and offers values the current runtime cannot format.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

ECMA-402 `Intl.supportedValuesOf()` enumerates supported values for defined keys. Use it as runtime capability evidence, then intersect with product policy and stored-data requirements.

**Source:** [ECMA-402 — Intl.supportedValuesOf](https://tc39.es/ecma402/#sec-intl.supportedvaluesof)

## Controls

- feature-detect the function and each required key;
- intersect results with an allowlist appropriate to the product;
- preserve stored legacy choices even when temporarily unsupported;
- provide localized labels separately from machine identifiers;
- cache per runtime build, not forever across ICU upgrades.

## Verification

Test supported and invalid keys, server/client differences, ICU-small builds, empty intersections, stored unsupported values, and upgrade diffs. Confirm sorting uses localized labels without changing stored identifiers.

## Gotchas

Supported does not mean appropriate for every locale. Currency enumeration is not a list of currently circulating currencies. Time-zone aliases and canonicalization require separate policy.
