# NIST SP 800-57 Part 3 Rev. 1 (2015) Cryptographic Key Management — Application-Specific Requirements Governance

## 1. Scope

This card governs ORCHORDS adoption of NIST SP 800-57 Part 3 Rev. 1 ("Cryptographic Key Management — Application-Specific Requirements") as the baseline for key lifecycles beyond the generic guidance in SP 800-57 Part 1. It applies to ORCHORDS-operated systems that manage keys for TLS, code signing, document signing, payment processing, DNSSEC, and workload identity.

## 2. Normative references

- NIST SP 800-57 Part 3 Rev. 1 (2015).
- NIST SP 800-57 Part 1 Rev. 5 (2020) — General key management guidance.
- NIST SP 800-131A Rev. 2 (2023) — Algorithm transition.
- NIST SP 800-133 Rev. 2 (2020) — Key generation.
- FIPS 140-3 (2024) — Cryptographic module validation.

## 3. Key class mapping

| Application | Class | Algorithm | Rotation | Storage |
| --- | --- | --- | --- | --- |
| TLS server cert | Public | ECDSA P-256 | 90 days | HSM or PKI issuer |
| Code signing | Public | ECDSA P-256 | 365 days | HSM, FIPS 140-3 L3 |
| Workload identity (SPIFFE) | Public | ECDSA P-256 | 90 days | KMS |
| Data encryption (envelope) | Symmetric | AES-256-GCM | 365 days | KMS |
| Document signing | Public | RSA-3072 | 730 days | HSM, FIPS 140-3 L3 |
| DNSSEC ZSK | Public | ECDSA P-256 | 90 days | HSM |
| DNSSEC KSK | Public | RSA-2048+ | 365 days | HSM, manual ceremony |

## 4. Lifecycle stages

1. **Generate** keys per SP 800-133; never reuse keys across applications.
2. **Distribute** via authenticated channels only; never email private keys.
3. **Use** keys for the registered purpose only; do not bridge algorithms.
4. **Store** in a FIPS 140-3 L3 module for any signing, or a hardware KMS for encryption.
5. **Rotate** on the schedule above; emergency rotation triggered by compromise.
6. **Retire** keys securely (zeroisation); retain metadata for audit, not the value itself.

## 5. Compromise handling

- Trigger an emergency rotation on any of: lost device, unauthorised access, suspected misuse, retirement of operator.
- Notify downstream consumers per `policies/crypto/rotation-procedure.md`.
- Quarantine the compromised public key in revocation lists within 60 minutes.

## 6. Tooling and ownership

| Domain | Tool | Owner |
| --- | --- | --- |
| TLS | cert-manager | Platform |
| Code signing | sigstore cosign + KMS | Security Engineering |
| Workload identity | SPIFFE/SPIRE | Platform |
| Envelope encryption | HashiCorp Vault Transit | Security Engineering |

## 7. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-07. New NIST SP 800-57 series editions or FIPS 140-3 transition triggers out-of-cycle updates.
