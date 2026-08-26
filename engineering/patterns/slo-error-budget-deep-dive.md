# slo-error-budget-deep-dive

**Issue:** SLO + error budget + burn rate alerts
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have uptime 99.9%. A deploy breaks things. You
push anyway. The SLO is missed. The customer is angry.
You wish you had error budget policy.

## Root cause
**SLOs without policy are just numbers.** Use the
Google SRE Workbook.

**Source:** Google SRE Workbook:
https://sre.google/workbook/table-of-contents/

## The "SLO" concept

Service Level Objective:
- **SLI:** Service Level Indicator (raw measurement)
- **SLO:** Target for SLI
- **SLA:** Agreement with consequences
- **Error budget:** Allowed failures (1 - SLO)

The SLO is the target.

## The "SLI types" pattern

For SLI types:
- **Availability:** good_requests / total_requests
- **Latency:** requests_below / total_requests
- **Throughput:** processed / submitted
- **Correctness:** correct / total (search, ML)
- **Freshness:** fresh_data / total (cache)

The SLI is per dimension.

## The "SLO target tiers" pattern

For tier-based SLOs:
| Tier | Availability | Latency P95 | Rationale |
|---|---|---|---|
| 1 (Payment, Auth) | 99.95% | 200ms | Direct revenue |
| 2 (Search, Recs) | 99.9% | 500ms | Core UX |
| 3 (Notif, Logs) | 99.5% | 2s | Async OK |
| 4 (Internal) | 99.0% | 5s | Maintenance OK |

The tier is per service.

## The "error budget" concept

For 99.9% SLO over 30 days:
- **Budget fraction:** 0.1%
- **Allowed failures (1M req/day):** 30,000
- **Allowed minutes:** 43.2
- **Allowed per day:** 1.44

The budget is the allowed failures.

## The "burn rate" concept

For burn rate:
- **Burn rate 1x:** Budget exhausted exactly at window end
- **Burn rate 10x:** Exhausted in 1/10 the window
- **Burn rate 14.4x:** Exhausted in 2 days (from 30)

The burn rate is the speed.

## The "multi-window burn rate" pattern

For alerting (Google SRE):
- **Fast burn (1h, 5m):** 14.4x → page
- **Medium burn (6h, 30m):** 6x → ticket
- **Slow burn (3d, 6h):** 1x → ticket
- **Critical burn (1h, 5m):** 14.4x AND 6h/30m 6x → page

The alert is multi-window.

## The "burn rate alert" pattern

For Prometheus:
```yaml
- alert: SLOErrorBudgetCriticalBurn
  expr: |
    job:slo:burn_rate_1h > 14.4
    and
    job:slo:burn_rate_6h > 6.0
  for: 5m
  labels:
    severity: page
  annotations:
    summary: "SLO error budget burning critically"
```

The alert pages.

## The "error budget policy" pattern

For thresholds:
| Budget | Action |
|---|---|
| >= 50% | Green: Normal velocity |
| 20-50% | Yellow: Add canary 1%→10%→50%→100% |
| < 20% | Red: Feature freeze, VP approval |
| <= 0% | Exhausted: Halt non-essential |

The policy is per threshold.

## The "policy YAML" pattern

For config-as-code:
```yaml
# error-budget-policy.yaml
policy:
  version: "2.0"
  effective_date: "2026-01-15"
  review_cycle: "quarterly"
  budget_thresholds:
    green:
      remaining_budget: ">= 50%"
      actions:
        - "Feature:Reliability = 8:2"
    yellow:
      remaining_budget: "20% ~ 50%"
      actions:
        - "Add canary stage"
        - "SLO review twice per week"
    red:
      remaining_budget: "< 20%"
      actions:
        - "Freeze feature releases"
        - "VP approval for all changes"
  exceptions:
    - "Security patches deployed immediately"
    - "Legal compliance exempt"
```

The policy is documented.

## The "Prometheus recording rules" pattern

For SLI rules:
```yaml
groups:
- name: sli.rules
  interval: 30s
  rules:
  - record: job:latency_seconds:p99
    expr: |
      histogram_quantile(0.99,
        sum(rate(http_request_duration_seconds_bucket[5m])) by (le, job))
  - record: job:error_rate:ratio5m
    expr: |
      sum(rate(http_requests_total{status=~"5.."}[5m])) by (job)
      /
      sum(rate(http_requests_total[5m])) by (job)
```

The SLI is recorded.

## The "SLO calc rules" pattern

For SLO rules:
```yaml
- name: slo.rules
  interval: 60s
  rules:
  - record: job:slo:error_budget_remaining_ratio
    expr: |
      1 - (
        (1 - slo_target)
        /
        (
          sum(rate(http_requests_total{status=~"5.."}[30d])) by (job)
          /
          sum(rate(http_requests_total[30d])) by (job)
        )
      )
```

