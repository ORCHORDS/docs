---
title: "NIST SP 800-208 LMS / XMSS Stateful Hash-Based Signature Version Transition Governance"
standard: "NIST SP 800-208"
publisher: "U.S. National Institute of Standards and Technology (NIST)"
category: "standards"
subcategory: "post-quantum-cryptography"
canonical_url: "https://csrc.nist.gov/pubs/sp/800/208/final"
status: "approved"
classification: "public"
audience: "Firmware signing teams, constrained-device cryptography, long-life signature operators"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# NIST SP 800-208 LMS / XMSS Version Transition Governance

## Profile

NIST SP 800-208 (Final, October 2020) is the recommendation for stateful hash-based signature schemes, specifically the Leighton-Micali Signature (LMS) and eXtended Merkle Signature Scheme (XMSS). The schemes are quantum-resistant, based on the security of cryptographic hash functions, with small signature outputs and small keys — well-suited to constrained devices and firmware signing.

Both schemes are *stateful*: each private key MUST NOT be used to sign more than a fixed number of messages; each signature MUST delete the used key material. State-management errors compromise the security of the entire signing key. This is the central operational risk addressed by the standard.

## Identifier

| Field | Value |
| --- | --- |
| Standard | SP 800-208 |
| Title | Recommendation for Stateful Hash-Based Signature Schemes |
| Final publication | 2020-10 |
| Schemes | LMS, HSS, XMSS, XMSS^MT |
| Companion | FIPS 205 (SLH-DSA — stateless fallback), FIPS 204 (ML-DSA — lattice alternative) |
| Cross-reference | IETF RFC 8554 (LMS), RFC 8391 (XMSS) |

## Migration Applicability

| Component | Affected |
| --- | --- |
| Firmware signing | LMS / HSS for constrained hardware roots-of-trust |
| Software update signatures | XMSS / XMSS^MT where state can be reliably persisted |
| Root-of-trust signing | Firmware roots with on-device state |
| Vehicular and industrial | Long-life deployments where quantum resistance is required |

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Adoption | Use LMS / XMSS for firmware signing in devices that can persist state reliably. |
| State management | Treat state loss as catastrophic for the signing key; design for persistent, atomic, audit-logged state advancement. |
| One-shot use | Document the maximum number of signatures per key; rotate keys before exhaustion. |
| Backup and recovery | Implement secure state backup that preserves auditability of state advancement; verify recovery on exercise. |
| Library choice | Use vetted implementations that enforce one-time state advance; record product identifier and version. |
| Compromise response | Treat any state-loss or unauthorized state advance as compromise; rotate the key family immediately. |
| Migration out | Plan migration to FIPS 205 (SLH-DSA) for stateless or FIPS 204 (ML-DSA) for lattice-based signatures where possible. |

## Implementation Notes

- LMS / XMSS are the only post-quantum signature schemes approved by NIST with statefulness; operationally, they are not interchangeable with ML-DSA or SLH-DSA without explicit lifecycle planning.
- State management errors yield catastrophic compromise; cryptographic correctness does not save the scheme.
- Common implementations fail closed on duplicate state; verify and exercise failure modes before deployment.
- Pair with IETF RFC 8554 (LMS) and RFC 8391 (XMSS) for protocol-level details and parameter identifiers.

## Companion Documents

- [NIST FIPS 205 SLH-DSA Version Guide](NIST_FIPS_205_SLH_DSA_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST FIPS 204 ML-DSA Version Guide](NIST_FIPS_204_ML_DSA_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST SSDF SP 800-218](../reference/NIST_SSDF_SP_800_218.md)
- [IETF RFC 8554 LMS Profile](../reference/RFC_8554_LMS_PROFILE.md)
- [IETF RFC 8391 XMSS Profile](../reference/RFC_8391_XMSS_PROFILE.md)
