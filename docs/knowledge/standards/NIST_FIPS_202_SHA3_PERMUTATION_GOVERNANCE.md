---
title: "NIST FIPS 202 SHA-3 Standard Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST FIPS 202 (August 2015); https://csrc.nist.gov/pubs/fips/202/final"
---

# NIST FIPS 202 SHA-3 Standard Governance

## Purpose

NIST Federal Information Processing Standard 202, *SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions*, specifies the Keccak-p permutation-based sponge construction used by the SHA-3 hash functions (SHA3-224, SHA3-256, SHA3-384, SHA3-512) and the two extendable-output functions SHAKE128 and SHAKE256. FIPS 202 was published in August 2015 and complements FIPS 180-5.

## Current context and source status

FIPS 202 (August 2015) is the current SHA-3 Standard. As of September 2026, no successor is in active draft. Profiles should reference FIPS 202 by version together with FIPS 180-5 (which defines the SHA-3 hash function families built on the FIPS 202 permutation).

## Governance workflow and controls

1. Use SHA-3 hash functions defined in FIPS 180-5 (SHA3-224, SHA3-256, SHA3-384, SHA3-512) for new applications where SHA-3 is mandated or preferred.
2. Use SHAKE128 or SHAKE256 (defined in FIPS 202) where an extendable-output function is appropriate; pair with a documented output-length policy.
3. For HMAC construction over SHA-3, use NIST SP 800-107 recommendations and the same key and tag lengths.
4. For post-quantum signature schemes, use FIPS 204 (ML-DSA) and FIPS 205 (SLH-DSA) which rely on FIPS 202 SHA-3 functions internally.
5. For Keccak-p permutation usage in custom MAC or KDF constructions, document the parameters and verify conformance to FIPS 202 section 3.
6. Validate FIPS 140-3 module certificates that claim SHA-3 / SHAKE support; do not assume Keccak-p permutations from libraries without FIPS validation.
7. Distinguish FIPS 202 SHA-3 from the original Keccak submission (different padding rule: 01 vs 06); do not interchange implementations.

## Validation and evidence

- Cryptographic inventory listing SHA-3 and SHAKE usages per system and per use case.
- FIPS 140-3 module validation certificates covering the SHA-3 / SHAKE implementations.
- Library vendor attestations of FIPS 202 conformance (note: pre-FIPS-202 implementations may use the original Keccak padding).
- Interoperability test evidence for any protocol using SHA-3 (TLS 1.3, DNSSEC, S/MIME, code-signing).
- Decision records for SHAKE128 vs SHAKE256 selection, including output length per use case.

Evidence that omits the cryptographic inventory, the FIPS 140-3 module validation, or the SHAKE length policy does not establish FIPS 202 conformance.

## Source basis

- NIST FIPS 202 (August 2015) — SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions.
- NIST FIPS 180-5 (August 2024) — Secure Hash Standard (companion specifying the SHA-3 hash function families).
- NIST FIPS 140-3 — Security Requirements for Cryptographic Modules.
- NIST SP 800-107 Rev. 1 — Recommendation for Applications Using Approved Hash Algorithms.
- NIST FIPS 204 (ML-DSA), FIPS 205 (SLH-DSA) — post-quantum signature schemes using SHA-3.
