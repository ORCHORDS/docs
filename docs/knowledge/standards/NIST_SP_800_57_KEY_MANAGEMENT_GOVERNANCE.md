---
title: NIST SP 800-57 Key Management Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NIST SP 800-57 Pt. 1 Rev. 5 (May 2020) — Recommendation for Key Management: General; Pt. 2 (2019) — Best Practices; Pt. 3 Rev. 1 (2015) — Application-Specific Key Management; https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final
---

# NIST SP 800-57 Key Management Governance

## Scope

This card governs how `orchords-docs` evaluates cryptographic key management against NIST SP 800-57. It is the reference input for any KB card that touches symmetric / asymmetric keys, key lifecycle, or key agreement.

## Why this card exists

NIST SP 800-57 Pt. 1 Rev. 5 (May 2020) is the canonical US federal key-management recommendation. Without an explicit card, the KB cites key-management practices that do not align with the cryptographic-strength tables or key-lifecycle phases.

## Document set

- **NIST SP 800-57 Pt. 1 Rev. 5** (May 2020) — General.
- **NIST SP 800-57 Pt. 2** (2019) — Best Practices.
- **NIST SP 800-57 Pt. 3 Rev. 1** (2015) — Application-Specific.

References: `https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final`.

## Cryptographic strength

| Bits of security | Symmetric | Asymmetric (RSA/ECC) |
|---|---|---|
| 80 | 2TDEA | RSA 1024 (legacy) |
| 112 | 3TDEA | RSA 2048 / ECC 224 |
| 128 | AES-128 | RSA 3072 / ECC 256 |
| 192 | AES-192 | RSA 7680 / ECC 384 |
| 256 | AES-256 | RSA 15360 / ECC 521 |

References: SP 800-57 Pt. 1 § 5.6.

## Key lifecycle

| Phase | Description |
|---|---|
| Pre-operational | key generation, distribution |
| Operational | storage, use, backup |
| Post-operational | archival |
| Destroyed | deletion, zeroization |

## Key types

| Type | Use |
|---|---|
| Symmetric (AES) | encryption |
| Asymmetric (RSA, ECC) | signatures, key agreement |
| Symmetric key wrapping | key transport |
| HMAC keys | authentication |
| Key encryption keys (KEK) | wrapping |

## Cryptoperiods

| Key type | Cryptoperiod |
|---|---|
| AES-128 | up to 25 years |
| RSA signing | up to 3 years |
| TLS ephemeral | per session |
| CA root | 10–20 years |
| CA intermediate | 5–10 years |

References: SP 800-57 Pt. 1 § 5.3.

## Cross-reference

| Domain | Card |
|---|---|
| TLS | `TLS_RFC_8446_VERSION_GOVERNANCE.md` |
| 800-131A | `NIST_SP_800_131A_2024_TRANSITION_GOVERNANCE.md` |
| Vault | `VAULT_VERSION_GOVERNANCE.md` |
| PKI | (deferred) |

## Self-attestation cycle

Every 180 days:

1. Walk every KB reference card that touches cryptography.
2. Confirm the bit-strength is current.
3. Update the next-review date.

## Sources

- NIST SP 800-57 Pt. 1 Rev. 5: `https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final`
- NIST SP 800-57 Pt. 2: `https://csrc.nist.gov/publications/detail/sp/800-57-part-2/final`
- NIST SP 800-57 Pt. 3 Rev. 1: `https://csrc.nist.gov/publications/detail/sp/800-57-part-3/rev-1/final`
