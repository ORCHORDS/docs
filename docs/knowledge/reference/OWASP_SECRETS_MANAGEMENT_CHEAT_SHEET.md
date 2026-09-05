---
title: "OWASP Secrets Management Cheat Sheet Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "OWASP Secrets Management Cheat Sheet; https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html"
---

# OWASP Secrets Management Cheat Sheet Reference Card

## Scope

Reference card for the OWASP Secrets Management Cheat Sheet, the canonical reference for handling secrets (passwords, API keys, tokens, certificates, database credentials) across the software lifecycle. The cheat sheet addresses secret generation, storage, distribution, rotation, revocation, and disposal, and it codifies what constitutes a secret-management violation. Profiles that govern secret handling should cite the OWASP cheat sheet and bind to the HashiCorp Vault rotation reference, NIST SP 800-57 (Key Management), and NIST SP 800-53 access-control family.

## Identifier table

| Field | Value |
| --- | --- |
| Primary source | OWASP Secrets Management Cheat Sheet |
| Companion artifacts | HashiCorp Vault Rotation Best Practices, NIST SP 800-57, NIST SP 800-53, OWASP Top 10 |
| Source URL | https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html |

## Plan

1. Reference the OWASP Secrets Management Cheat Sheet in secret-management policy and developer documentation.
2. Define what counts as a secret: passwords, API keys, tokens, certificates, database credentials, encryption keys, signing keys.
3. Use a secret-management platform (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, GCP Secret Manager) for storage and rotation.
4. Never commit secrets to source control; use pre-commit hooks and CI scanning to detect.
5. Never store secrets in environment variables of long-lived processes without rotation.
6. Prefer dynamic, short-lived secrets (for example, Vault dynamic database credentials) over static secrets.
7. Define a rotation policy per secret type: minimum, recommended, and maximum age.
8. Define a revocation procedure: immediate on suspected compromise; routine on role change.
9. Define a disposal procedure: cryptographic erasure for encrypted stores; overwrite for unencrypted stores.
10. Bind to HashiCorp Vault Rotation Best Practices for the rotation mechanism.
11. Bind to NIST SP 800-57 (Key Management) for the key-management lifecycle.
12. Bind to NIST SP 800-53 access-control family for the access-control binding.
13. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- OWASP Secrets Management Cheat Sheet.
- Secret-management platform documentation.
- Source-control scanning tooling (for example, GitGuardian, TruffleHog, gitleaks).
- Rotation policy and incident response procedures.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats the OWASP Secrets Management Cheat Sheet as the canonical reference for secret handling. Profiles that govern secret handling should define what counts as a secret, use a secret-management platform, never commit secrets to source control, prefer dynamic short-lived secrets, define rotation and revocation procedures, and bind to the HashiCorp Vault rotation reference, NIST SP 800-57, and NIST SP 800-53.

A profile that handles secrets without binding to the OWASP Secrets Management Cheat Sheet is non-conformant.

## Implementation Notes

- Pre-commit hooks (for example, gitleaks) catch most accidental commits before they reach the remote.
- CI scanning should run on every push; blocking checks should be enabled for known secret patterns.
- Long-lived API keys are a recurring root cause; prefer short-lived tokens (OAuth access tokens) issued at request time.
- Environment variables are visible to any process with access to the process environment; prefer secret-management-platform SDK calls.
- Revocation must be tested; secret-management platforms should have a documented "revoke and verify" procedure.

## Companion Documents

- [HashiCorp Vault Rotation Best Practices](HASHICORP_VAULT_ROTATION_BEST_PRACTICES.md)
- [Token Storage Best Practices](TOKEN_STORAGE_BEST_PRACTICES.md)
- [NIST SP 800-57 Key Management Version Governance](../reference/NIST_SP_800_57_KEY_MANAGEMENT_VERSION_GOVERNANCE.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
- [OWASP Top 10 Verification Review](OWASP_TOP_10_VERIFICATION_REVIEW.md)
