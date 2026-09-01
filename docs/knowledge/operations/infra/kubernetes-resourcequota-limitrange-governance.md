---
title: "ResourceQuota and LimitRange Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# ResourceQuota and LimitRange Governance

## API semantics

`ResourceQuota.spec.hard` limits aggregate namespace resources and object counts; status reports `hard` and `used`. Keys include `requests.cpu`, `requests.memory`, `limits.cpu`, `limits.memory`, `requests.storage`, `requests.ephemeral-storage`, `pods`, and `count/<resource>.<group>`. `scopes` and `scopeSelector` can target classes such as BestEffort, NotBestEffort, Terminating, NotTerminating, PriorityClass, or CrossNamespacePodAffinity. `LimitRange.spec.limits` has types Container, Pod, PersistentVolumeClaim, and supported fields `min`, `max`, `default`, `defaultRequest`, and `maxLimitRequestRatio`.

## Minimal configuration

```yaml
apiVersion: v1
kind: ResourceQuota
metadata: {name: compute, namespace: team-a}
spec:
  hard:
    requests.cpu: "20"
    requests.memory: 40Gi
    limits.cpu: "40"
    limits.memory: 80Gi
    pods: "100"
---
apiVersion: v1
kind: LimitRange
metadata: {name: container-defaults, namespace: team-a}
spec:
  limits:
  - type: Container
    defaultRequest: {cpu: 100m, memory: 128Mi}
    default: {cpu: 500m, memory: 512Mi}
    min: {cpu: 10m, memory: 32Mi}
```

## Ordering, versions, and edge cases

If quota covers CPU or memory requests/limits, admission can require those fields; LimitRange defaults are applied before quota accounting. Defaults may change QoS and cause throttling or OOMs, so inspect the persisted Pod. Quota is admission-time accounting, not node reservation. A quota may also constrain PriorityClass-scoped workloads. Multiple LimitRanges can produce non-obvious defaults; keep one governed policy per type where possible.

## Deployment, evidence, and rollback

Use `kubectl describe quota -n team-a` and `kubectl get resourcequota -o json` for hard/used. Create boundary and over-quota Pods and PVCs, and watch `FailedCreate` events with `exceeded quota` or LimitRange messages. Compare scheduler Pending, container throttling, and OOM events. Roll back hard values before removing defaults if existing deployment maxima depend on them; deleting quota immediately removes the aggregate guard.

Preserve the applied object, server version, server-side dry-run result, relevant events or audit records, and the exact rollback object. Test both acceptance and rejection. Re-run after Kubernetes minor upgrades because API defaults, feature state, and policy tables can change even when manifests still decode.

## Accounting tests

Quota usage updates asynchronously in status but admission uses the quota evaluator; do not infer a bypass from a briefly stale display. Test controller bursts because a Deployment can be accepted while ReplicaSet Pod creation fails. Object-count quota protects control-plane storage but can block cleanup workflows that create replacement objects first. StorageClass-scoped quota keys and extended-resource requests require exact documented key forms.

Inspect the admitted Pod to identify LimitRange defaults before comparing quota usage. CPU default limits can cause CFS throttling; memory defaults can trigger OOM kills; neither outcome appears as quota denial. Calculate a namespace's autoscaler maximum against quota and leave headroom for surge Pods and incident tooling. Monitor `resource_quota_controller` behavior through controller-manager health plus `FailedCreate` events. Roll back gradually: raise hard limits or remove a problematic minimum first, validate pending controllers recover, and only then decide whether to delete the policy object.

## Sources

- [Quota](https://kubernetes.io/docs/concepts/policy/resource-quotas/)
- [LimitRange](https://kubernetes.io/docs/concepts/policy/limit-range/)
