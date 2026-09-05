---
title: "NIST FIPS 180-5 Secure Hash Standard (SHS) Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST FIPS 180-5 (August 2024); https://csrc.nist.gov/pubs/fips/180-5/final"
---

# NIST FIPS 180-5 Secure Hash Standard (SHS) Governance

## Purpose

NIST Federal Information Processing Standard 180-5, *Secure Hash Standard (SHS)*, specifies the SHA-3 family of hash functions: SHA3-224, SHA3-256, SHA3-384, SHA3-512, and the extendable-output functions SHAKE128 and SHAKE256. The current FIPS 180-5 was published in August 2024 and supersedes FIPS 180-4. FIPS 202 specifies the underlying Keccak-based sponge construction.

## Current context and source status

FIPS 180-5 (August 2024) is the current SHS publication. As of September 2026, no successor is in active draft. FIPS 180-4 (March 2012) is superseded for new cryptographic implementations but remains in effect for legacy audit trails where legacy products are deployed. Profiles should reference FIPS 180-5 by version and treat FIPS 180-4 as historical.

## Governance workflow and controls

1. Use SHA-3 family functions (SHA3-224, SHA3-256, SHA3-384, SHA3-512) for new integrity, signature, and key-derivation use cases.
2. Use SHAKE128 or SHAKE256 as extendable-output functions (XOFs) where variable output length is required; do not use them as plain hash functions without an output-length policy.
3. For SHA-2 family (SHA-256, SHA-384, SHA-512), continue to use them where required for interoperability with established protocols (TLS, DNSSEC, S/MIME, code-signing roots); do not replace for replacement's sake.
4. SHA-1 and SHA-224 are NOT approved for cryptographic use in new systems; SHA-1 collision resistance has been broken in practice (SHAttered, 2017).
5. For HMAC usage, pair the hash function with NIST SP 800-107 and the corresponding HMAC standard.
6. For post-quantum transition, use SHA-3 or SHA-2 within approved signature schemes (FIPS 204 ML-DSA, FIPS 205 SLH-DSA).
7. Verify that any third-party library you depend on conforms to FIPS 180-5 (not a pre-180-4 implementation claiming SHA-3).
8. Record the hash function family, output length, and use case (integrity, authentication, KDF input, signature, XOF) in your cryptographic inventory.

## Validation and evidence

- Cryptographic inventory listing the SHA-3, SHA-2, SHAKE, and legacy SHA-1 usages, with hash function family and output length per use case.
- Algorithm-transition decision records for any movement away from SHA-1 or SHA-224.
- Library vendor attestations of FIPS 180-5 conformance for SHA-3 implementations.
- Interoperability test evidence where SHA-2 must be retained for protocol compatibility.
- FIPS 140-3 module validation certificates for modules providing SHA-3 / SHA-2 implementations.

Evidence that omits the cryptographic inventory, the algorithm-transition records, or the FIPS 140-3 validation references does not establish FIPS 180-5 conformance.

## Source basis

- NIST FIPS 180-5 (August 2024) — Secure Hash Standard (SHA-3 family, SHAKE XOFs).
- NIST FIPS 202 — SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions.
- NIST SP 800-131A Rev. 2 (March 2024) — Cryptographic Algorithm and Key Length Transition.
- NIST FIPS 140-3 — Security Requirements for Cryptographic Modules.
- NIST FIPS 204 (ML-DSA), FIPS 205 (SLH-DSA) — post-quantum signature algorithms using SHA-3.
