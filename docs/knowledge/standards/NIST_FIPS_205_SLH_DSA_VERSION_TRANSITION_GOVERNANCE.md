---
title: "NIST FIPS 205 Stateless Hash-Based Digital Signature Standard (SLH-DSA) Version Transition Governance"
standard: "NIST FIPS 205"
publisher: "U.S. National Institute of Standards and Technology (NIST)"
category: "standards"
subcategory: "post-quantum-cryptography"
canonical_url: "https://csrc.nist.gov/pubs/fips/205/final"
status: "approved"
classification: "public"
audience: "Cryptographic architects, firmware signing, long-life signature operators"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# NIST FIPS 205 SLH-DSA Version Transition Governance

## Profile

NIST FIPS 205 (Final, August 2024) is the Stateless Hash-Based Digital Signature Algorithm (SLH-DSA) standard, derived from SPHINCS+. SLH-DSA provides a quantum-resistant signature based only on the security of hash functions, with no number-theoretic assumptions. Twelve parameter sets are defined across SHA-2 (SLH-DSA-SHA2-*) and SHAKE (SLH-DSA-SHAKE-*) instantiations at four security levels (128, 192, 256 bits).

SLH-DSA is the conservative fallback when lattice-based signatures (ML-DSA) are not appropriate, particularly for firmware signing, long-lived documents, and auditability-of-assumptions requirements. It pairs with FIPS 204 (ML-DSA) and SP 800-208 (stateful hash-based signatures LMS/XMSS, for constrained environments).

## Identifier

| Field | Value |
| --- | --- |
| Standard | FIPS 205 |
| Title | Stateless Hash-Based Digital Signature Standard |
| Origin | SPHINCS+ |
| Final publication | 2024-08-13 |
| Parameter sets | 12 sets: SLH-DSA-{SHA2, SHAKE}-f, s, h — 128/192/256 bits fast/small/tiny |
| Companion | FIPS 203, FIPS 204, SP 800-208 |
| Underlying primitive | Hash function (SHA-2, SHAKE) |

## Migration Applicability

| Component | Affected |
| --- | --- |
| Firmware and device signing | SLH-DSA-128s as a fallback where ML-DSA is not available |
| Long-life document signing | SLH-DSA-256f when high-assurance is required |
| Root CA certificates | Conservative choice for long-life roots |
| Audit-dominant signatures | When security-proof minimalism is desired |
| Stateless requirements | Where stateful hash-based (LMS/XMSS) signatures cannot be used |

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Adoption | Use SLH-DSA as the conservative signature choice when number-theoretic assumptions are unacceptable. |
| Parameter set default | Use SLH-DSA-128s for constrained devices; use SLH-DSA-256f for higher assurance and where signature size is tolerable. |
| Signature size | Plan for larger signature sizes (kilobytes), which affect transport and storage. |
| Verification throughput | Validate verification performance with chosen library and hardware. |
| Library choice | Use audited implementations; record product identifier and version. |
| Migration triggers | Adopt SLH-DSA when regulatory or audit-imposed requirements demand hash-only cryptographic assumptions. |

## Implementation Notes

- SLH-DSA is stateless; no state-loss risk, unlike LMS/XMSS.
- SLH-DSA signatures are larger than ML-DSA; budget for bandwidth and storage.
- SLH-DSA is suitable for firmware and software signing where verification cost is acceptable.
- Pair with SP 800-208 (LMS/XMSS) for constrained environments where state can be reliably managed.

## Companion Documents

- [NIST FIPS 203 ML-KEM Version Guide](NIST_FIPS_203_ML_KEM_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST FIPS 204 ML-DSA Version Guide](NIST_FIPS_204_ML_DSA_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST SP 800-208 LMS/XMSS Version Guide](NIST_SP_800_208_QUANTUM_RESISTANT_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST SSDF SP 800-218](NIST_SSDF_SP_800_218.md)
- [Firmware Integrity Verification Best Practices](FIRMWARE_INTEGRITY_VERIFICATION_BEST_PRACTICES.md)
