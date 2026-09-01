---
title: "Transitioning the Use of Cryptographic Algorithms and Key Lengths: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# NIST SP 800-131A Rev. 2 Transitions

## Normative protocol requirements

Apply acceptable, deprecated, legacy-use, and disallowed status per operation. Legacy verification/decryption is not permission to create new protection. RSA signature generation below 2048 bits is disallowed; SHA-1 signature generation is disallowed except narrow protocol cases; legacy verification is assessed separately. Three-key TDEA applying protection became disallowed after 2023.

## Validation and interoperability

Inventory algorithm, size, mode, hash, operation, data lifetime and module status. Test boundary artifacts so new-protection paths reject disallowed choices while isolated archival readers implement only authorized legacy use. Cite the controlling table/effective date for every exception.

## Meaningful failure handling

Block disallowed algorithm or key-size use and label legacy-use exceptions separately from approved generation or protection. Evidence must cite the controlling table, operation, effective date, key size, and approved exception; an unsupported exception is a policy failure.

## Canonical sources

- [NIST SP 800-131A Rev. 2](https://doi.org/10.6028/NIST.SP.800-131Ar2)
