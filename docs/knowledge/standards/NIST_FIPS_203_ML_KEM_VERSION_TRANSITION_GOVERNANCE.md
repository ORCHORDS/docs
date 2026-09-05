---
title: "NIST FIPS 203 Module-Lattice-Based Key-Encapsulation Mechanism (ML-KEM) Version Transition Governance"
standard: "NIST FIPS 203"
publisher: "U.S. National Institute of Standards and Technology (NIST)"
category: "standards"
subcategory: "post-quantum-cryptography"
canonical_url: "https://csrc.nist.gov/pubs/fips/203/final"
status: "approved"
classification: "public"
audience: "Cryptographic architects, security engineers, PKI operators, application owners"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# NIST FIPS 203 ML-KEM Version Transition Governance

## Profile

NIST FIPS 203 (Final, August 2024) is the Module-Lattice-Based Key-Encapsulation Mechanism (ML-KEM) standard, derived from CRYSTALS-KYBER. It defines a quantum-resistant key-encapsulation mechanism for protecting symmetric session keys against quantum-capable adversaries, intended for general encryption use cases (TLS, IPSec, hybrid suites). ML-KEM provides three parameter sets: ML-KEM-512, ML-KEM-768, ML-KEM-1024 (with ML-KEM-768 the recommended default).

This standard is part of NIST's post-quantum cryptographic standardization. It pairs with FIPS 204 (ML-DSA signatures), FIPS 205 (SLH-DSA signatures), and SP 800-208 (stateful hash-based signatures). CNSA 2.0 (NSA) requires these algorithms for national-security systems.

## Identifier

| Field | Value |
| --- | --- |
| Standard | FIPS 203 |
| Title | Module-Lattice-Based Key-Encapsulation Mechanism |
| Origin | CRYSTALS-KYBER |
| Final publication | 2024-08-13 |
| Parameter sets | ML-KEM-512, ML-KEM-768 (recommended default), ML-KEM-1024 |
| Companion | FIPS 204, FIPS 205, SP 800-208 |
| Companion RFC | IETF draft-ietf-pquip-pqc-kem ✓ (corresponding IETF profile) |

## Migration Applicability

| Component | Affected |
| --- | --- |
| TLS, mTLS, QUIC | Key exchange in handshake |
| IPSec / IKEv2 | Key exchange |
| SSH | KEX |
| X.509 PKI | Hybrid certificates (e.g., RSA + ML-KEM) |
| Document encryption | Hybrid encryption schemes |
| Code signing | None directly (use FIPS 204 / 205 signatures) |

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Adoption | Plan ML-KEM adoption against the migration timeline; record the parameter set used. |
| Crypto-agility | Implement cryptographic abstraction so ML-KEM can be substituted for elliptic-curve and RSA-based KEMs. |
| Hybrid phasing | During transition, prefer hybrid handshakes (X25519 + ML-KEM) or both ML-KEM and classical via the negotiated suite. |
| Parameter set default | Use ML-KEM-768 for general-purpose sessions; select ML-KEM-1024 for higher-security targets only after validating performance. |
| Library choice | Use FIPS-validated or audited implementations; record product identifier and version. |
| Testing | Validate via test vectors from NIST CAVP; verify interoperability with chosen counterparties before rollout. |

## Implementation Notes

- ML-KEM does not replace FIPS 204 / 205 (signatures) — pair with them where signatures are also required.
- Audit log retrieval and auditability for cryptographic operations may be impacted by ML-KEM adoption; review audit pipelines.
- ML-KEM implementations MAY require additional entropy and constant-time code paths; verify on the chosen platform.
- CNSA 2.0 timelines require ML-KEM (or similar) for national-security systems by 2033; track and act on supplier timelines.
- Pair with key-management guidance from NIST SP 800-57 Part 1 Rev. 5 for hybrid key establishment.

## Companion Documents

- [NIST FIPS 204 ML-DSA Version Guide](NIST_FIPS_204_ML_DSA_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST FIPS 205 SLH-DSA Version Guide](NIST_FIPS_205_SLH_DSA_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST SP 800-208 Quantum-Resistant Hash Signature Version Guide](NIST_SP_800_208_QUANTUM_RESISTANT_VERSION_TRANSITION_GOVERNANCE.md)
- [IETF TLS Hybrid PQ Profile (where published)](IETF_TLS_HYBRID_PQ_PROFILE_VERSION_GUIDE.md)
- [NIST SP 800-57 Key Management](../reference/NIST_SP_800_57_KEY_MANAGEMENT.md)
