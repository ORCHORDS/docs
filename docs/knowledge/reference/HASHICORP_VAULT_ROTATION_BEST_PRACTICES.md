---
title: "HashiCorp Vault Secret Rotation Best Practices Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "HashiCorp Vault documentation; OWASP Secrets Management Cheat Sheet"
---

# HashiCorp Vault Secret Rotation Best Practices Reference Card

## Scope

Reference card for HashiCorp Vault secret rotation as a mechanism for limiting the blast radius of credential compromise. Rotation strategies include dynamic secrets (Vault generates a new credential per lease, with TTL), static-credential rotation (Vault periodically issues new credentials to a target system), and database credential rotation (Vault manages DB user lifecycle). Profiles that govern secret management should adopt Vault-style rotation practices and bind to the OWASP Secrets Management Cheat Sheet, NIST SP 800-57 (Key Management), and NIST SP 800-53 access-control family.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | HashiCorp Vault documentation, OWASP Secrets Management Cheat Sheet |
| Companion artifacts | OWASP Secrets Management Cheat Sheet, NIST SP 800-57, NIST SP 800-53 |
| Source URL | https://developer.hashicorp.com/vault/docs |

## Plan

1. Reference Vault rotation best practices in secret-management policy and platform documentation.
2. Prefer dynamic secrets over static secrets; dynamic secrets are short-lived and bound to a lease.
3. Set explicit TTLs (time-to-live) and max TTLs for every dynamic secret; long TTLs reduce the value of dynamic secrets.
4. Adopt the lease-renewal pattern: applications renew leases before expiry rather than requesting new secrets at expiry.
5. Audit every secret access; Vault audit logs are the primary evidence of secret usage.
6. Bind to the OWASP Secrets Management Cheat Sheet for the broader secrets-management treatment.
7. Bind to NIST SP 800-57 (Key Management) for the key-management binding.
8. Bind to NIST SP 800-53 access-control family for the access-control binding.
9. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- HashiCorp Vault documentation (current version).
- Vault policy and role configuration.
- Application lease-renewal patterns.
- Vault audit log pipeline.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats HashiCorp Vault rotation as the canonical reference for secret rotation practices. Profiles that govern secret management should prefer dynamic secrets over static secrets, set explicit TTLs, use lease renewal rather than per-request issuance, audit every secret access, and bind to the OWASP Secrets Management Cheat Sheet, NIST SP 800-57, and NIST SP 800-53.

A profile that governs secret management without binding to Vault rotation best practices (or an equivalent rotation mechanism) is non-conformant.

## Implementation Notes

- Dynamic secrets are issued for a lease; the lease has a TTL and a max TTL.
- Lease renewal is preferred over re-issuance; re-issuance creates churn and audit-log noise.
- Vault revocation is immediate; secret revocation should be triggered by an event (compromise, offboarding, role change).
- Static-credential rotation (for example, rotating the root password for a database) uses Vault's rotation APIs; the previous credential remains valid until the rotation completes.
- Audit logs should be ingested into a SIEM with defined retention; Vault audit logs are sensitive and must be protected.

## Companion Documents

- [OWASP Secrets Management Cheat Sheet](OWASP_SECRETS_MANAGEMENT_CHEAT_SHEET.md)
- [Token Storage Best Practices](TOKEN_STORAGE_BEST_PRACTICES.md)
- [NIST SP 800-57 Key Management Version Governance](../reference/NIST_SP_800_57_KEY_MANAGEMENT_VERSION_GOVERNANCE.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
