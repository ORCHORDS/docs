---
title: "NIST SP 800-57 Key Management Reference"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-57 Part 1 Rev. 5 (May 2020); https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final"
---

# NIST SP 800-57 Key Management Reference

## Scope

Reference card for NIST Special Publication 800-57 *Recommendation for Key Management*. The publication is published in three parts: Part 1 Rev. 5 (May 2020) covers general key-management concepts and cryptographic-period policy; Part 2 Rev. 1 (June 2019) covers organizational key-management practices; Part 3 Rev. 1 (January 2015) covers application-specific key management. Profiles that govern symmetric, asymmetric, or key-derivation material should reference the relevant part by revision.

## Identifier table

| Field | Value |
| --- | --- |
| Primary documents | SP 800-57 Part 1 Rev. 5 (general), Part 2 Rev. 1 (organizational), Part 3 Rev. 1 (application-specific) |
| Status | Final (Part 1 Rev. 5: May 2020; Part 2 Rev. 1: June 2019; Part 3 Rev. 1: January 2015) |
| Supersedes | Part 1 Rev. 4 (January 2016), Part 2 (June 2005), Part 3 (December 2009) |
| Companion artifacts | SP 800-131A (algorithm assurance), SP 800-56A/B/C (key establishment), FIPS 140-3 (module validation), FIPS 186-5 (signatures), FIPS 203/204/205 (post-quantum) |
| Source URL | https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final |

## Plan

1. Reference the relevant SP 800-57 part and revision whenever a profile governs cryptographic key material.
2. Identify the cryptographic-key types in scope (symmetric data-encryption, key-wrapping, authentication; public signature, key-establishment; ephemeral; root and subordinate key-management keys; authorization keys) and assign the originator-usage, recipient-usage, and cryptoperiod limits.
3. Apply algorithm assurance labels (deprecated, restricted, acceptable, legacy) from SP 800-131A to every operational algorithm.
4. Map lifecycle stages (generation, distribution, storage, use, change, update, archival, escrow, recovery, suspension, deactivation, destruction, revocation, compromise) to specific controls, event records, and authorized roles.
5. Track cryptoperiod boundaries in the same state machine that enforces key state transitions; calendar reminders alone are not sufficient.
6. Where quantum risk is relevant, label each algorithm as quantum-vulnerable or quantum-resistant and document the planned transition to post-quantum replacements (FIPS 203, 204, 205).

## Inputs

- SP 800-57 Part 1 Rev. 5 practice statements with key-type definitions, cryptoperiod tables, and lifecycle state definitions.
- Algorithm-specific Special Publications (SP 800-56A, SP 800-56B, SP 800-131A, SP 800-208) and the current FIPS 186-5 signature specification.
- Operational key inventories with algorithm, bit length, state, cryptoperiod, custodian, and revocation status.
- Key-management organizational procedures (custodian separation, audit role, compromise handling).

## ORCHORDS Profile

ORCHORDS treats SP 800-57 Part 1 Rev. 5 as the canonical reference for key-management concepts and cryptographic-period policy. Profiles should cite Part 1 by revision and pull lifecycle expectations into their own governance procedures rather than restating the Part 1 text. The ORCHORDS reference card for Part 1 Rev. 5 is `NIST_SP_800_57_PART_1_R5_KEY_MANAGEMENT_VERSION_GOVERNANCE.md`; this card binds to it.

Profiles that govern post-quantum transitions should reference FIPS 203, 204, and 205 alongside SP 800-57 and document the inventory of pre-quantum keys that require replacement.

## Implementation Notes

- SP 800-57 does not specify algorithms. Algorithm-specific guidance is in SP 800-131A, SP 800-56A/B/C, and the FIPS publications.
- A claim of "FIPS-validated" without an algorithm assurance label is ambiguous. Pair FIPS 140-3 module validation with the SP 800-131A algorithm label.
- Cryptoperiod expiration is enforced through state transitions, not by waiting for the algorithm to fail.
- Symmetric key zeroization is a recorded event; do not infer zeroization from file deletion or session termination.
- Key compromise handling procedures should name the approver, the notification timeline, and the recovery or replacement path.

## Companion Documents

- [NIST SP 800-57 Part 1 Rev. 5 Key Management Version Governance](NIST_SP_800_57_PART_1_R5_KEY_MANAGEMENT_VERSION_GOVERNANCE.md)
- [NIST SP 800-208 Quantum-Resistant Version Transition Governance](../standards/NIST_SP_800_208_QUANTUM_RESISTANT_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST FIPS 203 ML-KEM Version Transition Governance](../standards/NIST_FIPS_203_ML_KEM_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST FIPS 204 ML-DSA Version Transition Governance](../standards/NIST_FIPS_204_ML_DSA_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST FIPS 205 SLH-DSA Version Transition Governance](../standards/NIST_FIPS_205_SLH_DSA_VERSION_TRANSITION_GOVERNANCE.md)
- [Public Key Infrastructure Operations Response](../playbooks/PUBLIC_KEY_INFRASTRUCTURE_OPERATIONS_RESPONSE.md)
- [Certificate Lifecycle Response](../playbooks/CERTIFICATE_LIFECYCLE_RESPONSE.md)