The budget is calculated.

## The "Grafana panels" pattern

For 4 panels:
1. **SLO Compliance Gauge:** % vs target
2. **Error Budget Remaining:** 100% to 0%
3. **Burn Rate Over Time:** 1x, 6x, 14.4x thresholds
4. **Budget Consumption Over Time:** Downward slope

The dashboard is 4 panels.

## The "release gate" pattern

For CI/CD gate:
```yaml
# Block deploy if budget low
- name: check-error-budget
  run: |
    BUDGET=$(curl -s "http://prom/api/v1/query?query=..." | jq '.data.result[0].value[1]')
    if (( $(echo "$BUDGET < 0.20" | bc -l) )); then
      echo "ERROR: Error budget below 20%. Freeze."
      exit 1
    fi
```

The gate blocks.

## The "postmortem SLO" pattern

For postmortems:
- **Required:** How much did this impact SLO?
- **Format:** "Spent X% of 30-day budget"
- **Result:** Quantifies business impact

The postmortem quantifies.

## The "tier-based budget" pattern

For tiers:
- **Tier 1:** Strict policy, VP escalation
- **Tier 2:** Standard policy
- **Tier 3:** Loose policy
- **Tier 4:** No SLO

The budget is per tier.

## The "exceptions" pattern

For allowed exceptions:
- **Security patches:** Always deploy
- **Legal compliance:** Always deploy
- **Data loss prevention:** Always deploy
- **Feature work:** Blocked

The exceptions are explicit.

## The "DORA + SLO" relationship pattern

For DORA metrics:
- **Lead time:** Velocity
- **Deploy freq:** Velocity
- **MTTR:** Recovery
- **Change fail rate:** Stability
- **SLO:** Customer trust

SLO is the customer view.

## The "SLO + Canary" pattern

For integration:
- **Canary metric:** Error rate vs baseline
- **Auto-promote:** If within SLO budget
- **Auto-rollback:** If SLO budget consumed

The canary is SLO-aware.

## The "Prometheus scaling" pattern

For scale:
- **Dedicated Prometheus:** For SLO (long windows)
- **Thanos / Cortex / Mimir:** Long retention
- **Downsampling:** 6h for 30d window
- **Multi-tenancy:** Label-based

The Prometheus scales.

## The "GitOps SLO" pattern

For git:
- **Recording rules:** In git
- **Dashboards:** JSON in git
- **Alert rules:** In git
- **Policy YAML:** In git
- **Changes:** PR review

The SLO is in git.

## The "no SLO" anti-pattern

For no SLO:
- **Issue:** No definition of "good"
- **Fix:** Define SLI + SLO per service

The SLO is required.

## The "100% SLO" anti-pattern

For 100% SLO:
- **Issue:** Means "never fail"
- **Result:** Never deploy
- **Fix:** Set 99.9% (or tier-based)

The SLO is realistic.

## The "no error budget" anti-pattern

For no budget policy:
- **Issue:** SLOs are decorative
- **Fix:** Budget → actions

The policy is the value.

## The "no burn rate alert" anti-pattern

For no burn rate:
- **Issue:** SLO breach is silent until window end
- **Fix:** Multi-window burn rate

The burn rate alerts fast.

## The "no exception policy" anti-pattern

For no exceptions:
- **Issue:** Security patches blocked
- **Fix:** Explicit exceptions

The exceptions are listed.

## The "no postmortem SLO" anti-pattern

For no SLO in PM:
- **Issue:** No quantification
- **Fix:** Budget impact in PM

The PM quantifies.

## Verification
- **Test:** SLI rules evaluate
- **Test:** SLO rules produce budget metrics
- **Test:** Burn rate alerts fire
- **Test:** Release gate works
- **Audit:** Quarterly review

## Gotchas
- **The "100% SLO" anti-pattern.** 99.x% is right.
- **The "no policy" anti-pattern.** Define policy.
- **The "single window" anti-pattern.** Multi-window.

## Related
- `patterns/error-budget-slo.md`
- `patterns/observability-three-pillars.md`
- `patterns/incident-response.md`
- `patterns/safe-deploy-checklist.md`
- `deploy/canary-deployments.md`
- OneUptime: https://oneuptime.com/blog/post/2026-02-06-slo-error-budget-burn-rate-grafana/view
- YoungJu: https://www.youngju.dev/blog/observability/2026-03-04-observability-slo-error-budget-execution.en
- DevToCash: https://devtocash.com/blog/sli-slo-implementation-prometheus-grafana-2026
- Google SRE: https://sre.google/workbook/table-of-contents/
