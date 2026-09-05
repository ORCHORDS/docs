# API Write Models Must Allowlist Mutable Properties

**Issue:** Client JSON is bound directly into an internal object, allowing callers to modify fields that exist in storage but were never intended to be user-controlled.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API3:2023 includes mass-assignment-style failures within broken object property level authorization. If the transport model mirrors the persistence model, newly added internal fields can accidentally become writable without an explicit API design decision.

## Engineering rule

- Use operation-specific input schemas or DTOs rather than binding arbitrary client fields to domain or persistence objects.
- Allowlist mutable properties and reject or ignore unknown fields according to a documented contract.
- Re-check authorization for sensitive state transitions even when the property is otherwise writable.
- Make schema changes trigger authorization-focused tests.

## Verification

- Add an internal boolean or privileged field to the persistence model and confirm existing endpoints cannot modify it.
- Send extra properties in request bodies and verify the documented unknown-field behavior.
- Test writable fields across roles and object ownership boundaries.

## Official source

- OWASP API3:2023 Broken Object Property Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/
