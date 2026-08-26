# Kubernetes kube-proxy nftables-mode migration

**Issue**

The nftables kube-proxy backend has different minimum kernel, compatibility, cleanup, and packet-processing behavior from iptables mode.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Validate Kubernetes, kernel, and nft versions on every node pool.
- Canary a node pool and drain workloads according to disruption budgets.
- Test service types, session affinity, source ranges, dual stack, and network-policy interaction.
- Keep explicit rollback and stale-rule cleanup procedures; do not mix ad hoc host nftables edits with managed chains.

## Verification

1. Continuously probe ClusterIP, NodePort, LoadBalancer, hairpin, and externalTrafficPolicy paths.
2. Compare rule-update latency and CPU at production service scale.
3. Reboot and roll back canary nodes and verify no stale rules retain traffic.

## Gotchas

- Host firewall nftables support does not establish kube-proxy backend support.
- Mixed backends complicate diagnosis.
- Rule syntax is implementation detail, not an automation API.

## Official source

- [Official documentation](https://kubernetes.io/docs/reference/networking/virtual-ips/#nftables-proxy-mode)
