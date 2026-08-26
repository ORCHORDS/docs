# Kubernetes Autoscaling — HPA, VPA, and KEDA

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your Kubernetes workloads run at fixed replica counts — either
over-provisioned (wasting cost) or under-provisioned (degrading
performance during traffic spikes). CPU-based autoscaling responds too
slowly to queue-based workloads: a Kafka consumer falls behind because
HPA cannot see the queue depth. Event-driven workloads (webhooks, batch
jobs, cron processors) idle at minimum replicas during quiet periods,
consuming resources. You want to scale to zero during off-hours but
Kubernetes HPA requires a minimum of 1 replica.

## Context

Kubernetes provides three autoscaling mechanisms: Horizontal Pod
Autoscaler (HPA) scales replica count based on metrics, Vertical Pod
Autoscaler (VPA) adjusts resource requests/limits, and KEDA (Kubernetes
Event-Driven Autoscaling) extends HPA with 60+ external metric sources
and scale-to-zero capability. In 2026, most production clusters combine
multiple strategies: HPA for CPU/memory-bound workloads, KEDA for
event-driven workloads, and VPA for right-sizing resource requests.
KEDA is a CNCF graduated project and the standard for scaling based on
external metrics (message queues, database connections, HTTP request
rates, custom Prometheus queries).

## Autoscaler comparison

| Feature | HPA | VPA | KEDA |
|---|---|---|---|
| Scales | Replica count | CPU/memory requests | Replica count |
| Metrics | CPU, memory, custom | Historical usage | 60+ external sources |
| Scale to zero | No (min 1) | N/A | Yes |
| Use case | Steady HTTP traffic | Right-sizing pods | Event-driven workloads |
| Complexity | Low | Medium | Medium |
| Conflicts | Cannot combine with KEDA on same workload | Cannot combine with HPA | Cannot combine with HPA on same workload |

## HPA (Horizontal Pod Autoscaler)

### Basic CPU-based scaling

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-server
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Percent
          value: 50
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 25
          periodSeconds: 120
```

### Custom metrics (Prometheus)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-server
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Pods
      pods:
        metric:
          name: http_requests_per_second
        target:
          type: AverageValue
          averageValue: "100"
```

## KEDA (Event-Driven Autoscaling)

### Architecture

```
External metric source     KEDA              Kubernetes
┌──────────────┐          ┌──────────┐       ┌─────────┐
│ Kafka        │──────────│ Scaler   │──────►│ HPA     │
│ RabbitMQ     │──────────│          │       │ (auto-  │
│ Redis        │──────────│ Metrics  │       │ created)│
│ Prometheus   │──────────│ Server   │       └─────────┘
│ AWS SQS      │──────────│          │
│ Azure Queue  │──────────│ Scale-to │
│ HTTP         │──────────│ -zero    │
└──────────────┘          └──────────┘

KEDA creates and manages an HPA under the hood.
Do NOT create a separate HPA for the same workload.
```

### Kafka consumer scaling

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: order-processor
spec:
  scaleTargetRef:
    name: order-processor
  minReplicaCount: 0         # Scale to zero when no messages
  maxReplicaCount: 30
  cooldownPeriod: 300        # Wait 5 min before scaling down
  pollingInterval: 15        # Check metrics every 15s
  triggers:
    - type: kafka
      metadata:
        bootstrapServers: kafka:9092
        consumerGroup: order-processors
        topic: orders
        lagThreshold: "100"  # Scale up when lag > 100
```

### Prometheus query scaling

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: api-server
spec:
  scaleTargetRef:
    name: api-server
  minReplicaCount: 2
  maxReplicaCount: 50
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus:9090
        query: |
          sum(rate(http_requests_total{service="api"}[2m]))
        threshold: "500"
        activationThreshold: "10"
```

### Cron-based scaling

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: batch-processor
spec:
  scaleTargetRef:
    name: batch-processor
  triggers:
    - type: cron
      metadata:
        timezone: America/New_York
        start: 0 8 * * 1-5    # Scale up at 8am weekdays
        end: 0 18 * * 1-5     # Scale down at 6pm weekdays
        desiredReplicas: "10"
