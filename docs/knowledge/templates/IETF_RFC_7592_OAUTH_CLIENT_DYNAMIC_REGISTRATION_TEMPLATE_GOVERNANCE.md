# IETF RFC 7592 OAuth 2.0 Dynamic Client Registration Management Template Governance

## Purpose
Establish the governance pattern for templating OAuth 2.0 dynamic client registration management endpoints per IETF RFC 7592, including client update, configuration retrieval, and deletion flows.

## Scope
Applies to every OAuth/OIDC relying party and authorization server produced by the studio that exposes dynamic client registration endpoints, regardless of whether the registration endpoint is publicly accessible or restricted.

## Workflow
1. Use a templated registration request payload that conforms to RFC 7591 with optional software_statement, logo_uri, and policy_uri fields.
3. On successful registration, persist the registration_access_token and registration_client_uri and store them with the client metadata; the client MUST be rotated whenever the registration_access_token is rotated.
5. Template the update request to apply RFC 7592 §3.2 semantics: only writable fields may be modified; the client_id is immutable.
7. Template the configuration retrieval and deletion requests per RFC 7592 §3.3 and §3.4, with explicit verification of the registration_access_token bearer credential.
9. Capture registration events in an audit trail keyed to the client_id, the registration_access_token's SHA-256 hash, and the timestamp.

## Controls and evidence
- Client registration record with RFC 7591/7592 field set, registration_client_uri, and registration_access_token metadata (hash only).
- Update history with previous and new field values, diff summary, and operator.
- Audit log entry for every retrieval, update, or deletion action with result code and error code (where applicable).
- Quarterly reconciliation between active registrations and the client inventory.

## Validation
- Verify a sampled registration record's fields match the latest server-side configuration.
- Recompute the audit-log hash for three sampled events and confirm consistency with the audit repository.
- Confirm the registration_access_token is stored only as a hash and never as plaintext in any backup snapshot.

## Failure correction
- **Registration_access_token exposed** → revoke and reissue, document the incident, and audit for misuse within the exposure window.
- **Client_id mutated** → reject the update, document the attempt, and reissue the immutable client_id.
- **Drift between registration record and client inventory** → reconcile within 24 hours, document the cause, and tighten the inventory refresh cadence.

## Limitations
- RFC 7592 is a management plane protocol and does not itself define the registration payload format; refer to RFC 7591 for the initial registration.
- Registration_access_tokens are bearer credentials; any logging that records them in plaintext must be remediated.
- Dynamic registration does not absolve the client of meeting the authorization server's policy requirements (e.g., PKCE, redirect URI validation).

## Scope note
This article is part of the templates leaf. Cross-reference: IETF_RFC_7807_PROBLEM_DETAILS_TEMPLATE_GOVERNANCE.md, OPENAPI_3_1_SPECIFICATION_TEMPLATE_GOVERNANCE.md, IETF_RFC_8259_JSON_INTERCHANGE_TEMPLATE_GOVERNANCE.md.

## Canonical sources
- IETF RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol: https://datatracker.ietf.org/doc/html/rfc7591
- IETF RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol: https://datatracker.ietf.org/doc/html/rfc7592
- IETF RFC 6749 — The OAuth 2.0 Authorization Framework: https://datatracker.ietf.org/doc/html/rfc6749
- IETF RFC 8252 — OAuth 2.0 for Native Apps: https://datatracker.ietf.org/doc/html/rfc8252
- OpenID Connect Dynamic Client Registration 1.0: https://openid.net/specs/openid-connect-registration-1_0.html