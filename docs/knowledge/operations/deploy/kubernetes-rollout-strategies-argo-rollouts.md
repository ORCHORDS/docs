# Kubernetes Rollout Strategies — Rolling Update, Blue-Green, Canary with Argo Rollouts

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your Kubernetes Deployment uses the default RollingUpdate strategy.
A new version ships with a subtle bug that only appears under load.
By the time monitoring detects the regression, all pods have been
replaced — rollback requires redeploying the previous image across
the entire fleet. You want to route 5% of traffic to the new
version first, but native Kubernetes rollouts cannot split traffic
by percentage — they only replace pods. Your team manually watches
dashboards during deploys because there is no automated analysis
to decide whether to promote or abort.

## Context

Native Kubernetes RollingUpdate replaces pods gradually via
`maxSurge` and `maxUnavailable` tunables but cannot split traffic
by percentage, run automated analysis, or gate promotion on metrics.
Argo Rollouts is a CRD-based controller that replaces the Deployment
resource with a `Rollout` CRD, adding blue-green and canary
strategies with traffic splitting (via Istio, NGINX, ALB, or
Gateway API), automated AnalysisRuns for metric-driven promotion or
rollback, and manual approval gates. Flagger is an alternative that
layers on top of standard Deployments without requiring manifest
migration.

## Native Kubernetes RollingUpdate

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1          # max pods above desired count
      maxUnavailable: 0    # zero-downtime pattern
```

```
maxSurge + maxUnavailable tunables:

  Both accept absolute numbers or percentages.

  Conservative (zero-downtime):
    maxSurge: 1, maxUnavailable: 0
    → One new pod created, verified ready, then one old removed

  Fast (trade safety for speed):
    maxSurge: 50%, maxUnavailable: 50%
    → Half the fleet replaced simultaneously

Limitations:
  → No traffic-percentage splitting
  → No automated metrics-based analysis
  → Rollback is all-or-nothing (kubectl rollout undo)
  → No pause/resume or manual approval gates
  → No true blue-green or canary support
```

## Argo Rollouts — Blue-Green

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: myapp
spec:
  replicas: 3
  strategy:
    blueGreen:
      activeService: myapp-active
      previewService: myapp-preview
      autoPromotionEnabled: false
      prePromotionAnalysis:
        templates:
          - templateName: success-rate
      scaleDownDelaySeconds: 30
```

```
Blue-Green flow:

  1. New version deployed as preview ReplicaSet
  2. previewService routes to new (green) pods
  3. prePromotionAnalysis runs automated checks
  4. If analysis passes → traffic cuts over instantly
  5. activeService now routes to green pods
  6. Old (blue) pods scale down after delay

  autoPromotionEnabled: false → requires manual approval
  scaleDownDelaySeconds → grace period before old pods removed
```

## Argo Rollouts — Canary with traffic splitting

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: myapp
spec:
  replicas: 5
  strategy:
    canary:
      canaryService: myapp-canary
      stableService: myapp-stable
      trafficRouting:
        istio:
          virtualService:
            name: myapp-vsvc
            routes: [primary]
      steps:
        - setWeight: 20
        - pause: { duration: 5m }
        - analysis:
            templates:
              - templateName: success-rate
        - setWeight: 50
        - pause: { duration: 10m }
        - setWeight: 100
```

```
Traffic routing providers:
  → Istio VirtualService
  → NGINX Ingress canary annotations
  → AWS ALB weighted target groups
  → SMI (Service Mesh Interface)
  → Gateway API

Traffic weights are enforced at the network layer,
not by pod-count ratios. 20% weight means 20% of
requests go to canary, regardless of replica count.
```

## AnalysisRun and AnalysisTemplate

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
spec:
  metrics:
    - name: success-rate
      interval: 60s
      successCondition: result[0] >= 0.95
      failureLimit: 3
      provider:
        prometheus:
          address: http://prometheus:9090
          query: |
            sum(rate(http_requests_total{status=~"2..",
              app="{{args.service}}"}[5m]))
            /
            sum(rate(http_requests_total{
              app="{{args.service}}"}[5m]))
```

```
Metrics providers:
  Prometheus, Datadog, New Relic, Wavefront,
  CloudWatch, Web/HTTP, Job, Kayenta

Behavior on analysis result:
  Success     → promote (advance to next step)
  Failure     → abort and rollback to stable
  Inconclusive → pause for human judgment

Analysis modes:
  Inline (blocking) — runs between steps
  Background — runs continuously during progression
  Pre/Post-promotion — blue-green specific
```

## Argo Rollouts vs Flagger

```
Aspect              Argo Rollouts        Flagger
──────────────────────────────────────────────────────────────
CRD approach        Replaces Deployment  Layers on top of
                    with Rollout CRD     standard Deployment

Manifest change     Requires migration   No manifest change
                    (workloadRef helps)  needed

GitOps alignment    Argo CD native       Flux native

Control style       Explicit step-based  Fully automated
                    with manual gates    metric-driven

Resource usage      ~35MB RAM, CPU       ~24MB RAM, lower
                    spikes               CPU usage

Best fit            Argo CD stack,       Flux stack, minimal
                    explicit control     manifest churn,
                    needed               mesh-native automation
```

## Anti-patterns

- **Using native rollouts for critical services** — no traffic
  splitting or automated analysis means regressions affect all
  users before detection. Use Argo Rollouts or Flagger for
  production services with SLOs.
- **Canary without traffic routing** — running canary by pod
  ratio alone means traffic split depends on load balancer
  behavior, not explicit weights. Always configure a traffic
  routing provider.
- **Skipping analysis steps** — manual dashboard watching does
  not scale. Define AnalysisTemplates with metric queries for
  automated promotion/rollback decisions.
- **Setting maxUnavailable too high** — aggressive rolling
  updates can take down significant capacity during deploys.
  Use `maxUnavailable: 0` for zero-downtime guarantees.

## Gotchas

- **Argo Rollouts requires manifest migration** — existing
  Deployments must be converted to the Rollout CRD. Use
  `workloadRef` to reference existing Deployments during
  gradual migration.
- **Analysis providers need connectivity** — AnalysisTemplates
  query external metrics systems. Network policies must allow
  the Argo Rollouts controller to reach Prometheus/Datadog.
- **Canary weight ≠ pod count** — with traffic routing, 20%
  canary weight routes 20% of traffic to potentially 1 pod.
  Ensure canary pods can handle the traffic volume at each
  weight step.
- **Abort does not delete canary pods immediately** — after
  abort, canary pods scale down gracefully. In-flight requests
  complete before termination.

## Verification

- Rollout strategy configured (blue-green or canary, not default).
- Traffic routing provider integrated for percentage-based splitting.
- AnalysisTemplates defined with SLI-based success conditions.
- Automated rollback triggers on failed analysis.
- Manual promotion gates enabled for critical deployments.
- Resource limits set on canary pods for load handling.
- Rollback procedure tested and documented.

## Related

- `documentation/docs/policies/deploy/progressive-canary-rollback-strategies.md`
- `documentation/docs/policies/deploy/argocd-flux-gitops-comparison.md`
- `documentation/docs/policies/monitoring/slo-error-budgets-burn-rate-alerting.md`

## Source URLs (verified 2026-08-16)

- Argo Rollouts — Concepts — https://argo-rollouts.readthedocs.io/en/stable/concepts/
- Argo Rollouts — Analysis and Progressive Delivery — https://argo-rollouts.readthedocs.io/en/stable/features/analysis/
- Kubernetes Deployments Documentation — https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- Argo Rollouts vs Flagger Comparison — https://kubernetes.ae/argo-rollouts-vs-flagger/
