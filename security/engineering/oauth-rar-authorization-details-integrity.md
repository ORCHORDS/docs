# OAuth Rich Authorization Request Integrity

**Issue:** RFC 9396 `authorization_details` can express fine-grained authority, but loose type handling or a mismatch between consent, token issuance, and resource enforcement can amplify privileges.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Accept `authorization_details` only as a JSON array of recognized, type-specific objects and validate every field, identifier, action, location, and extension against policy.
- Merge scopes and rich details into one consent and authorization decision; do not let a broad scope silently override a narrow detail or vice versa.
- Protect request integrity with PAR, JAR, or another authenticated channel when an intermediary or user agent could alter details.
- Bind the authorized details to the resulting grant and token representation, and make introspection or token validation expose exactly what resource servers must enforce.
- Preserve exact security-significant identifiers while applying one documented canonicalization policy. Reject ambiguous duplicates and conflicting objects.
- Minimize detail values and prevent sensitive account, transaction, or location data from leaking through URLs, logs, browser history, or analytics.

## Verification
- Mutate type, action, location, identifier, and amount between request, consent, token, introspection, and resource call; every mismatch is rejected.
- Test duplicate and conflicting detail objects plus an unknown type under the documented policy.
- Inspect authorization-server, proxy, browser, and resource-server logs for leaked detail values.

## Gotchas
RAR makes authorization more expressive; it does not define the business policy or replace audience restriction, sender constraint, consent, and resource-server enforcement.

## Official sources
- https://www.rfc-editor.org/rfc/rfc9396.html
