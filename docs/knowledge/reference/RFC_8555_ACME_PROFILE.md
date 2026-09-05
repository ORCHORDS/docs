---
title: "RFC 8555 ACME Profile"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 8555 (March 2019); https://www.rfc-editor.org/rfc/rfc8555"
---

# RFC 8555 ACME Profile

## Scope

Reference card for IETF RFC 8555, *Automatic Certificate Management Environment (ACME)* (March 2019). ACME defines a protocol for automatic certificate enrollment, renewal, and revocation. Profiles governing automated certificate issuance should reference RFC 8555 by revision, supplemented by RFC 8738 (TLS-ALPN-01 challenge for TLS-only issuance), RFC 9773 (TLS-ALPN-01 update), the current CA/Browser Forum Baseline Requirements, and the ACME server implementations deployed by the issuing CA.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 8555 (March 2019) |
| Status | Proposed Standard |
| Companion updates | RFC 8738 (TLS-ALPN-01), RFC 9773 (TLS-ALPN-01 update), draft-ietf-acme-authority-token etc. |
| Companion profile | CA/Browser Forum Baseline Requirements (current version) |
| Source URL | https://www.rfc-editor.org/rfc/rfc8555 |

## Plan

1. Reference RFC 8555 by revision whenever a profile defines automated certificate issuance, renewal, or revocation.
2. Specify the challenge types supported by the issuing CA (HTTP-01, DNS-01, TLS-ALPN-01) and the constraints on each challenge (for example DNS-01 requires programmatic access to the DNS zone).
3. Specify the account model: a single account per registrant, with an account key used for JWS-signed requests, and account key rollover policy.
4. Specify the certificate profile: identifier types (DNS, IP, wildcard), validity period expectations, and any constraints on the certificate profile imposed by the issuing CA.
5. Specify the renewal cadence and the expected number of renewals per certificate (RFC 8555 recommends renewing at approximately 2/3 of the certificate lifetime).
6. Specify the revocation flow: who can revoke, how revocation is authorized, and the expected acknowledgement from the issuing CA.

## Inputs

- RFC 8555 normative sections: 6 (ACME workflow), 7 (directory), 8 (objects), 9 (challenges), 10 (authorization and issuance).
- Issuing CA's ACME server URL, directory metadata, supported challenge types, supported identifier types, and rate-limit policy.
- Domain control validation: which challenges are available per domain and how the validating infrastructure (DNS provider, HTTP origin) authorizes the challenge response.
- Internal certificate inventory and the procedure for tracking issuance and renewal events.

## ORCHORDS Profile

ORCHORDS treats RFC 8555 as the canonical protocol for automated certificate issuance. Profiles should reference the RFC by revision, identify the supported challenge types, and bind the challenge response to a specific infrastructure (DNS provider, origin server, ALPN-aware reverse proxy). The CA/Browser Forum Baseline Requirements apply on top of RFC 8555 and should be cited separately.

Profiles that integrate DNS-01 challenges should bind the DNS provider API to the challenge handling procedure; a generic DNS-01 challenge without provider binding is incomplete.

## Implementation Notes

- ACME account keys must be protected at the level of any signing key that controls issuance; treat the account key as a high-value secret.
- Wildcard issuance requires DNS-01 challenge per RFC 8555 §6.6.4; HTTP-01 cannot issue wildcards.
- ACME directory metadata (terms-of-service, external account binding, profiles) may impose additional requirements beyond RFC 8555; check the issuing CA's directory document.
- Revocation via ACME requires the account key (or a delegated signing key), not the certificate; design the revocation procedure around account-level authorization.
- Renewal cadence: ACME servers are typically configured to refuse early renewal outside an acceptable window. Align the internal scheduler with the server's window.
- Use CAA records (RFC 8659) to constrain the issuing CAs authorized for a domain.

## Companion Documents

- [RFC 5280 X.509 PKI Profile](RFC_5280_X509_PKI_PROFILE.md)
- [RFC 6960 OCSP Profile](RFC_6960_OCSP_PROFILE.md)
- [CA Browser Forum Baseline Requirements](CA_BROWSER_FORUM_BASELINE_REQUIREMENTS.md)
- [NIST SP 800-52 TLS Guidelines](NIST_SP_800_52_TLS_GUIDELINES.md)
- [Certificate Lifecycle Response](../playbooks/CERTIFICATE_LIFECYCLE_RESPONSE.md)
