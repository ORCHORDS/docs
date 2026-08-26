# Kubernetes topology spread: minimum domains and eligible-node semantics

**Issue:** A workload appears zone-spread in normal conditions but becomes concentrated or unschedulable when affinity, taints, or a zone outage changes the eligible-node set.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Use topology spread constraints with an explicit availability objective. Set `minDomains` only with `DoNotSchedule`, and choose node-affinity and taint inclusion policies deliberately so the scheduler calculates skew against the nodes the Pod can actually use.

## Key semantics

A topology domain is a node-label key/value grouping, such as a zone. When eligible domains are fewer than `minDomains`, Kubernetes uses zero as the global minimum for skew calculation. The eligibility calculation is influenced by node affinity/selectors and taints according to the configured inclusion policies.

## Rollout checklist

1. Verify topology labels on every schedulable node and avoid mixing inconsistent label vocabularies.
2. Match only the workload replicas meant to be balanced; inspect selectors and rollout labels.
3. Select `DoNotSchedule` when the availability constraint is hard, and test the capacity consequence.
4. Set `minDomains` from the number of failure domains required for the service objective.
5. Confirm the Kubernetes-version support and default behavior for `matchLabelKeys`, affinity policy, and taint policy.
6. Run node, zone, and autoscaler simulations and confirm both placement and recovery behavior.

## Guardrails

- `ScheduleAnyway` optimizes skew but does not guarantee resilience.
- A strict spread rule can block releases when capacity or labels are incomplete.
- The eligible-domain calculation—not simply the number of zones in the cluster—governs the outcome.
- Inspect real scheduled Pods after every major label, taint, affinity, or autoscaler change.

## Sources

- [Kubernetes: Pod topology spread constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/)
