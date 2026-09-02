# CNCF K3s Lightweight Cluster Governance

## Purpose

K3s (CNCF Sandbox, originally Rancher Labs) is a lightweight Kubernetes distribution packaged as a single binary under 100 MB, designed for edge, IoT, CI, and resource-constrained environments. The K3s governance pattern captures the install method (server, agent, HA), the embedded SQLite vs external datastore choice (etcd, PostgreSQL, MySQL), the disabled-default components list, and the upgrade procedure. Without explicit governance, K3s clusters drift from upstream Kubernetes defaults and miss required security hardening.

## Current context and source status

K3s 1.30 (released 2024), K3s 1.32 (released 2025), and K3s 1.34 (released 2026) are the current supported versions. The project follows the CNCF Sandbox governance model. K3s embeds SQLite (default), etcd, or supports external PostgreSQL/MySQL datastores.

## Governance pattern

1. Pin K3s version and channel (`stable`, `testing`) in the install script.
2. Use HA mode (3+ server nodes with embedded etcd or external datastore) for production.
3. Disable unused components (`--disable` flags for Traefik, ServiceLB, local-storage, cloud-controller) per environment.
4. Configure the datastore: SQLite (default, single-server only), embedded etcd, external PostgreSQL, or external MySQL.
5. Maintain TLS communication between server and agent with the auto-generated certificate authority.
6. Use the K3s secrets-encryption flag (`--secrets-encryption`) to encrypt secrets at rest.
7. Configure the K3s API server audit log and forward to a central collector.
8. Monitor K3s metrics: `k3s_*` metrics via the embedded metrics-server.
9. Maintain the upgrade procedure: drain server, upgrade, verify etcd quorum, proceed.
10. Document the rollback path: snapshot the datastore before upgrade, restore if upgrade fails.

## Validation and evidence

- K3s version and channel recorded in install script.
- HA configuration documented.
- Disabled-default components list recorded per environment.
- Datastore choice and configuration recorded.
- Secrets-encryption flag enabled and verified.
- Audit log forwarded to central collector.
- Rollback procedure tested in staging.

## Failure correction

Common defects include running SQLite in production (single-server, no HA), missing secrets-encryption, and using default Traefik when an alternative ingress is required. Corrective actions include enforcing HA configuration, enabling secrets-encryption, and disabling default Traefik in favor of the documented ingress.

## Limitations

- K3s is not feature-complete with upstream Kubernetes (for example, in-tree cloud providers are removed).
- SQLite is not recommended for HA or production.
- K3s does not bundle all upstream Kubernetes add-ons (for example, metrics-server is optional).
- K3s API server uses different default ports (6443 for API, 10250 for kubelet).

## Scope note

This knowledge article is part of the **operations** leaf. Sibling leaves cover: **platforms** (K3s deployment topology), **engineering** (K3s cluster bootstrap), **security** (secrets-encryption and audit log), and **templates** (K3s install script template). Use this article together with those siblings where the topic overlaps.

## Canonical sources

- K3s documentation (CNCF Sandbox): https://docs.k3s.io/
- K3s GitHub repository (CNCF Sandbox): https://github.com/k3s-io/k3s
- K3s architecture overview (CNCF Sandbox): https://docs.k3s.io/architecture

Sources were verified on September 1, 2026.