# progressive-delivery-2026

**Issue:** Progressive delivery — Argo Rollouts vs Flagger
**Date:** 2026-08-09
**Status:** documented

## Symptom
You deploy a new version. 5% of traffic. Error
rate spikes. You roll back manually. By the time
you decide, 5% saw broken. You need auto-rollback.

## Root cause
**Canary + auto-rollback = progressive.** Argo + Flagger.

**Source:** CNCF + argo-rollouts 2026.

## The "progressive delivery" concept

Progressive delivery:
- **Canary:** % of traffic
- **Blue/green:** Switch instant
- **A/B:** Header/cookie split
- **Auto-rollback:** On SLO breach
- **Use:** Risk reduction

The delivery is gradual.

## The "Argo Rollouts" pattern

For Argo CD shops:
- **CRD:** `Rollout`
- **Memory:** ~50 MB
- **Modes:** Canary, blue/green
- **Dashboard:** Optional
- **When:** Already on Argo

The Argo is the default.

## The "Flagger" pattern

For Flux / A/B:
- **Service mesh:** Istio, Linkerd, Kuma
- **A/B:** Header/cookie
- **Provider:** Prometheus, Datadog
- **When:** Need A/B

The Flagger is the mesh option.

## The "canary minimum" pattern

For size:
- **Min:** 5% for signal
- **Window:** 1 SLO cycle
- **Why:** Statistical
- **Below:** No signal
- **Fix:** ≥ 5%

The canary is sized.

## The "AnalysisTemplate" pattern

For criteria:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
spec:
  metrics:
  - name: error-rate
    provider:
      prometheus:
        query: |
          rate(http_errors_total[5m])
    successCondition: result[0] < 0.01
```

The template is code.

## The "SLO-based rollback" pattern

For rollback:
- **Trigger:** SLO breach
- **Not:** Error count (flap)
- **Signal:** Stable
- **Why:** Burn rate
- **Fix:** Latency / error rate

The rollback is SLO.

## The "complement flags" pattern

For combo:
- **Canary:** By traffic
- **Flag:** By user/segment
- **Combine:** Yes
- **Not:** Mutate during canary
- **Why:** Causality

The combo is layered.

## The "Spinnaker for K8s" anti-pattern

For Spinnaker:
- **Issue:** 8 GB+ RAM, 10+ services
- **Fix:** Argo Rollouts
- **Why:** Massive overkill

The Spinnaker is replaced.

## The "no auto-rollback" anti-pattern

For manual:
- **Issue:** Slow response
- **Fix:** Auto on SLO
- **Why:** Defeats risk

The rollback is auto.

## The "1% canary" anti-pattern

For 1%:
- **Issue:** No signal
- **Fix:** ≥ 5%
- **Why:** Statistical

The canary is sized.

## The "mutate with flags" anti-pattern

For mid:
- **Issue:** Can't analyze
- **Fix:** Static during
- **Why:** Causality

The flag is static.

## The "same metric both" anti-pattern

For flap:
- **Issue:** Success = rollback trigger
- **Fix:** Different signals
- **Why:** Loop

The metrics differ.

## The "no analysis" anti-pattern

For scrape only:
- **Issue:** No query
- **Fix:** AnalysisTemplate
- **Why:** Slow blue-green

The analysis is set.

## The "long-lived flags" anti-pattern

For release flag:
- **Issue:** Test matrix
- **Fix:** Weeks only
- **Why:** Combinatorial

The flag is short.

## The "argo checklist" pattern

For checklist:
- [ ] Canary ≥ 5%
- [ ] SLO-based rollback
- [ ] AnalysisTemplate in Git
- [ ] Auto-rollback enabled
- [ ] Argo Rollouts / Flagger
- [ ] No flag mutation during
- [ ] Different metrics
- [ ] Flags cleaned up
- [ ] Spinnaker avoided

The checklist is 9.

## Verification
- **Test:** Canary deploys
- **Test:** Rollback fires
- **Test:** SLO tracked
- **Audit:** Per release

## Gotchas
- **The "1%" anti-pattern.** ≥ 5%.
- **The "no auto-rollback" anti-pattern.** Auto.
- **The "Spinnaker" anti-pattern.** Argo.

## Related
- `deploy/canary-deployments.md`
- `deploy/feature-rollout-strategies.md`
- `deploy/zero-downtime-deploys.md`
- `deploy/ephemeral-preview-environments.md`
- `patterns/feature-flags-best-practices.md`
- `patterns/error-budget-slo.md`
- Argo: https://argo-rollouts.readthedocs.io/en/stable/
- Flagger: https://flagger.app/
- CNCF: https://www.cncf.io/projects/argo/
