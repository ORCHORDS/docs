---
title: "NIST FIPS 204 Module-Lattice-Based Digital Signature Standard (ML-DSA) Version Transition Governance"
standard: "NIST FIPS 204"
publisher: "U.S. National Institute of Standards and Technology (NIST)"
category: "standards"
subcategory: "post-quantum-cryptography"
canonical_url: "https://csrc.nist.gov/pubs/fips/204/final"
status: "approved"
classification: "public"
audience: "Cryptographic architects, PKI operators, code-signing operators"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# NIST FIPS 204 ML-DSA Version Transition Governance

## Profile

NIST FIPS 204 (Final, August 2024) is the Module-Lattice-Based Digital Signature Algorithm (ML-DSA) standard, derived from CRYSTALS-Dilithium. It defines a quantum-resistant digital signature for general-purpose integrity and authentication. ML-DSA provides three parameter sets: ML-DSA-44, ML-DSA-65 (recommended default), ML-DSA-87, balancing signature size and security level.

FIPS 204 is part of NIST's post-quantum signature suite. It pairs with FIPS 203 (ML-KEM for key encapsulation), FIPS 205 (SLH-DSA for hash-based signatures), and SP 800-208 (LMS and XMSS, stateful hash-based signatures). CNSA 2.0 requires ML-DSA or SLH-DSA for national-security signatures.

## Identifier

| Field | Value |
| --- | --- |
| Standard | FIPS 204 |
| Title | Module-Lattice-Based Digital Signature Standard |
| Origin | CRYSTALS-Dilithium |
| Final publication | 2024-08-13 |
| Parameter sets | ML-DSA-44, ML-DSA-65 (recommended default), ML-DSA-87 |
| Companion | FIPS 203, FIPS 205, SP 800-208 |
| Companion RFC | IETF drafts for ML-DSA signatures in CMS, JOSE, PKIX |

## Migration Applicability

| Component | Affected |
| --- | --- |
| Code signing | ML-DSA signatures for binary signing |
| Document signing (PDF, XML) | ML-DSA in CMS SignedData |
| Authentication tokens | ML-DSA-based JWT / JWS |
| X.509 PKI | Hybrid certificates with classical + ML-DSA signatures |
| Software updates | ML-DSA signature validation |
| Attestation | ML-DSA-based remote attestation |

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Adoption | Record ML-DSA usage and the parameter set in cryptographic inventory; mark components that use ML-DSA. |
| Crypto-agility | Abstract signing keys so ML-DSA can be substituted for RSA/ECDSA without re-wiring. |
| Hybrid signatures | During transition, prefer hybrid certificates that combine classical and post-quantum signatures. |
| Parameter set default | Use ML-DSA-65 for general-purpose signing; select ML-DSA-87 for high-security targets. |
| Key custody | Apply protective controls equivalent to those used for classical signature keys, with attention to state-loss risk; ML-DSA is stateless but key compromise has the same impact. |
| Library choice | Use FIPS-validated or audited implementations; record product identifier and version. |
| Validation | Verify with NIST CAVP test vectors; verify interoperability with consuming systems and trust stores. |

## Implementation Notes

- ML-DSA signatures are not compatible with classical verification paths; update verification infrastructure.
- Migration of trust stores (operating systems, browsers, mobile platforms) is necessary; some platforms need explicit enrollment of ML-DSA roots.
- CNSA 2.0 timelines target signing-migration by 2033 for software/firmware signing; non-signature software signing at shorter horizon.
- Pair with FIPS 205 (SLH-DSA) where stateful or stateless-hash-based signatures are required as a fallback.

## Companion Documents

- [NIST FIPS 203 ML-KEM Version Guide](NIST_FIPS_203_ML_KEM_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST FIPS 205 SLH-DSA Version Guide](NIST_FIPS_205_SLH_DSA_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST SP 800-208 LMS/XMSS Version Guide](NIST_SP_800_208_QUANTUM_RESISTANT_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST SP 800-57 Key Management](../reference/NIST_SP_800_57_KEY_MANAGEMENT.md)
- [NIST SSDF SP 800-218](../reference/NIST_SSDF_SP_800_218.md)
