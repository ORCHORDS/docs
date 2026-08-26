# Kubernetes NetworkPolicy default-deny egress and DNS allowance

**Issue:** A namespace adopts default-deny egress, then workloads fail unpredictably because DNS, required in-cluster services, or explicit outbound dependencies were never allowlisted.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Start namespaces with explicit ingress and egress isolation, then add the smallest allow rules required by acceptance tests. A NetworkPolicy is only enforced when the selected network plugin implements it; verify enforcement in the actual cluster.

**Source:** [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)

## Rollout

1. Inventory each workload’s inbound callers, DNS resolver, in-cluster services, and external dependencies.
2. Apply default-deny ingress and egress in a non-production namespace.
3. Add an explicit DNS egress rule to the cluster DNS service and explicit rules for each required dependency.
4. Test application readiness, service discovery, metrics, certificate validation, and failure paths.
5. Promote with policy-as-code review and alerts for denied traffic.

## Verification

- a pod with no matching allow policy cannot reach arbitrary destinations;
- DNS resolution works only through the intended resolver;
- required in-cluster traffic is permitted by label/namespace and port, not broad CIDRs;
- policy enforcement is confirmed by the CNI and an observed blocked connection;
- a newly added dependency fails safely until its rule is reviewed and added.

## Gotchas

- A default-deny egress policy blocks DNS unless an explicit DNS allowance is provided.
- Multiple NetworkPolicies combine additively; a broad allow in any matching policy can defeat intended isolation.
- Standard NetworkPolicy rules do not match DNS names directly; use a compatible policy engine or controlled egress gateway where hostname policy is required.
- Do not use a blanket `0.0.0.0/0` allow merely to restore a broken rollout.

## Related

- `deploy/kubernetes-namespace-isolation.md`
- `infra/kubernetes-network-policies-service-mesh.md`
- `security/zero-trust-network.md`
