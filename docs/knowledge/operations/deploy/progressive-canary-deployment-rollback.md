# Progressive Canary Deployment and Automated Rollback

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your team deploys new versions by switching 100% of traffic at once. A
bad release causes a full outage until someone manually rolls back —
often 15-30 minutes of downtime. You have no automated way to validate
a release against production traffic before committing to it. Rollback
is a manual process that requires rebuilding, redeploying, or reverting
Git commits under pressure.

## Context

Progressive deployment gradually shifts production traffic from the
stable version to the new version, validating at each step before
proceeding. Canary deployment is the most common pattern — routing a
small percentage of traffic (1-10%) to the new version while monitoring
key metrics. If metrics degrade, traffic is automatically routed back
to the stable version without human intervention. In 2026, Argo
Rollouts and Flagger are the dominant Kubernetes-native tools for
progressive delivery, while cloud platforms (AWS, GCP, Cloudflare) offer
built-in traffic splitting for serverless and container workloads.

## Deployment strategies compared

| Strategy | Traffic split | Rollback speed | Risk | Complexity |
|---|---|---|---|---|
| **Big bang** | 0% → 100% | Minutes (manual) | High | Low |
| **Blue-green** | 0% or 100% | Seconds (switch) | Medium | Medium |
| **Canary** | Gradual (1% → 100%) | Seconds (revert weight) | Low | Medium |
| **A/B (feature flag)** | User segment based | Instant (flag toggle) | Low | Medium |
| **Shadow/dark launch** | 0% (mirrored) | N/A (no user impact) | None | High |

## Canary rollout stages

```
Stage 1:  1% traffic  → 5 min analysis  → promote or rollback
Stage 2:  10% traffic → 10 min analysis → promote or rollback
Stage 3:  25% traffic → 10 min analysis → promote or rollback
Stage 4:  50% traffic → 15 min analysis → promote or rollback
Stage 5:  100% traffic → canary complete
```

At each stage, automated analysis compares canary metrics against the
baseline (stable version). If any metric breaches a threshold, traffic
is automatically routed back to the stable version.

## Argo Rollouts

```yaml
# Argo Rollouts canary strategy
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: api-server
spec:
  replicas: 10
  strategy:
    canary:
      steps:
        - setWeight: 5
        - pause: { duration: 5m }
        - analysis:
            templates:
              - templateName: error-rate-check
        - setWeight: 25
        - pause: { duration: 10m }
        - analysis:
            templates:
              - templateName: error-rate-check
        - setWeight: 50
        - pause: { duration: 15m }
        - analysis:
            templates:
              - templateName: latency-check
        - setWeight: 100
      canaryService: api-canary
      stableService: api-stable
      trafficRouting:
        istio:
          virtualService:
            name: api-vsvc
```

### Analysis template

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: error-rate-check
spec:
  metrics:
    - name: error-rate
      interval: 60s
      successCondition: result[0] < 0.05
      failureLimit: 3
      provider:
        prometheus:
          address: http://prometheus:9090
          query: |
            sum(rate(http_requests_total{status=~"5.*",
              app="{{args.service-name}}",
              version="canary"}[5m]))
            /
            sum(rate(http_requests_total{
              app="{{args.service-name}}",
              version="canary"}[5m]))
```

## Key metrics for canary analysis

| Metric | Threshold | Action |
|---|---|---|
| Error rate (5xx) | Canary > baseline + 1% | Rollback |
| P99 latency | Canary > baseline × 1.5 | Rollback |
| P50 latency | Canary > baseline × 1.2 | Rollback |
| Success rate | Canary < 99% | Rollback |
| CPU/memory | Canary > baseline × 2 | Investigate |
| Business metric (conversions) | Canary < baseline × 0.95 | Investigate |

## Automated rollback triggers

```
1. Metric-based: error rate, latency, or success rate breach threshold
2. Health-based: readiness/liveness probes fail
3. Time-based: analysis window expires without promotion
4. Manual: engineer triggers rollback via CLI or dashboard
```

### Rollback speed

| Mechanism | Rollback time | Data impact |
|---|---|---|
| Traffic weight shift | < 10 seconds | None (both versions running) |
| Kubernetes rollback | 30-60 seconds | Pod restart required |
| Blue-green switch | < 10 seconds | None (both environments ready) |
| Git revert + redeploy | 5-15 minutes | New build required |

## Non-Kubernetes progressive delivery

### Cloudflare Workers (gradual rollout)

```toml
# wrangler.toml — gradual rollout
[deployment]
strategy = "percentage"
percentage = 10
```

### AWS Lambda (weighted alias)

```bash
# Route 10% to new version
aws lambda update-alias --function-name my-func \
  --name live \
  --routing-config AdditionalVersionWeights={"2"=0.1}
```

## Anti-patterns

- **Canary without analysis** — shifting traffic percentages on a timer
  without checking metrics. This is a slow big-bang deploy, not a canary.
  Automated metric analysis is what makes canary deployments valuable.
- **Too-short analysis windows** — a 30-second analysis window cannot
  detect latency regressions that emerge under sustained load. Use at
  least 5-minute windows per stage.
- **Skipping low-traffic periods** — canary deployments during low
  traffic may not have enough data points for statistical significance.
  Deploy during peak hours or use synthetic traffic to supplement.
- **No baseline comparison** — comparing canary metrics against fixed
  thresholds instead of the concurrent baseline. Fixed thresholds do
  not account for normal traffic variation.

## Gotchas

- **Sticky sessions** — canary traffic splitting may route the same user
  to different versions on consecutive requests. Use consistent hashing
  (by user ID or session) to ensure users stay on one version.
- **Database schema compatibility** — both canary and stable versions
  must work with the same database schema. Schema changes must be
  backward-compatible or handled via expand-contract migrations.
- **Observability overhead** — canary analysis requires per-version
  metric labeling. Ensure your monitoring can segment metrics by
  deployment version (Kubernetes labels, custom headers).
- **Stateful services** — canary deployments assume stateless services.
  Stateful services (WebSocket, caches) require session draining before
  version transitions.

## Verification

- Canary deployments are configured for all production services.
- Automated analysis gates check error rate and latency at each stage.
- Rollback happens automatically when metrics breach thresholds.
- Rollback completes in under 60 seconds.
- Both canary and stable metrics are observable in dashboards.
- Database migrations are backward-compatible with canary patterns.

## Related

- `documentation/docs/policies/deploy/blue-green-deployment.md`
- `documentation/docs/policies/deploy/gitops-patterns.md`
- `documentation/docs/policies/monitoring/alerting-strategy-routing-escalation.md`

## Source URLs (verified 2026-08-16)

- Argo Rollouts canary guide — https://akuity.io/blog/automating-blue-green-and-canary-deployments-with-argo-rollouts
- Canary deployment with rollback — https://www.headout.studio/canary-deployment-with-automated-rollback/
- Canary rollout strategy guide — https://www.codewords.ai/blog/what-is-canary-deployment
- Harness progressive delivery — https://www.harness.io/blog/q2-2026-product-update-harness-continuous-delivery-gitops
