---
title: "NIST SP 800-57 Key Management — Version Governance"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-57 Part 1 Rev. 5 (or current published revision); https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-57pt1r5.pdf"
---

# NIST SP 800-57 Key Management — Version Governance

## Scope

Reference card for version governance of the NIST SP 800-57 key-management recommendations. The publication family — Part 1 (general), Part 2 (best practices for key-management organizations), Part 3 (application-specific key management) — defines cryptographic-key lifecycles, key states, key types, and algorithm/strength recommendations. Profiles that govern key management should bind to SP 800-57 by current revision and track each revision's deprecated algorithms, key sizes, and protocol bindings.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | NIST SP 800-57 Part 1 Rev. 5 (or current published revision) |
| Status | Continuously maintained by NIST; track CSD transitions for deprecation notices |
| Companion artifacts | FIPS 140-3 (module validation), FIPS 186-5 (digital signatures), NIST SP 800-131A (transitions) |
| Source URL | https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-57pt1r5.pdf |

## Plan

1. Reference SP 800-57 Part 1 Rev. 5 (or current revision) whenever a profile governs cryptographic-key lifecycles.
2. Adopt the SP 800-57 key-state model: pre-activation, active, deactivated, suspended, compromised, destroyed.
3. Adopt the SP 800-57 key-type taxonomy: symmetric keys, private keys, public keys, master keys, key-encryption keys, data-encryption keys.
4. Track NIST cryptographic algorithm and key-size transitions through NIST SP 800-131A.
5. Bind key-generation guidance to FIPS 186-5 (signatures) and SP 800-90A (DRBG).
6. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- NIST SP 800-57 Part 1 Rev. 5 (current published revision).
- NIST SP 800-57 Part 2 and Part 3 application-specific guidance.
- FIPS 140-3 module certificate and security policy.
- Internal key-management policy, key inventory, rotation schedule, and destruction log.

## ORCHORDS Profile

ORCHORDS treats SP 800-57 as the canonical reference for cryptographic-key lifecycle governance. Profiles that govern key management should reference SP 800-57 by current revision, identify the key types in scope, and bind to FIPS 140-3, FIPS 186-5, and SP 800-90A.

A profile that manages cryptographic keys without binding to SP 800-57 is non-conformant.

## Implementation Notes

- SP 800-57 key states drive operational procedures (generation, activation, rotation, suspension, destruction); each state transition must be logged.
- Algorithm deprecation windows announced via SP 800-131A must be reflected in the internal cryptographic inventory before the deadline.
- Key-encryption keys must be cryptographically separated from data-encryption keys; do not reuse key types across roles.
- Compromised-key events require root-cause analysis and revocation; SP 800-57 defines the lifecycle that determines whether rotation or full revocation applies.
- Application-specific Part 3 guidance supplements Part 1 for protocols such as TLS, IPsec, S/MIME, and DNSSEC.

## Companion Documents

- FIPS 140-3 — Cryptographic Module Validation Program
- FIPS 186-5 — Digital Signature Standard
- NIST SP 800-90A — Random Bit Generators
- NIST SP 800-131A — Cryptographic Algorithm and Key-Size Transitions
- NIST SP 800-56A — Key Establishment
- NIST SP 800-56B — Key Establishment Using Integer Factorization
- NIST SP 800-56C — Key Derivation
- NIST SP 800-108 — Key Derivation Using Pseudorandom Functions
- ISO/IEC 11770-1 — Key Management — Framework

## Metadata

- Source: NIST SP 800-57 Part 1 Rev. 5; current published revision; companion artifacts above.
- Profile-binding scope: cryptographic key management, key lifecycle, algorithm and key-size transitions.
