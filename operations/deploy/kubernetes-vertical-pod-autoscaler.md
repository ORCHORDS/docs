# kubernetes-vertical-pod-autoscaler

**Issue:** Using VPA to right-size container resource requests automatically
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers guess at CPU/memory requests, leading to chronic over-provisioning or OOMKills. VPA observes actual usage and recommends or applies correct requests, reducing wasted capacity.

## Pattern / Solution
Install VPA:
```bash
git clone https://github.com/kubernetes/autoscaler.git
cd autoscaler/vertical-pod-autoscaler
./hack/vpa-up.sh
```

VPA in recommendation-only mode (safe starting point):
```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: myapp-vpa
  namespace: production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  updatePolicy:
    updateMode: "Off"   # Off = recommend only, no restarts
  resourcePolicy:
    containerPolicies:
    - containerName: myapp
      minAllowed:
        cpu: 100m
        memory: 128Mi
      maxAllowed:
        cpu: "4"
        memory: 4Gi
```

Read recommendations:
```bash
kubectl describe vpa myapp-vpa
# Look for: Recommendation > Container Recommendations
```

Auto mode (applies changes via pod restarts):
```yaml
  updatePolicy:
    updateMode: "Auto"
```

## Gotchas
- `Auto` mode evicts pods to apply new requests — ensure PodDisruptionBudget limits simultaneous evictions
- VPA and HPA cannot both manage CPU/memory on the same deployment; use HPA for scaling, VPA for sizing, or use KEDA + VPA
- VPA requires at least 2 pods running for safe recommendations (single pod gives no baseline)
- Recommendations stabilize after ~24h of traffic; do not apply Auto mode on day one
- VPA ignores containers with `resources: {}` until at least some history is collected

## Related
- `kubernetes-horizontal-pod-autoscaler.md`
- `kubernetes-resource-limits.md`
- `performance-baseline-tracking.md`
