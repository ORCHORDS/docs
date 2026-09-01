---
title: "API Priority and Fairness Tuning"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# API Priority and Fairness Tuning

## API semantics

APF uses `flowcontrol.apiserver.k8s.io/v1` `FlowSchema` and `PriorityLevelConfiguration`. FlowSchemas are evaluated by ascending `matchingPrecedence`; the first match wins. `distinguisherMethod` separates flows by user or namespace. Rules match subjects plus resource or non-resource requests. Priority levels are `Exempt` or `Limited`; Limited uses `nominalConcurrencyShares`, `lendablePercent`, `borrowingLimitPercent`, and a `limitResponse` of `Reject` or `Queue`. Queuing uses `queues`, `handSize`, and `queueLengthLimit` for shuffle sharding.

## Minimal configuration

```yaml
apiVersion: flowcontrol.apiserver.k8s.io/v1
kind: PriorityLevelConfiguration
metadata: {name: batch-low}
spec:
  type: Limited
  limited:
    nominalConcurrencyShares: 10
    lendablePercent: 50
    limitResponse:
      type: Queue
      queuing: {queues: 64, handSize: 8, queueLengthLimit: 50}
---
apiVersion: flowcontrol.apiserver.k8s.io/v1
kind: FlowSchema
metadata: {name: batch-jobs}
spec:
  matchingPrecedence: 900
  priorityLevelConfiguration: {name: batch-low}
  distinguisherMethod: {type: ByUser}
  rules:
  - subjects: [{kind: Group, group: {name: batch.example}}]
    resourceRules:
    - verbs: ["*"]
      apiGroups: ["*"]
      resources: ["*"]
      namespaces: ["*"]
      clusterScope: true
```

## Ordering, versions, and edge cases

Do not edit mandatory `exempt` and `catch-all` behavior without understanding bootstrap objects. LIST requests consume seats according to estimated work; watch initialization and wide lists can dominate. APF protects API-server concurrency but cannot cure etcd, webhook, or network latency. Test rule matching because a lower numeric precedence unexpectedly captures traffic. Avoid broad Exempt classification.

## Deployment, evidence, and rollback

Observe `apiserver_flowcontrol_current_executing_requests`, `...current_inqueue_requests`, `...request_wait_duration_seconds`, `...rejected_requests_total`, `...dispatched_requests_total`, and seat utilization by priority level and flow schema. Load a noisy identity while checking node leases and controller reconciliation. Roll back by restoring previous objects; deleting a custom FlowSchema sends requests to the next match, often catch-all, so test that behavior before removal.

Preserve the applied object, server version, server-side dry-run result, relevant events or audit records, and the exact rollback object. Test both acceptance and rejection. Re-run after Kubernetes minor upgrades because API defaults, feature state, and policy tables can change even when manifests still decode.

## Classification tests

Use authenticated test identities for each FlowSchema subject type: User, Group, and ServiceAccount. Verify namespaced and cluster-scoped resource rules independently; `clusterScope: true` does not mean all namespaces. Non-resource rules are separate. Check the selected priority level in APF metrics while issuing GET, LIST, WATCH, and mutating traffic.

Queue geometry is a trade-off: more queues improve isolation, larger hand size reduces collision probability but spreads a flow across more queues, and queue length increases tolerated bursts while increasing worst-case delay. Reject mode returns HTTP 429 when the concurrency limit is reached; clients need bounded backoff. Watch for borrowing that starves a donor level and for low-share flows that never dispatch. Preserve bootstrap APF objects and their `autoupdate-spec` annotation behavior. On rollback, apply the previous FlowSchema precedence and priority allocation together to avoid a transient misclassification.

## Sources

- [APF](https://kubernetes.io/docs/concepts/cluster-administration/flow-control/)
- [API](https://kubernetes.io/docs/reference/kubernetes-api/cluster-resources/flow-schema-v1/)
