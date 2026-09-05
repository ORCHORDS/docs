---
title: HashiCorp Vault Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: HashiCorp Vault documentation; HashiCorp; BSL 1.1 (since 1.15); Vault changelog
---

# HashiCorp Vault Version Governance

## Scope

This card governs how `orchords-docs` evaluates HashiCorp Vault across versions, storage backends, and integration patterns. It is the reference input for any KB card that touches secret management, PKI, transit encryption, or dynamic credentials.

## Why this card exists

Vault is the canonical secret-management platform. Since 1.15 (2023), HashiCorp Vault ships under the Business Source License (BSL) 1.1, restricting direct commercial resale of the open-source binary. Without an explicit card, the KB cites Vault versions that ignore license changes and the OpenBao / Vault community fork.

## Versions

| Version | Status |
|---|---|
| 0.10–1.4 | legacy |
| 1.5–1.9 | MPL-2.0 era |
| 1.10–1.14 | MPL-2.0 era (final) |
| 1.15+ | BSL 1.1 |
| OpenBao 2.0+ | MPL-2.0 community fork |

References: `https://github.com/hashicorp/vault/releases`.

## License policy

- **Pre-1.15 (MPL-2.0)** — permitted for all use cases.
- **1.15+ (BSL 1.1)** — permitted for self-hosted, non-competing use.
- **OpenBao** — MPL-2.0 fork, recommended for BSL-restricted environments.

## Storage backends

| Backend | Status |
|---|---|
| Integrated Raft | recommended (HA) |
| Consul | deprecated (since 1.12) |
| ZooKeeper | unsupported |
| Etcd | unsupported |
| Filesystem | dev only |

References: `https://developer.hashicorp.com/vault/docs/configuration/storage`.

## Seal / unwrap

| Seal | Use |
|---|---|
| Shamir | default; unseal by N-of-M key shares |
| AWS KMS | production (single-region) |
| Azure Key Vault | production (Azure) |
| GCP CKMS | production (GCP) |
| HSM PKCS#11 | production (FIPS-validated) |
| Transit | auto-unseal via Vault Transit |

References: `https://developer.hashicorp.com/vault/docs/configuration/seal`.

## Secret engines

| Engine | Use |
|---|---|
| KV v1 / v2 | static secrets |
| Database | dynamic DB credentials |
| PKI | short-lived X.509 |
| Transit | encrypt/decrypt/sign/verify |
| SSH | dynamic SSH credentials |
| AWS / GCP / Azure | dynamic cloud creds |
| TOTP | one-time passwords |
| Identity | aliasing between auth methods |

References: `https://developer.hashicorp.com/vault/docs/secrets`.

## Auth methods

| Method | Use |
|---|---|
| Token | direct |
| Userpass | username/password |
| LDAP / OIDC / SAML | federation |
| Kubernetes | service-account JWT |
| AWS / GCP / Azure | IAM / workload identity |
| AppRole | machine-to-machine |
| GitHub | GitHub PAT |

References: `https://developer.hashicorp.com/vault/docs/auth`.

## Audit logging

Vault audit logs (JSON):

- Required for production.
- Stream to file, syslog, or socket.
- Ship via Filebeat / Vector to a SIEM.

References: `https://developer.hashicorp.com/vault/docs/audit`.

## Cross-reference

| Domain | Card |
|---|---|
| Kubernetes | `KUBERNETES_VERSION_GOVERNANCE.md` |
| IAM | `OAUTH_2_1_VERSION_GOVERNANCE.md` |
| PKI | (deferred) |
| OpenBao | `OPENBAO_VERSION_GOVERNANCE.md` (deferred) |

## Sources

- Vault documentation: `https://developer.hashicorp.com/vault/docs`
- Vault releases: `https://github.com/hashicorp/vault/releases`
- Vault changelog: `https://github.com/hashicorp/vault/blob/main/CHANGELOG.md`
- OpenBao: `https://openbao.org/`
