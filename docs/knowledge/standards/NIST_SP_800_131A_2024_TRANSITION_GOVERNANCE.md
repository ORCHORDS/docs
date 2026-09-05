---
title: "NIST SP 800-131A Rev. 2 Algorithm Transition Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-131A Rev. 2 (March 2024); https://csrc.nist.gov/pubs/sp/800/131/a/r2/final"
---

# NIST SP 800-131A Rev. 2 Algorithm Transition Governance

## Purpose

NIST Special Publication 800-131A Rev. 2, *Transitioning the Use of Cryptographic Algorithms and Key Lengths* (March 2024), describes the cryptographic algorithm and key length transitions that NIST recommends for U.S. federal applications and that profiles worldwide commonly adopt. Rev. 2 supersedes Rev. 1 (November 2015) and aligns with FIPS 140-3, FIPS 180-5, FIPS 186-5, FIPS 197, FIPS 202, FIPS 203, FIPS 204, and FIPS 205.

## Current context and source status

SP 800-131A Rev. 2 was published in March 2024 and reflects the post-quantum migration roadmap. As of September 2026, no successor is in active draft. Profiles should reference Rev. 2 by version, track CNSA 2.0 (NSA) for national-security timing, and treat Rev. 1 as historical.

## Governance workflow and controls

1. Apply the disposition categories defined in Rev. 2: acceptable, deprecated, restricted, legacy-use, disallowed.
2. Acceptable algorithms: SHA-2 family, SHA-3 family, SHAKE128, SHAKE256, AES-128/192/256, ECDSA over P-256/P-384/P-521 with SHA-256/384/512, EdDSA, ML-KEM (FIPS 203), ML-DSA (FIPS 204), SLH-DSA (FIPS 205), KDFs per SP 800-108 and SP 800-56A.
3. Deprecated algorithms: 2TDEA, 3TDEA, AES in CBC for new protocols where AEAD alternatives exist, RSA for signature generation at less than 2048-bit keys, ECDSA at less than 224-bit curves.
4. Restricted algorithms: RSA signature verification (legacy acceptable, generation restricted per Rev. 2), SHA-1 (verification restricted to legacy use cases).
5. Disallowed: RSA key generation at 1024-bit or smaller, DSA, ECDSA at less than 160-bit, RSA signature generation at 1024-bit or smaller.
6. For hybrid deployments (classical plus post-quantum), combine classical algorithms with approved PQ algorithms per SP 800-227 (hybrid key establishment) and SP 800-228 (hybrid signature modes).
7. Maintain a cryptographic inventory with algorithm, key length, key origin, and disposal disposition.
8. Plan and execute algorithm transitions with a documented cutover plan, dual-running where required, and audit trail.

## Validation and evidence

- Cryptographic inventory with per-asset algorithm, key length, use case, and SP 800-131A Rev. 2 disposition.
- Algorithm-transition decision records and migration plans.
- FIPS 140-3 module validation certificates for every approved algorithm in use.
- Hybrid deployment evidence (SP 800-227, SP 800-228) where post-quantum transitions are in flight.
- Disposition-update records when NIST revises the SP 800-131A series.

Evidence that omits the cryptographic inventory, the migration plans, or the FIPS 140-3 module validation does not establish SP 800-131A Rev. 2 conformance.

## Source basis

- NIST SP 800-131A Rev. 2 (March 2024) — Cryptographic Algorithm and Key Length Transition.
- NIST FIPS 140-3 — Security Requirements for Cryptographic Modules.
- NIST FIPS 180-5, FIPS 186-5, FIPS 197, FIPS 202 — companion algorithm standards.
- NIST FIPS 203 (ML-KEM), FIPS 204 (ML-DSA), FIPS 205 (SLH-DSA) — post-quantum standards.
- NIST SP 800-227 — hybrid key establishment.
- NIST SP 800-228 — hybrid signature modes.
- NIST CNSA 2.0 — NSA national-security transition timing.
