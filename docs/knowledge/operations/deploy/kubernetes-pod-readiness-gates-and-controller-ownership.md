# Kubernetes Pod readiness gates and controller ownership

**Issue:** Container readiness can become true before an external dependency, network attachment, load balancer, or policy controller has finished preparing the Pod.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Pod `readinessGates` add custom conditions to the kubelet's readiness decision. A Pod is Ready only when its containers are ready and every named readiness-gate condition is true. A missing custom condition defaults to false.

Use a dedicated controller to patch the Pod status subresource for the condition it owns. Define the condition type as a qualified label key and make updates idempotent, generation-aware where applicable, and observable.

## Operational controls

- Assign one clear controller as writer for each custom condition.
- Grant only the RBAC needed to read Pods and patch status.
- Define timeout, failure, and controller-outage behavior; fail-closed readiness can halt a rollout indefinitely.
- Keep readiness separate from liveness to avoid restart loops.
- Emit condition reason, message, and transition time useful for diagnosis.
- Ensure deletion and replacement do not leave stale external registration.

## Verification

1. Create a Pod with the condition absent and confirm it remains not Ready.
2. Set the condition true and confirm Service endpoint eligibility changes.
3. Revoke the condition and verify traffic drains as intended.
4. Stop the controller and exercise timeout and alert behavior.
5. Test rapid Pod replacement and stale external state cleanup.

## Sources

- [Kubernetes: Pod Conditions](https://kubernetes.io/docs/concepts/workloads/pods/pod-condition/)
- [Kubernetes API: PodReadinessGate](https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.35/#podreadinessgate-v1-core)
