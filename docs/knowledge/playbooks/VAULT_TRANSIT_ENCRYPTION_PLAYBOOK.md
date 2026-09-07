# HashiCorp Vault Transit Encryption Playbook

## Purpose
Stand up and operate the Vault Transit secret engine for envelope encryption of application data at rest. The playbook covers key creation, naming, rotation, access policy, and audit integration so engineering teams can adopt a consistent, auditable encryption posture across environments. It is intended to be repeatable, safe to run under change control, and aligned with the security baseline for cryptographic controls.

## Audience
Platform engineers, security engineers, application owners, and SREs on rotation. Platform engineers perform initial setup, upgrades, and rotation; security engineers own policy, audit, and incident response; application owners integrate their services and manage their data; SREs operate the runbook during on-call shifts, drills, and post-incident verification.

## Pre-conditions
- Vault server running release 1.18.x or the current LTS line, sealed and unsealed per the standard KMS-backed unseal workflow.
- A managed audit device enabled (syslog, file, or socket) with confirmed delivery to the destination.
- An authentication method in place for workload and human identities (OIDC, AppRole, or Kubernetes) with group mappings defined.
- The transit engine mounted at a documented, namespaced path.
- Network reachability from application hosts to the Vault cluster over a TLS channel.
- An agreed key naming convention reviewed by security and recorded in the runbook index.

## Procedure
1. Mount the transit engine at the agreed namespaced path, for example `transit/`.
2. Adopt a key naming convention such as `<purpose>-<env>-v<n>`, for example `payments-prod-v1`.
3. Create the key with the type that matches the use case, for example `aes256-gcm96` for symmetric envelope encryption.
4. Tune `allow_plaintext_backup`, `deletion_allowed`, and `min_decryption_version` per the security baseline; start with conservative defaults.
5. Configure rotation via `keys/rotate/<key>` on a fixed cadence and record the schedule in the change calendar.
6. Authorize application identities with a Vault policy granting `update` on `transit/encrypt/<key>` and the minimum required decryption capability; reference the [Vault Audit Log Shipping Playbook](VAULT_AUDIT_LOG_SHIPPING_PLAYBOOK.md) for the policy skeleton.
7. Implement envelope encryption: request a datakey, encrypt the payload locally with the plaintext key, store the ciphertext key alongside the data, and wipe the plaintext key from memory after use.
8. For signed payloads (HMAC or signing keys), produce signatures through Vault and validate against `transit/verify/<key>`; reject any payload whose signature does not verify.
9. Enable `rotation_period` on the key and wire a monitoring check that alerts when the active version age exceeds the agreed threshold.
10. Export audit logs to the SIEM and trigger SOAR workflows for events such as unexpected decrypt failures, root token use, or seal transitions; reference the [Vault Audit Log Shipping Playbook](VAULT_AUDIT_LOG_SHIPPING_PLAYBOOK.md) for delivery details.
11. Drill key compromise on a regular cadence: bump `min_decryption_version` to block the suspect version, issue a new version, and re-wrap downstream data with the new key.
12. Document the integration, link the runbook from the service catalog, and hand over to security operations with a signed acceptance form.

## Rollback
If a rotation is rolled back, re-enable the previous key version, decrypt affected records with the new key, and re-encrypt with the rolled-back version once compromise is contained. If compromise is suspected to be active, rotate the root token, re-seal the cluster, revoke all active leases, and follow the incident response playbook before re-enabling service to downstream consumers.

## References
- [HashiCorp Vault Version Governance](../reference/VAULT_VERSION_GOVERNANCE.md)
- [Vault Audit Log Shipping Playbook](VAULT_AUDIT_LOG_SHIPPING_PLAYBOOK.md)
- [HashiCorp Vault Transit Secret Engine Version Governance](../reference/VAULT_TRANSIT_VERSION_GOVERNANCE.md)
