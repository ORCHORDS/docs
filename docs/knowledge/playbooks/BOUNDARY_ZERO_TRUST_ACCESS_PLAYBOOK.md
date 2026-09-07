# HashiCorp Boundary Zero-Trust Access Playbook

## Purpose
This playbook deploys HashiCorp Boundary to deliver identity-aware, brokered access to internal services and infrastructure without exposing a flat VPN. It establishes a zero-trust access tier that issues short-lived, role-bound credentials through Vault, terminates sessions through policy-controlled proxies, and produces an auditable trail of every connection. Credential brokering replaces static SSH keys and shared RDP passwords, and optional session recording captures operator activity for post-incident review and compliance evidence. The result is a single ingress path that enforces identity, authorization, and recording uniformly across clouds, regions, and on-premises estates.

## Audience
Platform engineers, security engineers, infrastructure operators, and IAM engineers who own the underlying target estates and consume the access tier on a daily basis.

## Pre-conditions
- HCP Boundary or self-hosted controllers with worker topology sized for HA.
- HashiCorp Vault clusters unsealed and reachable from controllers and workers.
- KMS integration available (AWS KMS, GCP KMS, or Azure Key Vault) for controller root key wrapping.
- Identity provider with OIDC (Okta, Entra ID, Google Workspace, Auth0) for human and workload authentication.
- Network peering or private connectivity from controllers and workers to every target host or service.
- Audit log destination (CloudWatch, Splunk, Datadog, Elastic) reachable over TLS.
- Session recording backend bucket (S3, GCS, Azure Blob, or MinIO) with lifecycle policy applied.
- Boundary Desktop client distributed to operator workstations.

## Procedure
1. Deploy controllers in HA across availability zones, with one active and at least one standby per region.
2. Deploy workers per region or VPC peering zone, then register each worker with the controllers over the public cluster URL.
3. Configure KMS for the controller so the root DEK is wrapped by an external key and escrow is verified.
4. Define the organisation project structure: create the org, then projects per environment (prod, staging, dev) and scopes per team or business unit.
5. Add a static or dynamic host catalog for targets, using cloud plugins where hosts churn frequently.
6. Build host sets that reference the catalog and filter by tags, accounts, or services.
7. Configure targets with protocol (TCP, SSH, RDP, HTTP) and the default port for each service.
8. Wire a Vault credential library for SSH and RDP credential brokering so Boundary issues ephemeral credentials on connect.
9. Configure OIDC authentication against the corporate IdP, including auth-method scopes and claim mapping to Boundary roles.
10. Apply session recording to sensitive targets with the defined storage backend, set retention, and restrict access to the security tenant.
11. Validate connect via the Boundary Desktop client against a non-production target, then promote to production.
12. Wire Boundary audit events to SIEM and SOAR (Security Orchestration Automation and Response) so anomalous sessions trigger automated response.
13. Hand over to platform operations with runbooks, alert routing, and on-call ownership confirmed.

## Rollback
Drain workers by removing them from the cluster, revoke all active sessions through the controller API, retain recorded sessions in immutable storage for forensics, then isolate the controllers at the network layer. Re-enable the previous bastion or VPN path before tearing down Boundary state so operators are never locked out. Preserve Boundary audit logs and Vault unwrap events for the incident record, and freeze any pending KMS root key rotation until the rollback is reviewed.

## References
- [HashiCorp Boundary Secure Access Version Governance](../reference/BOUNDARY_VERSION_GOVERNANCE.md)
- [HashiCorp Vault Version Governance](../reference/VAULT_VERSION_GOVERNANCE.md)
- [OAuth 2.1 Version Governance](../reference/OAUTH_2_1_VERSION_GOVERNANCE.md)