# Kubernetes KEDA Event-Driven Autoscaling

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Standard Kubernetes HPA (HorizontalPodAutoscaler) scales on CPU
and memory only. Queue-backed workers spin idle replicas during
off-hours while simultaneously failing to burst fast enough when
messages arrive in a spike. The result is wasted compute and
occasional processing lag.

## Context

KEDA (Kubernetes Event-Driven Autoscaling) installs as a set of
CRDs and a controller that replaces the HPA's metric source with
external event sources: HTTP request rate, message-queue depth,
Prometheus metrics, and more. KEDA creates and owns the HPA
object on behalf of the operator; both must not be managed
simultaneously.

This entry covers the `ScaledObject` CRD, the HTTP and Queue-
depth scalers, scale-to-zero (`minReplicaCount: 0`), cooldown
tuning, the Prometheus scaler, and the HPA ownership contract.

KEDA version: 2.15. Kubernetes: 1.31+.

## 1. Installing KEDA

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm repo update

helm install keda kedacore/keda \
  --namespace keda \
  --create-namespace \
  --version 2.15.0 \
  --set watchNamespace=""   # watch all namespaces
```

Verify the controller and metrics-apiserver pods are running:

```bash
kubectl get pods -n keda
# keda-operator-...              1/1  Running
# keda-operator-metrics-...      1/1  Running
```

## 2. ScaledObject: Queue-Depth Scaler

The following example scales a Cloudflare Queue consumer based on
approximate message depth exposed through a custom Prometheus
metric (`cloudflare_queue_depth`):

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: queue-worker-scaler
  namespace: example project
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: queue-worker

  # 0 = scale to zero when idle
  minReplicaCount: 0
  maxReplicaCount: 20

  # Seconds to wait after last event before scaling down
  cooldownPeriod: 120

  # Seconds between metric polls
  pollingInterval: 15

  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.monitoring.svc:9090
        metricName: cloudflare_queue_depth
        query: |
          cloudflare_queue_depth{queue="example project-jobs"}
        # Scale up 1 replica per 50 messages
        threshold: "50"
```

`cooldownPeriod` prevents thrashing when the queue empties
briefly between bursts. Set it to at least 2x the average message
processing time.

## 3. ScaledObject: HTTP Scaler

The KEDA HTTP Add-on enables HTTP-based scale-to-zero. Traffic
is intercepted by an ingress-level proxy that holds requests
while the first replica starts:

```yaml
# Requires: helm install http-add-on kedacore/keda-add-ons-http
apiVersion: http.keda.sh/v1alpha1
kind: HTTPScaledObject
metadata:
  name: api-http-scaler
  namespace: example project
spec:
  hosts:
    - example project-api.internal
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: example project-api
    service: example project-api-svc
    port: 8080
  replicas:
    min: 0
    max: 10
  scaledownPeriod: 90
  targetPendingRequests: 100
```

`targetPendingRequests` drives scale-out: one replica is added
for each additional 100 concurrent in-flight requests beyond the
current capacity.

## 4. HPA Interaction and Ownership

KEDA creates a `HorizontalPodAutoscaler` object when a
`ScaledObject` is applied. Do not create a separate HPA for the
same Deployment:

```
+--------------------+       owns       +------------------+
|   ScaledObject     |  ------------->  |       HPA        |
| (keda.sh/v1alpha1) |                  | (autoscaling/v2) |
+--------------------+                  +------------------+
         |                                       |
         | watches                               | controls
         v                                       v
  External metric              +-----------------------------+
  source (Prometheus,          |       Deployment replicas    |
  queue depth, HTTP)           +-----------------------------+
```

Verify KEDA owns the HPA after applying a ScaledObject:

```bash
kubectl get hpa -n example project
# NAME                            REFERENCE            ...
# keda-hpa-queue-worker-scaler    Deployment/queue-...

kubectl describe hpa keda-hpa-queue-worker-scaler -n example project \
  | grep "Controlled By"
# Controlled By: ScaledObject/queue-worker-scaler
```

## 5. Prometheus Metrics Scaler: Custom Lag Metric

For fine-grained autoscaling based on processing lag rather than
queue depth, expose a lag gauge from the worker and scale on it:

```yaml
# Worker exposes: job_processing_lag_seconds (gauge)
triggers:
  - type: prometheus
    metadata:
      serverAddress: http://prometheus.monitoring.svc:9090
      metricName: job_processing_lag_seconds
      query: |
        max(job_processing_lag_seconds{
          namespace="example project"
        })
      # Scale up when lag exceeds 30 seconds
      threshold: "30"
      # Ignore when metric is absent (queue empty)
      ignoreNullValues: "true"
```

Combine with the queue-depth trigger using `triggers` as a list.
KEDA scales to the maximum replica count demanded by any single
trigger.

## Anti-patterns

- Creating a manual `HorizontalPodAutoscaler` for a Deployment
  that already has a `ScaledObject`. The two controllers fight
  over the replica count.
- Setting `minReplicaCount: 0` without the HTTP Add-on for user-
  facing services. Requests during cold start return 503 unless
  a proxy holds them.
- Using extremely short `pollingInterval` (< 5 s) with Prometheus
  queries that are expensive to evaluate. This can overload the
  Prometheus server under high cardinality.
- Forgetting `ignoreNullValues: "true"` when a metric disappears
  on an empty queue; KEDA will treat the missing metric as an
  error and log noise.

## Gotchas

- Deleting a `ScaledObject` does not delete the HPA it created.
  Clean up manually with `kubectl delete hpa <name>`.
- Scale-to-zero means the first request after idle suffers cold-
  start latency (pod scheduling + container pull). Set a PDB
  (`PodDisruptionBudget`) on always-on services even when using
  KEDA to protect against node drains during active scaling.
- KEDA 2.x requires `autoscaling/v2` HPA support; Kubernetes
  1.25+ satisfies this out of the box.

## Verification

```bash
# Inspect ScaledObject status
kubectl describe scaledobject queue-worker-scaler -n example project

# Watch replica count change in real time
kubectl get deployment queue-worker -n example project -w

# Manually trigger a scale event by injecting Prometheus metric
# or publishing messages to the queue, then observe:
kubectl get hpa -n example project -w
```

## Related

- `cloudflare-queues-consumer-worker.md`
- `prometheus-custom-metrics-adapter.md`
- `kubernetes-pod-disruption-budgets.md`

## Source URLs (verified 2026-08-17)

- https://keda.sh/docs/2.15/concepts/scaling-deployments/
- https://keda.sh/docs/2.15/scalers/prometheus/
- https://github.com/kedacore/http-add-on
- https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/
- https://keda.sh/docs/2.15/operate/cluster/
