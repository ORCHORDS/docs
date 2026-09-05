---
title: "IETF TLS Hybrid PQ Profile Version Guide"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF TLS Working Group drafts (hybrid PQ key exchange); current consensus drafts at https://datatracker.ietf.org/wg/tls/"
---

# IETF TLS Hybrid PQ Profile Version Guide

## Scope

Reference card for IETF TLS hybrid post-quantum key exchange profiles. Hybrid profiles combine a classical key exchange (for example X25519) with a post-quantum key exchange (for example ML-KEM, ML-DSA, or FrodoKEM) so that the resulting TLS connection is at least as strong as the stronger of the two components, and not weaker than the classical-only baseline. Profiles governing TLS configurations that adopt hybrid PQ key exchange should reference the current IETF consensus draft and the supporting SP 800-227 / FIPS 203 / FIPS 204 / FIPS 205 documents.

## Identifier table

| Field | Value |
| --- | --- |
| Primary artifacts | IETF TLS WG consensus drafts (hybrid PQ key exchange, hybrid PQ signatures), IETF TLS 1.3 (RFC 8446), TLS 1.2 (RFC 5246) |
| Companion artifacts | RFC 8446 (TLS 1.3), RFC 9798 (PQ TLS authentication), NIST FIPS 203 (ML-KEM), FIPS 204 (ML-DSA), FIPS 205 (SLH-DSA), NIST SP 800-227 |
| Use cases | TLS connections requiring post-quantum resistance to harvest-now-decrypt-later, hybrid key exchange and hybrid signature deployment |
| Source URL | https://datatracker.ietf.org/wg/tls/ |

## Plan

1. Reference the current IETF TLS WG consensus draft(s) for hybrid PQ key exchange and authentication whenever a profile adopts a hybrid PQ TLS configuration.
2. Specify the hybrid construction: which classical algorithm is paired with which post-quantum algorithm, and the key-share or signature construction.
3. Specify the negotiation model: which cipher suites or named groups are offered, and the expected fallback behavior when the peer does not support the hybrid construction.
4. Specify the certificate chain model: classical PKI or PQ-only PKI; hybrid PKI with PQ signature algorithms in the chain.
5. Specify the validation policy: which cipher suites are accepted, the failure mode when negotiation fails, and the audit logging of PQ-capable vs PQ-incapable peers.
6. Plan the transition: hybrid construction now, post-quantum-only construction once standards are stable, peer support is universal, and PQ-only PKI is operational.

## Inputs

- Current IETF TLS WG draft(s) for hybrid PQ key exchange and authentication.
- RFC 8446 (TLS 1.3) and RFC 5246 (TLS 1.2) for protocol baseline.
- NIST FIPS 203, FIPS 204, FIPS 205 for post-quantum algorithm specifications.
- Internal TLS configuration policy, certificate inventory, and peer support survey.

## ORCHORDS Profile

ORCHORDS treats the current IETF TLS WG consensus drafts as the canonical reference for hybrid PQ TLS profiles. Profiles that adopt hybrid PQ should reference the specific draft and version rather than treating "hybrid PQ" as a generic term. A profile that references "post-quantum TLS" without binding to a specific draft and algorithm pair is non-conformant.

Profiles that govern TLS configurations also reference NIST SP 800-52 (current revision) and the CA/Browser Forum Baseline Requirements (current version).

## Implementation Notes

- Harvest-now-decrypt-later is a real threat for TLS traffic that should remain confidential for years; hybrid PQ should be evaluated for any long-lived confidential connection.
- Hybrid key exchange requires the server to support both algorithms; if the server supports only the post-quantum component, the connection may not establish with classical-only peers.
- Hybrid signature chains are heavier than classical chains; budget for the increased chain size and verification cost.
- Hybrid PQ TLS is not a replacement for end-to-end application-layer cryptography; it only protects the TLS layer.
- Log hybrid PQ configuration state (negotiated cipher suite, certificate chain, peer capability) for incident response and audit.

## Companion Documents

- [NIST SP 800-52 TLS Guidelines](NIST_SP_800_52_TLS_GUIDELINES.md)
- [NIST FIPS 203 ML-KEM Version Transition Governance](../standards/NIST_FIPS_203_ML_KEM_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST FIPS 204 ML-DSA Version Transition Governance](../standards/NIST_FIPS_204_ML_DSA_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST FIPS 205 SLH-DSA Version Transition Governance](../standards/NIST_FIPS_205_SLH_DSA_VERSION_TRANSITION_GOVERNANCE.md)
- [NIST SP 800-208 Quantum-Resistant Version Transition Governance](../standards/NIST_SP_800_208_QUANTUM_RESISTANT_VERSION_TRANSITION_GOVERNANCE.md)
- [RFC 5280 X.509 PKI Profile](RFC_5280_X509_PKI_PROFILE.md)
