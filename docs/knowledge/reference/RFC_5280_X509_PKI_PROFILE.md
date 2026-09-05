---
title: "RFC 5280 X.509 PKI Profile"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 5280 (May 2008); https://www.rfc-editor.org/rfc/rfc5280"
---

# RFC 5280 X.509 PKI Profile

## Scope

Reference card for IETF RFC 5280, *Internet X.509 Public Key Infrastructure Certificate and Certificate Revocation List (CRL) Profile* (May 2008). RFC 5280 is the canonical profile of X.509 v3 certificates and X.509 v2 CRLs for use in the Internet PKI. Profiles governing certificate issuance, validation, and revocation should reference RFC 5280 by revision, supplemented by RFC 6818 (updates), RFC 8398, RFC 8399, RFC 9162 (transparency), and the CA/Browser Forum Baseline Requirements.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 5280 (May 2008) |
| Status | Proposed Standard |
| Companion updates | RFC 6818 (Jan 2013), RFC 8398 (May 2018), RFC 8399 (May 2018), RFC 9162 (Aug 2021), RFC 9598 (June 2024 — MRT profile) |
| Companion profile | CA/Browser Forum Baseline Requirements (current version) |
| Source URL | https://www.rfc-editor.org/rfc/rfc5280 |

## Plan

1. Reference RFC 5280 by revision whenever a profile defines certificate issuance, validation, or revocation policy.
2. Specify the certificate fields that the profile constrains (version, serialNumber, signature, issuer, validity, subject, subjectPublicKeyInfo, extensions) and the constraints on each.
3. Specify the extension profile: key usage, extended key usage, basic constraints, name constraints, certificate policies, policy constraints, policy mappings, inhibit anyPolicy, subject alternative name, issuer alternative name, and CRL distribution points.
4. Specify the validation algorithm: build a certification path from trust anchor to target certificate, validate signatures, check validity dates, check revocation status using CRLs, OCSP, or both.
5. Specify the revocation-handling policy: which mechanism (CRL, OCSP, OCSP stapling, OCSP multi-staple, OCSP archive cutoff) is required for each certificate class.
6. Maintain conformance with the current CA/Browser Forum Baseline Requirements; treat them as a profile constraint on top of RFC 5280.

## Inputs

- RFC 5280 normative sections: 4.1 (certificate fields), 4.2 (extensions), 5 (operational protocols), 6 (path validation).
- CA/Browser Forum Baseline Requirements (current published version).
- Internal PKI issuance policy, profile constraints, and validation engine configuration.
- Trust anchor inventory and the procedure for adding or removing trust anchors.

## ORCHORDS Profile

ORCHORDS treats RFC 5280 as the canonical X.509 certificate profile for Internet PKI. Profiles that govern internal PKI should reference RFC 5280 by revision and explicitly identify any deviation (for example, internal names, internal policy OIDs). Internal PKIs that issue certificates to public-trust paths must additionally conform to the CA/Browser Forum Baseline Requirements.

Profiles that govern CT (Certificate Transparency) compliance should bind to RFC 9162 and the relevant CT log policies, not to RFC 5280 alone.

## Implementation Notes

- Path validation per RFC 5280 §6 must include signature verification, validity-period check, revocation-status check, and policy enforcement.
- Self-signed certificates used as trust anchors must be installed with intent; an accidentally trusted self-signed certificate is a critical security defect.
- Name constraints should be used to limit a CA's issuance scope to authorized name spaces; the absence of name constraints is a known hardening gap.
- OCSP stapling (RFC 6066, RFC 6961) reduces reliance on third-party OCSP responders and improves privacy.
- Algorithm agility is governed by RFC 7696 (elliptic curve) and the post-quantum hybrid profile work (RFC 9798 et al.).

## Companion Documents

- [RFC 6960 OCSP Profile](RFC_6960_OCSP_PROFILE.md)
- [RFC 8555 ACME Profile](RFC_8555_ACME_PROFILE.md)
- [CA Browser Forum Baseline Requirements](CA_BROWSER_FORUM_BASELINE_REQUIREMENTS.md)
- [NIST SP 800-57 Key Management](NIST_SP_800_57_KEY_MANAGEMENT.md)
- [Public Key Infrastructure Operations Response](../playbooks/PUBLIC_KEY_INFRASTRUCTURE_OPERATIONS_RESPONSE.md)
- [Certificate Lifecycle Response](../playbooks/CERTIFICATE_LIFECYCLE_RESPONSE.md)
