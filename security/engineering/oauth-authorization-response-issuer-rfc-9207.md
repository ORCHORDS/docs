# OAuth Authorization-Response Issuer Validation with RFC 9207

**Issue:** A client connected to multiple authorization servers can send a code to the wrong token endpoint during an OAuth mix-up attack.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Record the expected issuer with each authorization transaction before redirecting the user.
- Require and decode the authorization-response `iss` parameter when the selected server advertises support.
- Compare `iss` with the expected issuer using exact simple-string comparison and reject mismatches before code exchange.
- Require unique issuer identifiers across configured authorization servers.
- For OpenID Connect front-channel ID tokens, require the response `iss` parameter and ID-token issuer claim to agree.

## Verification

- Swap responses between two configured issuers and confirm neither code reaches the wrong token endpoint.
- Test missing, duplicated, encoded, case-varied, query-bearing, and fragment-bearing issuer values.
- Cover success and error authorization responses, including a JARM profile where the issuer is carried inside the protected response.

## Gotchas

- Verify source maturity and product support before making a normative claim.
- Keep secrets, tokens, personal data, and restricted evidence out of examples and logs.
- Reassess after material changes to scope, dependencies, or enforcement.

## Sources

- https://www.rfc-editor.org/rfc/rfc9207.html
