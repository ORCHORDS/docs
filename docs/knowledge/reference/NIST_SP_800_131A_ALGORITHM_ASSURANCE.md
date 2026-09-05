---
title: "NIST SP 800-131A Cryptographic Algorithm Assurance Reference Card"
standard: "NIST SP 800-131A Rev. 2"
publisher: "National Institute of Standards and Technology (NIST)"
category: "reference"
subcategory: "cryptographic-assurance"
canonical_url: "https://csrc.nist.gov/pubs/sp/800/131/a/r2/final"
status: "approved"
classification: "public"
audience: "Cryptographic implementers, security architects, compliance engineers"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
---

# NIST SP 800-131A Cryptographic Algorithm Assurance Reference Card

## Profile

NIST SP 800-131A Rev. 2, *Transitioning the Use of Cryptographic Algorithms and Key Lengths* (March 2019), provides the assurance labels used by every cryptographic profile: **acceptable**, **deprecated**, **restricted**, and **legacy**. SP 800-131A is the companion to SP 800-57 Part 1 Rev. 5 (Key Management) and the algorithm-specific Special Publications (SP 800-56A, SP 800-56B, SP 800-131A itself, FIPS 186-5, FIPS 203, FIPS 204, FIPS 205). Profiles that govern cryptography, key management, TLS configuration, or PKI operations should cite SP 800-131A Rev. 2 explicitly and bind to SP 800-57 Part 1 Rev. 5, FIPS 140-3, and SP 800-52 (TLS guidelines).

## Identifier

| Field | Value |
| --- | --- |
| Primary document | NIST SP 800-131A Rev. 2, *Transitioning the Use of Cryptographic Algorithms and Key Lengths* |
| Publisher | NIST Computer Security Resource Center (CSRC) |
| Status | Final publication; periodic updates expected as new algorithms (for example, ML-KEM, ML-DSA, SLH-DSA) transition through the assurance labels |
| Companion artifacts | SP 800-57 Part 1 Rev. 5, FIPS 140-3, FIPS 186-5, FIPS 203, FIPS 204, FIPS 205, SP 800-52 |
| Source URL | https://csrc.nist.gov/pubs/sp/800/131/a/r2/final |

## Current context and source status

SP 800-131A Rev. 2 was published in March 2019. No successor revision is published as of September 5, 2026, although the document will be updated to reflect the post-quantum algorithms standardized in FIPS 203 (ML-KEM), FIPS 204 (ML-DSA), and FIPS 205 (SLH-DSA), and the deprecation of additional legacy algorithms.

## Assurance labels

| Label | Meaning | Example |
| --- | --- | --- |
| Acceptable | The algorithm and key length provide adequate security and may be used. | AES-128/192/256, SHA-256/384/512, ECDSA P-256/P-384/P-521 with SHA-256/384, RSA 2048+ |
| Deprecated | The algorithm may be used but the user must accept some risk; transition plans should be in place. | RSA 1024 (signature verification only beyond 2023) |
| Restricted | The algorithm may be used only under specific constraints (for example, legacy interoperability). | RSA 1024, ECDSA with SHA-1 |
| Legacy | The algorithm is no longer trusted; only allowed for verifying old signatures or decrypting old ciphertext. | RSA 1024 (signing), SHA-1 (signature generation), DES, 3DES |

## Governance pattern

1. Cite SP 800-131A Rev. 2 in cryptographic profiles, key-management policies, and algorithm inventories.
2. Inventory every cryptographic algorithm in use and assign the assurance label.
3. Plan transitions from deprecated, restricted, and legacy algorithms; document transition timelines with approver, scope, expiration, and compensating controls.
4. Bind to SP 800-57 Part 1 Rev. 5 for the key-management lifecycle.
5. Bind to FIPS 140-3 for module validation.
6. Bind to FIPS 186-5 for digital signature algorithm parameters.
7. Bind to FIPS 203 (ML-KEM), FIPS 204 (ML-DSA), and FIPS 205 (SLH-DSA) for post-quantum algorithm parameters.
8. Bind to SP 800-52 for TLS implementation guidance.
9. Re-evaluate algorithm assurance annually and after NIST announcements.
10. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Validation and evidence

Compliance evidence includes:

- Cryptographic algorithm inventory with assurance label, key length, key-management policy reference, and owner.
- Transition plan for any deprecated, restricted, or legacy algorithm in use.
- Key-management policy that cites SP 800-57 Part 1 Rev. 5.
- Module validation certificates (FIPS 140-3) for the cryptographic modules in production.
- Annual re-evaluation record of the algorithm inventory.

Evidence that omits the assurance label, the transition plan, or the FIPS 140-3 module validation does not establish SP 800-131A Rev. 2 conformance.

## Companion Documents

- [NIST SP 800-57 Part 1 Rev. 5 Key Management Version Governance](../reference/NIST_SP_800_57_KEY_MANAGEMENT_VERSION_GOVERNANCE.md)
- [NIST SP 800-52 TLS Guidelines](NIST_SP_800_52_TLS_GUIDELINES.md)
- [NIST FIPS 203 ML-KEM Version Transition Governance](../standards/NIST_FIPS_203_ML_KEM_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST FIPS 205 SLH-DSA Version Transition Governance](../standards/NIST_FIPS_205_SLH_DSA_VERSION_TRANSITION_GOVERNANCE.md)
- [RFC 5280 X.509 PKI Profile](RFC_5280_X509_PKI_PROFILE.md)
- [RFC 6960 OCSP Profile](RFC_6960_OCSP_PROFILE.md)
- [RFC 8555 ACME Profile](RFC_8555_ACME_PROFILE.md)
- [CA/Browser Forum Baseline Requirements](CA_BROWSER_FORUM_BASELINE_REQUIREMENTS.md)
- [IETF TLS Hybrid PQ Profile Version Guide](IETF_TLS_HYBRID_PQ_PROFILE_VERSION_GUIDE.md)
