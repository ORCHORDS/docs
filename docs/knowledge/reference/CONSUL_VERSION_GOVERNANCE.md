---
title: HashiCorp Consul Service Mesh / Service Discovery Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: HashiCorp Consul documentation; HashiCorp; Consul 1.16+ (BSL 1.1)
---

# HashiCorp Consul Service Mesh / Service Discovery Version Governance

## Scope

This card governs how `orchords-docs` evaluates HashiCorp Consul across versions, deployment modes (standalone / client-server / cluster), and integration patterns (service discovery, K/V, service mesh).

## Why this card exists

Consul is the canonical service-discovery and service-mesh platform. Since 1.15 (2023), Consul ships under BSL 1.1. Without an explicit card, the KB cites Consul practices that ignore the license change and the Connect / Dataplane split.

## Versions

| Version | Status |
|---|---|
| 1.10–1.14 | MPL-2.0 era |
| 1.15+ | BSL 1.1 |
| 1.16+ | BSL 1.1 (current) |
| 1.17+ | BSL 1.1 (current) |
| 1.18+ | BSL 1.1 (current) |
| 1.19+ | BSL 1.1 (current) |

References: `https://github.com/hashicorp/consul/releases`.

## License policy

- **Pre-1.15 (MPL-2.0)** — permitted.
- **1.15+ (BSL 1.1)** — self-hosted permitted; competing SaaS forbidden.

## Deployment modes

| Mode | Use |
|---|---|
| Standalone | dev only |
| Client-server | production (typical) |
| Cluster (multi-server) | HA |
| Datacenter (multi-region) | federated |

References: `https://developer.hashicorp.com/consul/docs/architecture`.

## Core features

| Feature | Use |
|---|---|
| Service discovery | DNS / HTTP API |
| Health checking | TCP / HTTP / gRPC / TTL |
| K/V store | dynamic configuration |
| Service mesh (Connect) | mTLS via Envoy or built-in |
| ACL | access control |
| Sentinel | policy-as-code |

## Service mesh

Consul Connect:

- Sidecar mode (Envoy).
- Consul Dataplane (Consul 1.13+, replaces sidecar).
- Intentions: explicit ALLOW / DENY between services.
- Upstreams: per-service discovery.

References: `https://developer.hashicorp.com/consul/docs/connect`.

## Cross-reference

| Domain | Card |
|---|---|
| Service mesh | `ISTIO_VERSION_GOVERNANCE.md` |
| Vault | `VAULT_VERSION_GOVERNANCE.md` |
| Nomad | `NOMAD_VERSION_GOVERNANCE.md` (deferred) |

## Sources

- Consul documentation: `https://developer.hashicorp.com/consul/docs`
- Consul releases: `https://github.com/hashicorp/consul/releases`
- Consul changelog: `https://github.com/hashicorp/consul/blob/main/CHANGELOG.md`
