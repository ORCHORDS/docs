# OAuth Resource Indicators and Audience-Restricted Tokens

**Issue:** A broadly reusable access token increases blast radius because one compromised resource server can replay it at another API.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Send an absolute, fragment-free `resource` identifier when a client requests authorization for a specific protected resource.
- Have the authorization server bind the issued token to the requested resource and expose the resulting audience unambiguously.
- Resource servers must reject tokens whose audience does not identify them, even when signature, issuer, and expiry are valid.
- Request the smallest resource set needed; avoid multi-resource tokens unless the use case and trust model justify them.
- Bind refresh-token use to the originally authorized resources and prevent silent audience expansion.

## Verification

- Present a valid token to a sibling API and require audience rejection.
- Test omitted, repeated, query-bearing, relative, malformed, and fragment-bearing resource values.
- Exchange refresh tokens while attempting to add an unauthorized resource.

## Gotchas

- Verify source maturity and product support before making a normative claim.
- Keep secrets, tokens, personal data, and restricted evidence out of examples and logs.
- Reassess after material changes to scope, dependencies, or enforcement.

## Sources

- https://www.rfc-editor.org/rfc/rfc8707.html
