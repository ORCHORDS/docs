# error-budget-calculation

**Issue:** Calculating and tracking error budgets for SLOs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams don't know how much reliability margin remains before breaching their SLO, so they either ship too conservatively or too aggressively.

## Pattern / Solution
```
error_budget = (1 - SLO_target) * window_seconds
remaining    = error_budget - total_bad_seconds
```

Example for 99.9% SLO over 30 days:
```
window        = 30 * 24 * 3600 = 2,592,000 seconds
error_budget  = 0.001 * 2,592,000 = 2,592 seconds (~43 minutes)
```

Prometheus query for remaining budget:
```promql
(1 - (
  sum(rate(http_requests_total{status=~"5.."}[30d]))
  / sum(rate(http_requests_total[30d]))
)) * 2592000
```

## Gotchas
- Error budget resets at the window boundary, not rolling continuously unless configured
- Planned downtime counts against the budget unless excluded explicitly
- Track budget burn rate, not just remaining budget

## Related
- `sli-slo-sla-definitions.md`
- `error-budget-policy.md`
- `slo-alerting-burn-rate.md`
