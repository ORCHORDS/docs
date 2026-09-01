---
title: "PodDisruptionBudget Availability Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# PodDisruptionBudget Availability Governance

## API semantics

`policy/v1` `PodDisruptionBudget` selects pods and sets exactly one of `minAvailable` or `maxUnavailable`, as integer or percentage. For percentages Kubernetes rounds up, so `maxUnavailable: 30%` can permit one disruption for a single replica. In policy/v1 an empty selector `{}` selects all pods in the namespace; this differs from the removed policy/v1beta1 behavior. Status includes `currentHealthy`, `desiredHealthy`, `expectedPods`, `disruptionsAllowed`, `disruptedPods`, and `observedGeneration`. The Eviction subresource respects PDBs; direct Pod DELETE does not.

## Minimal configuration

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: {name: api, namespace: shop}
spec:
  maxUnavailable: 1
  unhealthyPodEvictionPolicy: IfHealthyBudget
  selector:
    matchLabels: {app.kubernetes.io/name: api}
```

## Ordering, versions, and edge cases

`unhealthyPodEvictionPolicy` is stable from v1.31; `IfHealthyBudget` is default, while `AlwaysAllow` permits eviction of Running but unready pods and can unblock drains. PDBs protect voluntary disruptions, not node loss, OOM, involuntary eviction, or rollout deletion. Align selector with controller labels, replica minimum, topology, readiness semantics, Deployment `maxUnavailable`, and application quorum. Overlapping PDBs can make eviction satisfy all budgets and become unexpectedly restrictive.

## Deployment, evidence, and rollback

Run `kubectl get pdb -n shop -o wide`, verify `observedGeneration`, then `kubectl drain NODE --ignore-daemonsets` in a canary. Events and drain errors show HTTP 429 eviction refusals. Test healthy, unready, minimum-replica, rollout, and autoscaler-minimum states. Roll back by restoring the former budget; emergency deletion permits disruption immediately, so require approval and capture service health before and after.

Preserve the applied object, server version, server-side dry-run result, relevant events or audit records, and the exact rollback object. Test both acceptance and rejection. Re-run after Kubernetes minor upgrades because API defaults, feature state, and policy tables can change even when manifests still decode.

## Eviction calculations

For `minAvailable`, desired healthy derives from the selected controller's expected scale where Kubernetes can identify it; unmanaged or mismatched pods create difficult status. For `maxUnavailable`, use it with pods controlled by a scalable controller. Verify owner references and selector cardinality rather than assuming label count equals expected pods. A pod counts healthy when Ready according to PDB logic, so readiness gates and slow startup directly reduce `disruptionsAllowed`.

Exercise the `/api/v1/namespaces/{namespace}/pods/{name}/eviction` subresource using `policy/v1` and observe 201 success or 429 TooManyRequests. Node drain retries eviction; a permanently zero allowance is an operational deadlock, not proof of availability. Test machine maintenance while a rollout and autoscaling event occur. Capture PDB status before every override. After emergency deletion or relaxation, restore the object, wait for `observedGeneration`, and verify quorum and topology before continuing drain.

## Sources

- [PDB](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
- [Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)
