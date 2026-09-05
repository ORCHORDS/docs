---
title: "RFC 8391 XMSS Profile"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 8391 (May 2018); https://www.rfc-editor.org/rfc/rfc8391"
---

# RFC 8391 XMSS Profile

## Scope

Reference card for IETF RFC 8391, *XMSS: eXtended Merkle Signature Scheme* (May 2018). XMSS is a stateful hash-based signature scheme designed for post-quantum resistance. The companion multi-tree variant XMSS-MT (RFC 8391 Appendix A) extends XMSS with multiple levels. Profiles governing firmware signing, software signing, or long-term document signing that require a conservative post-quantum fallback should reference RFC 8391 by revision. Note that XMSS is stateful; RFC 8391 §5.1 mandates against state reuse.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 8391 (May 2018) |
| Status | Informational (consensus-driven operational guidance) |
| Companion documents | RFC 8554 (LMS / HSS — companion hash-based scheme), NIST SP 800-208 (stateful HBS profile), FIPS 204 (ML-DSA), FIPS 205 (SLH-DSA — stateless alternative) |
| Use cases | Firmware signing, software signing, long-term document signing, code signing in air-gapped or constrained environments |
| Source URL | https://www.rfc-editor.org/rfc/rfc8391 |

## Plan

1. Reference RFC 8391 by revision whenever a profile adopts XMSS / XMSS-MT as the signature scheme.
2. Treat state management as a security-critical control: state reuse across signatures produces a key compromise (RFC 8391 §5.1).
3. Specify the XMSS parameter set (for example XMSS-SHA2_16_256, XMSSMT-SHA2_20/2_256) and document the expected signature size and key generation time.
4. Specify the storage model for the one-time signature keys (WOTS+ keys): each WOTS+ key may be used exactly once.
5. Specify the operational procedure for backup and recovery: backup procedures must preserve the per-key usage state to prevent accidental reuse after restore.
6. Where stateless signatures are acceptable, prefer SLH-DSA (FIPS 205, RFC to be published) rather than XMSS.

## Inputs

- RFC 8391 normative sections: 4 (XMSS), 5 (operational considerations), 6 (parameter choices), Appendix A (XMSS-MT).
- NIST SP 800-208 parameter sets and approved algorithms.
- Internal key generation, signing, and verification tooling; signing-key state store and audit log.
- Firmware and software update policy that requires post-quantum-resistant signatures.

## ORCHORDS Profile

ORCHORDS treats RFC 8391 as the canonical reference for XMSS / XMSS-MT hash-based signatures. Profiles that adopt XMSS should reference the RFC by revision, specify the parameter set, and bind the state-management procedure to the signing tool. A profile that adopts XMSS without specifying the state-management procedure is non-conformant.

XMSS / XMSS-MT are stateful and require careful operational discipline. ORCHORDS profiles that need post-quantum signatures without state-management overhead should consider SLH-DSA (FIPS 205) instead.

## Implementation Notes

- State reuse is catastrophic; even a single bit error in the state tracking can compromise the signature key.
- Backup and restore of stateful signature systems must use a backup format that preserves the per-key usage markers.
- High-volume signing workloads are not well-suited to XMSS because of the per-signature state update; consider batching or using a stateless scheme.
- XMSS signatures are large (kilobytes) compared with RSA or ECDSA; budget for the increased signature size in storage and bandwidth.
- XMSS-MT (multi-tree) reduces the per-signature time penalty at the cost of larger keys; choose the tree depth and total tree count based on the expected number of signatures.

## Companion Documents

- [RFC 8554 LMS Profile](RFC_8554_LMS_PROFILE.md)
- [NIST SP 800-208 Quantum-Resistant Version Transition Governance](../standards/NIST_SP_800_208_QUANTUM_RESISTANT_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST FIPS 204 ML-DSA Version Transition Governance](../standards/NIST_FIPS_204_ML_DSA_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST FIPS 205 SLH-DSA Version Transition Governance](../standards/NIST_FIPS_205_SLH_DSA_VERSION_TRANSITION_GOVERNANCE.md)
- [Firmware Integrity Verification Best Practices](FIRMWARE_INTEGRITY_VERIFICATION_BEST_PRACTICES.md)
- [Secure Boot and Measured Boot Response](../playbooks/SECURE_BOOT_AND_MEASURED_BOOT_RESPONSE.md)