```

## VPA (Vertical Pod Autoscaler)

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: api-server
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server
  updatePolicy:
    updateMode: Auto           # Off, Initial, Auto
  resourcePolicy:
    containerPolicies:
      - containerName: api
        minAllowed:
          cpu: 100m
          memory: 128Mi
        maxAllowed:
          cpu: 2000m
          memory: 2Gi
```

## When to use each

```
HPA (CPU/memory):
  → Web servers, API endpoints
  → Steady request-driven workloads
  → When CPU correlates with load

KEDA (event-driven):
  → Message queue consumers (Kafka, RabbitMQ, SQS)
  → Batch processing jobs
  → Workloads that should scale to zero
  → Custom metric scaling (Prometheus, Datadog)

VPA (right-sizing):
  → Initial resource request tuning
  → Workloads with variable memory patterns
  → Combined with HPA (VPA adjusts requests, HPA adjusts replicas)
```

## Anti-patterns

- **HPA + KEDA on the same workload** — KEDA creates an HPA under
  the hood. Having both creates a conflict where two controllers
  fight over replica count, causing oscillation. Use one or the other.
- **Aggressive scale-down** — scaling down too quickly causes
  request failures during traffic fluctuations. Use stabilization
  windows (300s+ for scale-down) and percentage-based policies.
- **CPU-based scaling for queue consumers** — queue consumers are
  often CPU-idle while waiting for messages. CPU-based HPA will not
  scale up when the queue is deep. Use KEDA with queue lag metrics.
- **No resource requests** — HPA requires resource requests to
  calculate utilization percentages. Without requests, HPA cannot
  make scaling decisions. Always set CPU and memory requests.

## Gotchas

- **Scale-to-zero activation delay** — when KEDA scales to zero and
  a new event arrives, there is a cold-start delay (pod scheduling +
  container startup). For latency-sensitive workloads, set
  `minReplicaCount: 1` instead of 0.
- **VPA eviction** — VPA in `Auto` mode evicts and recreates pods
  to apply new resource requests. This causes brief availability
  disruptions. Use `Initial` mode for production workloads and apply
  VPA recommendations during planned maintenance.
- **HPA flapping** — if the target metric oscillates around the
  threshold, HPA rapidly scales up and down. Use stabilization
  windows and the `behavior` field to control scaling velocity.
- **Pod Disruption Budgets** — autoscaler scale-down respects PDBs.
  A PDB that blocks all evictions prevents scale-down. Ensure PDBs
  allow at least one pod eviction.

## Verification

- CPU-bound workloads use HPA with stabilization windows.
- Event-driven workloads use KEDA with appropriate triggers.
- VPA recommendations are reviewed and applied for resource tuning.
- Scale-down policies prevent aggressive replica reduction.
- Resource requests and limits are set on all containers.
- Autoscaler behavior is validated under load testing.

## Related

- `documentation/docs/policies/infra/iac-testing-terratest-checkov.md`
- `documentation/docs/policies/monitoring/alerting-strategy-routing-escalation.md`
- `documentation/docs/policies/performance/api-rate-limiting-algorithms.md`

## Source URLs (verified 2026-08-16)

- Kubernetes Autoscaling 2026: HPA, VPA, KEDA — https://devstarsj.github.io/2026/06/26/kubernetes-autoscaling-hpa-vpa-keda-2026/
- Kubernetes Autoscaling Patterns: HPA, VPA and KEDA — https://www.spectrocloud.com/blog/kubernetes-autoscaling-patterns-hpa-vpa-and-keda
- Modern Kubernetes Scaling: KEDA vs Native HPA — https://blogs.businesscompassllc.com/2026/06/modern-kubernetes-scaling-architectures.html
- KEDA vs HPA: Which Kubernetes Autoscaler to Use — https://www.plural.sh/blog/keda-vs-hpa-guide/
