# kubernetes-resource-limits

**Issue:** Setting CPU and memory requests/limits correctly to avoid OOMKill, CPU throttling, and noisy-neighbour evictions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Under-specified limits allow one pod to consume all node resources and starve neighbours. Over-specified limits waste cluster capacity. OOMKilled pods and CPU-throttled services are the most common performance issues traced back to wrong resource settings.

## Pattern / Solution
**Requests vs. limits**
- `requests`: what the scheduler uses to place the pod; guaranteed minimum
- `limits`: hard ceiling; exceeding memory limit → OOMKill; exceeding CPU limit → throttle (not kill)

**Recommended starting values (tune from metrics)**
```yaml
resources:
  requests:
    cpu: "250m"     # 0.25 vCPU — start conservative
    memory: "256Mi"
  limits:
    cpu: "1000m"    # 1 vCPU — allow burst
    memory: "512Mi" # hard cap — set 2× the P95 observed usage
```

**CPU: do not set limits equal to requests**
Setting `cpu.limits = cpu.requests` causes throttling at any burst above the request value, even when the node has spare capacity. CPU is compressible — throttling is usually better than crash, but aggressive limits harm latency.

**Memory: set limits 20-50% above P95 observed usage**
```bash
# Query P95 memory from Prometheus
max_over_time(
  container_memory_working_set_bytes{container="api"}[7d]
) by (pod)
```

**LimitRange (namespace default)**
```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
  namespace: prod
spec:
  limits:
    - type: Container
      default:
        cpu: "500m"
        memory: "256Mi"
      defaultRequest:
        cpu: "100m"
        memory: "128Mi"
```

**VPA (Vertical Pod Autoscaler) for automatic right-sizing**
```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: api-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  updatePolicy:
    updateMode: "Off"  # recommendation-only; don't auto-evict
```

## Gotchas
- OOMKilled exit code is 137 — check `kubectl describe pod` for `OOMKilled` reason, not just the exit code
- Pods without memory limits can be evicted during node memory pressure even if they are not over their request
- JVM and .NET runtimes often report available system memory, not container limits — pass `-Xmx` or `DOTNET_GCHeapHardLimit` explicitly
- Burstable QoS class (requests < limits) is evicted before Guaranteed (requests == limits) under node pressure

## Related
- `kubernetes-rolling-update.md`
- `kubernetes-readiness-liveness-probes.md`
- `infrastructure-cost-tagging.md`
