# Secret Rotation Playbook

## Purpose

Drive a predictable rotation of any secret the project manages (database password, API key, OAuth client secret, signing key, SSH key, TLS server cert, mTLS client cert). The playbook covers human-managed, machine-managed, and workload-identity-managed secrets, and the rotation cadence that each class requires.

## Audience

Security engineer, SRE on-call, platform-team engineers, application owners.

## Pre-conditions

1. The secret class is registered in the secret inventory (`docs/knowledge/reference/SECRET_INVENTORY.md` if present).
2. The rotation cadence is set per the cadence table below.
3. The target system supports dual-key window (old and new secret both accepted) for at least 24 hours.
4. The secret is stored in a vault that supports versioning (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, GCP Secret Manager, sealed-secrets).
5. The reference card for the protocol is current (e.g., `MQTT_5_VERSION_GOVERNANCE.md` for OAuth bearer tokens).

## Procedure

### 1. Identify the secret class

| Class | Examples | Rotation cadence | Owner |
|---|---|---|---|
| Human-managed credential | admin password, root SSH key | 90 days | security engineer |
| Service-account API key | AWS access key, GCP service account key | 30 days | platform team |
| OAuth 2.0 client secret | integration partner credential | 180 days | platform team |
| Database password | Postgres / MySQL / MongoDB user | 90 days | DBA |
| TLS server cert | public-facing cert | 90 days (or per CA policy) | platform team |
| mTLS client cert | service-to-service mTLS | 90 days | platform team |
| Workload-identity token | SPIFFE / SPIRE / cloud workload identity | automatic, ≤ 24 hours | platform team |
| Encryption CMK | customer-managed KMS key | 365 days | security engineer |
| Signing key | JWT issuer, code-signing | 365 days | security engineer |
| SSH user key | human bastion access | 180 days | security engineer |
| SSH host key | server host key | never (fingerprint pinned) | platform team |
| SSH CA | project-internal CA | 365 days | security engineer |

### 2. Pre-rotation validation

1. Confirm the target system accepts both the old and new secret for a 24-hour window (dual-key window).
2. Confirm the secret inventory entry is current.
3. Confirm the rotation owner is on call during the change window.
4. Confirm the change ticket is open with the dual-key window timebox.

### 3. Rotation

1. Generate the new secret in the vault. Record the secret ID and the rotation timestamp.
2. Push the new secret to the target system alongside the old secret. Confirm acceptance.
3. Observe the dual-key window for at least 24 hours. Validate application behavior with both secrets.
4. After the dual-key window: revoke the old secret at the source (vault, CA, IAM, KMS).
5. Confirm the old secret is rejected on retry. If the old secret still works after revocation, treat as an incident.

### 4. Post-rotation validation

- Application logs show no `AUTH_FAILED` events with the new secret.
- Application logs show no successful auth with the old secret after revocation.
- The secret inventory entry has been updated with the new ID and timestamp.
- Audit log entries confirm the rotation event.

### 5. Storage and inventory update

1. Update the secret inventory entry with the new secret ID.
2. Update the change ticket with timestamps for: pre-rotation, rotation, dual-key end, revocation.
3. Archive the audit log entries under the secret ID for retention period.
4. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` if the rotation caused any user-visible outage.

## Special cases

### 5a. Emergency rotation

If a secret is suspected of being compromised:

1. Generate and push the new secret immediately.
2. Revoke the old secret immediately, without waiting for the dual-key window.
3. Investigate the suspected compromise in parallel (timeline, scope, attribution).
4. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` within 24 hours.

### 5b. Certificate revocation (CRL / OCSP)

For TLS / mTLS certs:

1. The rotation generates a new cert in the vault.
2. The old cert is added to the CRL or marked invalid via OCSP responder.
3. The CA revocation publication SLA is ≤ 24 hours.
4. The old cert is removed from the target system after the revocation SLA elapses.

### 5c. CMK rotation

For customer-managed KMS keys:

1. Generate new key material in the KMS.
2. Alias the old key as `previous-version`; alias the new key as `current-version`.
3. After the dual-key window (≥ 24 hours): disable the previous-version key.
4. After ≥ 30 days: schedule the previous-version key for deletion (the KMS deletion SLA is 7 — 30 days).

## Rollback

A failed rotation is rolled back by:

1. Re-activating the old secret as the active secret at the source.
2. Reverting the target system to the old secret.
3. Documenting the failure in the change ticket.

Rollback decisions must be made within 30 minutes of the failure. Every rollback triggers `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## References

- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- `WORKLOAD_IDENTITY_ROTATION_PLAYBOOK.md`
- OWASP Secrets Management Cheat Sheet: `https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html`
- NIST SP 800-57 (Key Management): `https://csrc.nist.gov/publications/detail/sp/800-57-part-1-rev-5/final`
