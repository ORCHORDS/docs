---
title: "Secret Rotation Playbook"
owner: "IAM Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# Secret Rotation Playbook

## Trigger

Use this playbook when a secret (API key, cloud credential, database password, encryption key, signing key, OAuth client secret, service-account token, or similar credential) is scheduled for routine rotation, has been compromised, has been over-issued beyond policy, or must be retired on a service or owner change.

## Scope

Apply the process to all long-lived credentials under the organization's identity governance scope, including human credentials, machine credentials stored in vault, dynamically issued short-lived tokens, and credentials embedded in applications, infrastructure-as-code, and third-party platforms.

## Inputs

- secret inventory entry (owner, system, classification, last rotation, retention class);
- vault or secret-management system identifier;
- rotation policy (interval, on-event, on-leave);
- downstream consumers (services and pipelines that read the secret);
- incident ticket or scheduled rotation task.

## Steps

1. **Identify the rotation scope.** Confirm the secret identifier, its owners, the systems that depend on it, and any consumers with cached credentials.
2. **Provision the new credential.** Generate a high-entropy replacement in the vault; ensure the secret-management system records the new credential's metadata, fingerprint, and expiry.
3. **Pre-distribute where supported.** For systems that consume secrets via dynamic retrieval, deploy the new credential to the secret store and confirm consumers pick up the new value within the documented propagation window.
4. **Replace and verify.** Update each consumer to use the new credential; verify functional authentication against the protected system.
5. **Retire the old credential.** On confirmation that all consumers are using the new credential, disable and revoke the old credential; do not rely on overlap unless the overlap is documented and bounded.
6. **Revoke at the source.** For compromised secrets, additionally revoke at the issuing authority (cloud IAM, identity provider, certificate authority, OAuth provider, third-party SaaS platform) so the credential cannot be used even if replayed.
7. **Rotate downstream tokens.** Invalidate refresh tokens, access tokens, and session tokens derived from the rotated secret.
8. **Audit.** Record the rotation event, the parties notified, the verification evidence, and any consumers that required manual updates.
9. **Detect reuse.** Search logs and audit data for use of the retired credential; treat any post-retirement use as a security finding.

## Escalation

Escalate to the IAM Lead and Security when:
- a secret is suspected of compromise;
- a consumer cannot be migrated within the overlap window;
- the rotation impacts downstream systems whose downtime exceeds tolerance;
- the secret is shared across organizational or trust boundaries.

## Evidence

- rotation event record with timestamps and approvers;
- vault version history showing active and retired credentials;
- verification logs from target systems;
- revocation and propagation audit logs;
- risk register entry tying the secret to its consuming systems.

## Completion Criteria

The rotation is considered complete when:
- the new credential is in active use and verified;
- the old credential is revoked at the issuing authority and at the secret store;
- downstream tokens are rotated and inactive use is monitored;
- the rotation event is recorded in the central audit log.

## Exceptions

Document deviations with the technical justification, scope, expiration, compensating control, and review schedule. Where rotation is impractical due to a third-party constraint, document the mitigation and track it for remediation.

## Related Documents

- [NIST SP 800-57 Key Management](../reference/NIST_SP_800_57_KEY_MANAGEMENT.md)
- OWASP Secrets Management Cheat Sheet
- HashiCorp Vault Rotation Best Practices
- [OAuth 2.1 Client Integration Response](OAUTH_2_1_CLIENT_INTEGRATION_RESPONSE.md)
