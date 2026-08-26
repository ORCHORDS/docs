# EHDS secondary-use permit boundaries

**Issue:** Regulation (EU) 2025/327 establishes the European Health Data Space. Secondary use of electronic health data is permission- and purpose-bound and involves health data access bodies and secure processing environments; applicability and transition dates require jurisdiction-specific legal analysis.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Classify the requested purpose, prohibited uses, data categories, controller/holder roles, permit basis, minimisation, retention, and publication duties.
- Release only the authorised dataset inside the approved secure processing environment; separate identity/key administration from analysis.
- Log permit conditions, queries, exports, transformations, and deletion evidence without copying sensitive data into general logs.

## Verification

1. Deny a purpose, field, user, export, or retention period outside the permit.
2. Test revocation and expiry while preserving required audit evidence.
3. Verify output checking prevents row-level or otherwise disallowed disclosure.

## Gotchas

A research or public-interest label is not itself a permit. EHDS phases obligations over time and interacts with GDPR and national health law; this is an engineering control map, not a conclusion that processing is lawful.

## Official sources

- https://eur-lex.europa.eu/eli/reg/2025/327/oj
