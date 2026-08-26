# SRE Error Budget Policy Enforcement

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Teams ship features at full pace even after repeated SLO
violations. Reliability work never gets scheduled because
"we'll catch up later." An outage arrives and the error
budget is already overdrawn, giving engineering no runway
to safely experiment with fixes.

## Context

An error budget is the complement of your SLO target: a
99.9 % availability SLO over a 28-day window gives you
0.1 % of that window — roughly 40.3 minutes — as
permitted downtime. Without a written policy that
gates feature work on budget health, the budget is
decorative. This entry covers how to calculate the
budget, alert on burn rate, define policy states, and
run the monthly error budget report.

## 1. Error Budget Calculation (28-Day Window)

```
total_requests  = sum(rate(http_requests_total[28d]))
bad_requests    = sum(rate(http_errors_total[28d]))

error_rate      = bad_requests / total_requests
error_budget_remaining = (1 - SLO_target) - error_rate

# Example for SLO = 99.9 %
SLO_target            = 0.999
allowed_error_rate    = 0.001   # 0.1 %
budget_minutes        = 28 * 24 * 60 * allowed_error_rate
                      = 40.32 minutes
```

Track budget as a percentage remaining:

```promql
# PromQL — error budget remaining %
(
  1 - (
    sum(increase(http_requests_total{status=~"5.."}[28d]))
    /
    sum(increase(http_requests_total[28d]))
  ) / 0.001
) * 100
```

## 2. Burn Rate Tiers and Alert Thresholds

Burn rate measures how fast you are consuming the budget
relative to the budget period. A burn rate of 1 means
you will exactly exhaust the budget at the end of the
window. A burn rate of 2 means you exhaust it in half
the window.

```
+----------+------------+------------------+-----------+
| Tier     | Burn Rate  | Budget Gone In   | Severity  |
+----------+------------+------------------+-----------+
| Baseline |   <= 1.0   | >= 28 days       | none      |
| Concern  |   > 2.0    | < 14 days        | warning   |
| High     |   > 6.0    | < 4.7 days       | page      |
| Critical |   > 14.4   | < 2 hours        | page now  |
+----------+------------+------------------+-----------+
```

Fast-burn alert (critical — 2 % budget in 1 hour):

```yaml
# Prometheus alerting rule
- alert: ErrorBudgetFastBurn
  expr: |
    (
      sum(rate(http_errors_total[5m]))  /
      sum(rate(http_requests_total[5m]))
    ) / 0.001 > 14.4
    and
    (
      sum(rate(http_errors_total[1h]))  /
      sum(rate(http_requests_total[1h]))
    ) / 0.001 > 14.4
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Fast burn: error budget exhausted in < 2 h"
```

Slow-burn alert (warning — 10 % budget in 3 days):

```yaml
- alert: ErrorBudgetSlowBurn
  expr: |
    (
      sum(rate(http_errors_total[6h]))  /
      sum(rate(http_requests_total[6h]))
    ) / 0.001 > 6.0
    and
    (
      sum(rate(http_errors_total[3d]))  /
      sum(rate(http_requests_total[3d]))
    ) / 0.001 > 6.0
  for: 15m
  labels:
    severity: warning
  annotations:
    summary: "Slow burn: error budget depleting fast"
```

## 3. Error Budget Policy States

Define four states and what they require of engineering:

```
Normal (> 50 % remaining)
  - Feature work proceeds without restriction.
  - SRE may approve experiments and canary releases.

Concern (25 – 50 % remaining)
  - New rollouts require SRE sign-off.
  - At least one reliability item per sprint.

Exhausted (0 – 25 % remaining)
  - Reliability work is priority 1.
  - Feature PRs may be merged but not deployed.
  - Weekly budget review with engineering lead.

Freeze (< 0 % — overdrawn)
  - Feature deployments halted until budget recovers.
  - Incident review required before freeze lifts.
  - Executive notification within 24 hours.
```

Automate state transitions by querying the budget metric
in a daily cron job and posting to a Slack channel with
a colour-coded badge (green / yellow / orange / red).

## 4. What a Budget Freeze Means for Feature Work

A freeze is not punishment; it is a circuit breaker. The
goal is to prevent new change from compounding existing
unreliability.

Rules during a freeze:
- Hotfixes and rollbacks are always permitted.
- Security patches proceed on an emergency basis with
  SRE approval.
- Infrastructure patches that reduce risk (disk
  clean-up, cert renewal) are permitted.
- New features and refactors are queued, not cancelled.
- The freeze lifts automatically when the 28-day budget
  returns above 10 % remaining and no active P1 exists.

Communicate the freeze in the engineering standup and
the #incidents Slack channel. Do not freeze silently.

## 5. Error Budget Report Template

Publish monthly (or after any freeze) using this format:

```
# Error Budget Report — [Month YYYY]

Service:      payment-api
SLO Target:   99.9 % (28-day rolling)
Window:       [start] – [end]

## Budget Summary
  Allowed error rate : 0.10 %
  Actual error rate  : 0.07 %
  Budget used        : 70 %
  Budget remaining   : 30 %
  Current state      : Concern

## Top Error Sources
  1. Timeout on downstream billing-service  — 45 %
  2. DB connection pool exhaustion           — 30 %
  3. Bad request from mobile client v1.4     — 25 %

## Actions Taken
  - [date] Connection pool limit raised PR #<number>
  - [date] Billing-service timeout increased ADR-0023

## Next Steps
  - Improve billing-service resilience (owner: @alice)
  - Add client validation layer (owner: @bob)
```

## Anti-patterns

- Resetting the SLO window after an incident to hide
  the spend — this destroys trust in the metric.
- Setting the SLO target so low that the budget never
  depletes and signals nothing.
- Running error budget reviews only when there is a
  freeze; run them monthly regardless.
- Counting only 5xx responses and ignoring latency SLIs
  when latency is in the SLO.

## Gotchas

- Prometheus `increase()` has edge cases with counter
  resets; prefer `rate()` over long windows.
- A 28-day rolling window means the budget improves
  naturally as old bad windows age out — plan for dips
  at month boundaries.
- Multi-region deployments need per-region budgets plus
  a global weighted budget to avoid region masking.
- Error budget burn rate alerts fire on short windows;
  tune `for:` to avoid alert flapping on traffic spikes.

## Verification

1. Query the PromQL expressions in Grafana Explore and
   confirm they return expected values for a known bad
   window.
2. Trigger a test alert by temporarily lowering the
   burn-rate threshold and confirm PagerDuty routing.
3. Walk through each policy state manually with the
   team and confirm everyone knows the rules before the
   first real event.

## Related

- `documentation/docs/policies/lessons/alert-fatigue-masks-real-outages-2026.md`
- `documentation/docs/policies/lessons/blameless-postmortem-2026.md`
- `documentation/docs/policies/lessons/dora-metrics-engineering-measurement.md`
- `documentation/docs/policies/lessons/incident-response-runbook.md`

## Source URLs (verified 2026-08-17)

- https://sre.google/workbook/implementing-slos/
- https://sre.google/workbook/alerting-on-slos/
- https://prometheus.io/docs/practices/alerting/
- https://grafana.com/blog/2021/11/11/slo-error-budgets/
