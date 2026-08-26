# OAuth Protected Resource Metadata RFC 9728 Discovery

**Issue:** Clients that guess resource-server authorization details can select the wrong issuer, scope, token presentation method, or signing keys.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Publish metadata at the deterministic well-known location derived from each protected-resource identifier.
- Require the returned `resource` value to exactly identify the resource whose metadata was requested.
- Constrain acceptable authorization servers and token-presentation methods; cross-check enumerable resource and authorization-server relationships.
- Prefer signed metadata where an application profile requires authenticated claims, and make signed values override matching plain JSON values.
- Cache with bounded freshness and fail closed when security-critical metadata becomes inconsistent.

## Verification

- Request metadata for valid and lookalike resource identifiers and reject authority or path substitution.
- Test unsigned, incorrectly signed, expired, conflicting, and recursively nested `signed_metadata`.
- Rotate advertised keys and issuers while validating cache expiry and rollback behavior.

## Gotchas

- Verify source maturity and product support before making a normative claim.
- Keep secrets, tokens, personal data, and restricted evidence out of examples and logs.
- Reassess after material changes to scope, dependencies, or enforcement.

## Sources

- https://www.rfc-editor.org/rfc/rfc9728.html
