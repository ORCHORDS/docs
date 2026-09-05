---
title: "NIST SP 800-52 TLS Guidelines"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-52 Rev. 2 (August 2019); https://csrc.nist.gov/publications/detail/sp/800-52/rev-2/final"
---

# NIST SP 800-52 TLS Guidelines

## Scope

Reference card for NIST Special Publication 800-52 Revision 2, *Guidelines for the Selection, Configuration, and Use of TLS Implementations* (August 2019). The publication is the primary US-government guidance for selecting and configuring TLS. Profiles that govern TLS configuration for federal systems should reference SP 800-52 Rev. 2 by version, and profiles that govern private-sector TLS should reference it as a recognized baseline.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | NIST SP 800-52 Rev. 2 (August 2019) |
| Status | Final; current edition (Rev. 3 in draft as of September 2026) |
| Supersedes | SP 800-52 Rev. 1 (April 2014) |
| Companion artifacts | SP 800-131A (algorithm assurance), SP 800-57 (key management), RFC 8446 (TLS 1.3), CA/Browser Forum Baseline Requirements |
| Source URL | https://csrc.nist.gov/publications/detail/sp/800-52/rev-2/final |

## Plan

1. Reference SP 800-52 Rev. 2 by version whenever a profile governs TLS configuration.
2. Use the SP 800-52 minimum cipher suite recommendation as the baseline and adopt the operating-mode-specific recommendations (server, mutual TLS, client).
3. Track the SP 800-52 Rev. 3 draft and identify the revisions (TLS 1.3 migration, quantum-safe hybrid profiles, certificate lifecycle).
4. Bind TLS configuration to SP 800-131A algorithm assurance labels.
5. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- SP 800-52 Rev. 2 normative sections: 3 (TLS basics), 4 (server configuration), 5 (mutual TLS), 6 (client), 7 (operational considerations).
- SP 800-131A algorithm assurance labels.
- Internal TLS configuration inventory: supported versions, cipher suites, certificates, client authentication.
- CA/Browser Forum Baseline Requirements (current version).

## ORCHORDS Profile

ORCHORDS treats SP 800-52 Rev. 2 as the canonical reference for TLS configuration in the US federal sector and as a recognized baseline for private-sector profiles. Profiles that reference TLS should cite the standard by version, identify the operating modes in scope, and bind to the CA/Browser Forum Baseline Requirements where applicable.

A profile that references "TLS" without binding to a recognized standard (SP 800-52, RFC 8446, CA/Browser Forum) is non-conformant.

## Implementation Notes

- The SP 800-52 Rev. 2 baseline enables TLS 1.2 and TLS 1.3 with a constrained set of cipher suites; older versions (SSL 3.0, TLS 1.0, TLS 1.1) are disallowed.
- Mutual TLS (mTLS) profiles per SP 800-52 §5 should specify the certificate authority trust model and the revocation checking policy.
- Client configuration per SP 800-52 §6 should bind to the broader application-policy rather than to TLS alone.
- Operational considerations per SP 800-52 §7 cover logging, session resumption, session tickets, OCSP stapling, and the certificate-transparency expectation.

## Companion Documents

- [NIST SP 800-57 Key Management](NIST_SP_800_57_KEY_MANAGEMENT.md)
- [RFC 5280 X.509 PKI Profile](RFC_5280_X509_PKI_PROFILE.md)
- [RFC 8555 ACME Profile](RFC_8555_ACME_PROFILE.md)
- [CA Browser Forum Baseline Requirements](CA_BROWSER_FORUM_BASELINE_REQUIREMENTS.md)
- [IETF TLS Hybrid PQ Profile Version Guide](IETF_TLS_HYBRID_PQ_PROFILE_VERSION_GUIDE.md)
- [Public Key Infrastructure Operations Response](../playbooks/PUBLIC_KEY_INFRASTRUCTURE_OPERATIONS_RESPONSE.md)
- [Certificate Lifecycle Response](../playbooks/CERTIFICATE_LIFECYCLE_RESPONSE.md)
