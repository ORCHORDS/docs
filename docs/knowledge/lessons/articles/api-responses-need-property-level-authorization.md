# API Responses Need Property-Level Authorization

**Issue:** An endpoint correctly authorizes access to an object but serializes sensitive fields that the caller is not authorized to read.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API3:2023 distinguishes authorization to an object from authorization to individual properties of that object. Passing the object-level check does not justify returning every stored field.

## Engineering rule

- Define response schemas per operation and caller capability.
- Explicitly select fields that may be returned instead of serializing entire persistence models.
- Apply property-level authorization before response construction.
- Keep returned structures to the minimum required by the endpoint's contract.
- Add response-schema validation as a defense-in-depth check.

## Verification

- Test the same object through callers with different roles and compare the returned field sets.
- Seed sensitive internal-only properties and assert they never appear in unauthorized responses.
- Fuzz optional fields and expansions to verify they cannot expose hidden properties.

## Official source

- OWASP API3:2023 Broken Object Property Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/
