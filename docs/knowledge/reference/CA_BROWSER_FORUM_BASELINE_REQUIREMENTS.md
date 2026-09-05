---
title: "CA Browser Forum Baseline Requirements"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "CA/Browser Forum Baseline Requirements for TLS Server Certificates (current published version); https://cabforum.org/baseline-requirements-documents/"
---

# CA Browser Forum Baseline Requirements

## Scope

Reference card for the CA/Browser Forum *Baseline Requirements for the Issuance and Management of Publicly-Trusted TLS Server Certificates* (current published version). The Baseline Requirements are the de facto public-trust PKI standard adopted by root programs operated by Apple, Google, Microsoft, and Mozilla. Profiles that govern public-trust TLS certificates should reference the current version and the companion Extended Validation, S/MIME, and Code-Signing Baseline Requirements where applicable.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | CA/Browser Forum Baseline Requirements for TLS Server Certificates (current published version) |
| Status | Continuously maintained by the CA/Browser Forum Server Certificate Working Group |
| Companion artifacts | EV Guidelines, S/MIME Baseline Requirements, Code-Signing Baseline Requirements, Network Security Standard, CCADB Policy |
| Source URL | https://cabforum.org/baseline-requirements-documents/ |

## Plan

1. Reference the CA/Browser Forum Baseline Requirements (BR) by current version whenever a profile governs public-trust TLS certificates.
2. Apply the BR scope: domain validation, organization validation, individual validation, certificate profile, certificate lifecycle, revocation, audit, network security, and the legal framework.
3. Apply the BR certificate profile (per RFC 5280 baseline) with the additional BR constraints (for example the wildcard scope, the SAN constraints, the Certificate Transparency expectation).
4. Apply the BR validation rules: domain validation methods (per BR §3.2.2.4), organization validation (per BR §3.2.2.1), and individual validation (per BR §3.2.3).
5. Apply the BR revocation rules: revocation triggers, revocation timelines, OCSP and CRL expectations, and the OCSP archive-cutoff expectation.
6. Apply the BR network and operational security rules: logging, monitoring, incident handling, root-key custody, and the audit expectations.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule; deviations from BR are typically not permitted for public-trust PKI.

## Inputs

- BR normative sections by topic (validation, issuance, profile, revocation, network security, audit).
- CA/Browser Forum Server Certificate Working Group ballots and decisions.
- Internal CA policy, certificate inventory, and audit records.

## ORCHORDS Profile

ORCHORDS treats the CA/Browser Forum Baseline Requirements as the binding standard for public-trust TLS certificates. Profiles that govern public-trust TLS should reference the current BR version, identify the validation methods in scope, and bind to RFC 5280, RFC 6960, RFC 8555, RFC 9162 (CT), NIST SP 800-52, and the current NIST algorithm-assurance labels.

Internal (private-trust) PKI may reference BR as a recognized baseline but is not bound by it; the internal PKI policy should identify the BR-inspired controls it adopts and the deviations.

## Implementation Notes

- BR is updated frequently via Forum ballots; profiles should reference the current version and identify the version date.
- The validation methods in BR §3.2.2.4 have evolved; the current Forum expectations are documented by version and ballot.
- Certificate Transparency (CT) is mandatory for public-trust certificates per the root programs; profiles should bind to RFC 9162 and the relevant CT log policies.
- OCSP must include archive-cutoff (RFC 6960) for long-term validation profiles.
- The BR network and operational security expectations are audited; the audit findings drive certificate-program decisions at the root programs.

## Companion Documents

- [RFC 5280 X.509 PKI Profile](RFC_5280_X509_PKI_PROFILE.md)
- [RFC 6960 OCSP Profile](RFC_6960_OCSP_PROFILE.md)
- [RFC 8555 ACME Profile](RFC_8555_ACME_PROFILE.md)
- [NIST SP 800-52 TLS Guidelines](NIST_SP_800_52_TLS_GUIDELINES.md)
- [Public Key Infrastructure Operations Response](../playbooks/PUBLIC_KEY_INFRASTRUCTURE_OPERATIONS_RESPONSE.md)
- [Certificate Lifecycle Response](../playbooks/CERTIFICATE_LIFECYCLE_RESPONSE.md)
