# Kubernetes LimitedSwap node rollout

**Issue:** Turning on node swap changes eviction, latency, secret-at-rest, and memory-pressure behavior in ways that can destabilize workloads.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use Linux cgroup v2 nodes, set failSwapOn false only on labeled canaries, and select memorySwap.swapBehavior explicitly. Under LimitedSwap, understand that eligible Burstable containers receive swap proportional to their memory request; Guaranteed, BestEffort, high-priority, and request-equals-limit cases do not use it. Encrypt swap because tmpfs-backed Kubernetes data may reach disk.

## Verification

Stress eligible and ineligible QoS classes, measure major faults and p99 latency, verify memory.swap.max, test kubelet/runtime restart and disk exhaustion, and confirm eviction and OOM behavior during sustained pressure.

## Gotchas

- Pin and verify exact platform versions before rollout.
- Preserve reproducible diagnostics without secrets or personal data.
- Define rollback and stop conditions before production use.

## Official source

- [Primary documentation](https://kubernetes.io/docs/concepts/cluster-administration/swap-memory-management/)
