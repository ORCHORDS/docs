# kubernetes-horizontal-pod-autoscaler

**Issue:** Configuring HPA for CPU, memory, and custom metrics-based autoscaling
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Static replica counts waste money at low traffic and cause outages at peaks. HPA adjusts replicas dynamically. Requires metrics-server for CPU/memory; KEDA or Prometheus Adapter for custom metrics.

## Pattern / Solution
CPU-based HPA (v2):
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: myapp-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  minReplicas: 2
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: AverageValue
        averageValue: 512Mi
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300   # prevent flapping
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 30
      policies:
      - type: Pods
        value: 4
        periodSeconds: 60
```

KEDA ScaledObject for queue depth:
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: myapp-scaler
spec:
  scaleTargetRef:
    name: myapp
  minReplicaCount: 0   # scale to zero when idle
  maxReplicaCount: 50
  triggers:
  - type: rabbitmq
    metadata:
      queueName: tasks
      host: amqp://rabbitmq:5672
      queueLength: "20"
```

Check HPA status:
```bash
kubectl get hpa myapp-hpa -o yaml
kubectl describe hpa myapp-hpa   # shows current metrics and events
```

## Gotchas
- HPA requires CPU/memory *requests* set on containers; without them, utilization cannot be computed
- HPA and VPA should not both control the same deployment's replicas — conflict causes thrashing
- Scale-to-zero with KEDA requires the deployment to have `minReplicas: 0`; standard HPA minimum is 1
- Stabilization window defaults differ between scale-up (0s) and scale-down (300s) — tune aggressively for batch workloads
- `averageUtilization` is computed against the *requested* CPU, not node capacity

## Related
- `kubernetes-vertical-pod-autoscaler.md`
- `kubernetes-resource-limits.md`
- `load-testing-before-deploy.md`
