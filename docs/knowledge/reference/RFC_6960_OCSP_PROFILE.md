---
title: "RFC 6960 OCSP Profile"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 6960 (June 2013); https://www.rfc-editor.org/rfc/rfc6960"
---

# RFC 6960 OCSP Profile

## Scope

Reference card for IETF RFC 6960, *X.509 Internet Public Key Infrastructure Online Certificate Status Protocol (OCSP)* (June 2013). OCSP provides a mechanism for obtaining timely information about the revocation status of an X.509 certificate without requiring CRL download. Profiles governing certificate validation and revocation handling should reference RFC 6960 by revision, supplemented by RFC 8954 (nonce extension), RFC 9760 (signed responses), and the CA/Browser Forum Baseline Requirements.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 6960 (June 2013) |
| Status | Proposed Standard |
| Companion updates | RFC 5010 (deprecated), RFC 8954 (nonce), RFC 9760 (signed responses), RFC 6066 (TLS OCSP stapling), RFC 6961 (multi-staple) |
| Companion profile | CA/Browser Forum Baseline Requirements (current version) |
| Source URL | https://www.rfc-editor.org/rfc/rfc6960 |

## Plan

1. Reference RFC 6960 by revision whenever a profile defines revocation-handling policy for X.509 certificates.
2. Specify the OCSP responder model: delegated responder (most common) versus authoritative CA responder, and the constraints on delegated responder signing authority.
3. Specify the request profile: issuer name hash, issuer key hash, serial number, optional nonce, and optional signature.
4. Specify the response profile: response status (successful, malformedRequest, internalError, tryLater, sigRequired, unauthorized), certificate status (good, revoked, unknown), validity interval, responder ID, and signature.
5. Specify when OCSP is mandatory versus optional. The CA/Browser Forum Baseline Requirements impose specific OCSP requirements on public CAs; non-public PKIs should adopt equivalent expectations.
6. Specify the fallback policy when the OCSP responder is unreachable: fail closed (treat as revoked) or fail open (treat as good). Fail-open is acceptable only with documented compensating controls.

## Inputs

- RFC 6960 normative sections: 4 (protocol), 5 (detailed protocol), appendix (certificate profile).
- Issuing CA's OCSP responder URL, signing certificate, and revocation-policy documentation.
- Validation engine configuration: how the engine obtains OCSP responses, caches responses, and handles the fail-open / fail-closed decision.
- Operational constraints: network availability of the OCSP responder, latency budgets, and the procedure for handling persistent responder outages.

## ORCHORDS Profile

ORCHORDS treats RFC 6960 as the canonical OCSP profile. Profiles that govern certificate validation should reference the RFC by revision, identify the responder model (delegated or authoritative), and bind the fail-open / fail-closed policy to a specific decision procedure. A profile that relies on OCSP without specifying the fail policy is incomplete.

OCSP stapling (RFC 6066) and OCSP multi-stapling (RFC 6961) reduce dependence on third-party responders and should be referenced when the validation engine supports them.

## Implementation Notes

- OCSP responses without a nonce are vulnerable to replay attacks. Use nonces (RFC 8954) or signed responses (RFC 9760) when replay protection is required.
- Cached OCSP responses must respect the validity interval; do not treat a cached response as authoritative past its nextUpdate time.
- Authoritative OCSP responses (signed by the issuing CA's private key) are stronger than delegated responses; design the responder key management accordingly.
- Privacy: OCSP queries reveal which sites a client visits. OCSP stapling eliminates third-party queries for stapled responses; privacy-sensitive clients should prefer stapled validation.
- Fail-open OCSP handling is acceptable only when (a) the certificate is short-lived, (b) revocation is independently distributed through another channel, or (c) the validation engine has other compensating controls.

## Companion Documents

- [RFC 5280 X.509 PKI Profile](RFC_5280_X509_PKI_PROFILE.md)
- [RFC 8555 ACME Profile](RFC_8555_ACME_PROFILE.md)
- [CA Browser Forum Baseline Requirements](CA_BROWSER_FORUM_BASELINE_REQUIREMENTS.md)
- [Public Key Infrastructure Operations Response](../playbooks/PUBLIC_KEY_INFRASTRUCTURE_OPERATIONS_RESPONSE.md)
- [Certificate Lifecycle Response](../playbooks/CERTIFICATE_LIFECYCLE_RESPONSE.md)
