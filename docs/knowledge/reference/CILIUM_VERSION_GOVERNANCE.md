---
title: Cilium eBPF Networking, Security, and Observability Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-06
review-cycle: 180 days
next-review: 2027-03-05
source: Cilium documentation and release guidance
---

# Cilium eBPF Networking, Security, and Observability Version Governance

## Scope

This card governs version selection, upgrade sequencing, and compatibility review for Cilium in Kubernetes environments.

## Current release policy

As of 2026-09-06, Cilium maintains the latest three minor stable release branches. The maintained line is 1.20, 1.19, and 1.18.

Cilium 1.20.1 was released in August 2026. Production deployments SHOULD select the latest patch release available on their chosen maintained minor branch rather than pinning to an older patch.

## Upgrade rules

- Upgrade only between consecutive minor releases.
- Update to the latest patch of the current minor before moving to the next minor.
- Keep Cilium agents, operators, and supporting components on the same version during normal operation.
- Read the version-specific upgrade notes before changing a minor version.
- Treat L7 policy, Ingress, and Gateway API traffic as potentially disruptive during upgrades because proxy-backed connections can need to reconnect.
- Run the documented pre-flight checks before a minor upgrade.

## Feature governance

Cilium can provide:

- Kubernetes CNI networking.
- Kubernetes NetworkPolicy enforcement.
- CiliumNetworkPolicy and CiliumClusterwideNetworkPolicy.
- eBPF-based service load balancing.
- Hubble network-flow observability.
- Gateway API and ingress capabilities.
- Cluster Mesh for multi-cluster connectivity.
- Service-mesh capabilities without requiring a sidecar for every workload.

Feature enablement MUST be evaluated separately from version support. A supported Cilium version does not imply every optional feature is suitable for every cluster.

## Compatibility evidence

Before promotion, record:

1. Kubernetes version.
2. Linux kernel versions in the node pool.
3. Cilium minor and patch version.
4. Datapath mode and kube-proxy replacement setting.
5. Enabled Gateway API, Hubble, Cluster Mesh, and policy features.
6. Results of Cilium health and connectivity tests.

## Sources

- Cilium documentation: `https://docs.cilium.io/`
- Cilium upgrade guide: `https://docs.cilium.io/en/stable/operations/upgrade/`
- Cilium releases: `https://github.com/cilium/cilium/releases`
