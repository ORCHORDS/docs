---
title: "HashiCorp Boundary Secure Access Version Governance"
owner: "Knowledge Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-08"
review-cycle: "180 days"
next-review: "2027-03-07"
source: "HashiCorp Boundary project documentation and Boundary release notes"
---

# HashiCorp Boundary Secure Access Version Governance

HashiCorp Boundary delivers identity-based secure access for dynamic infrastructure without exposing the network perimeter. This card governs version selection, integration boundaries, and the operational impact of upgrade decisions across self-hosted and managed deployments.

## Architecture

Boundary separates a control plane (controllers) from a data plane (workers). HCP Boundary operates the controllers as a managed service; self-hosted deployments run controllers inside the user's environment for production or regulated use. Workers always run close to the targets they expose. Both controllers and workers authenticate every connection with mTLS-bound, time-bound gRPC sessions that minimize standing credentials across dev, test, and production tiers.

## Core Resources

Scopes organize tenants, projects, and orgs hierarchically. Targets represent an addressable endpoint plus the policy applied to it. Host catalogs group hosts; host sets subset them by attribute filters, allowing elastic target membership without re-registration when cloud workloads scale.

## Credential Brokering

Credential stores broker secrets from external vaults, including HashiCorp Vault and AWS Secrets Manager. Credential libraries expose static or dynamic credentials, including short-lived database roles and cloud IAM credentials, so targets never see plaintext secrets.

## Authentication

Boundary supports OIDC, SAML, LDAP, and password auth methods. OIDC is the recommended primary; LDAP bridges legacy directories; SAML covers federated enterprise identity; password is permitted only for dev/test environments.

## Session Recording

Sessions may be recorded to AWS S3, Azure Blob, GCP GCS, MinIO, or the local filesystem. Backend choice affects retention policy, encryption keys, regulatory compliance posture, and egress cost.

## Worker Remote Access

Workers proxy TCP, SSH, RDP, and HTTP/Kubernetes targets. Protocol-relative connectivity removes static SSH bastions and VPN concentrators from the data path, replacing them with identity-aware proxies.

## KMS for Session Encryption

AWS KMS, GCP KMS, and Azure Key Vault encrypt session credentials at rest. KMS choice is independent of the session-recording backend and must align with the organization's primary cloud to satisfy key custody rules.

## Compatibility Horizon

Boundary tracks N-1 minor support. Each release notes deprecated APIs and removed feature flags. Pin controllers and workers to a single minor line and roll forward together to avoid protocol mismatches.

## Version Selection Decision Tree

Self-hosted vs HCP: choose HCP unless regulatory or network-isolation mandates self-hosting. KMS: pick the KMS native to the primary workload cloud. Recording backend: pick the object store native to the same cloud, or MinIO for air-gapped sites. Protocols: include only TCP, SSH, RDP, and Kubernetes ingress actually required.

## Operational Impact

Upgrades rotate worker tokens and re-establish gRPC sessions. Recording-backend changes require dual-write windows. KMS key rotation invalidates in-flight session credentials and forces re-authentication for active users.

## Cross-references

- Vault Version Governance: `docs/knowledge/reference/VAULT_VERSION_GOVERNANCE.md:1`
- Cloud KMS Reference: `docs/knowledge/reference/CLOUD_KMS_REFERENCE.md:1`
- Zero Trust Network Access Overview: `docs/knowledge/reference/ZTNA_OVERVIEW.md:1`

---
This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
