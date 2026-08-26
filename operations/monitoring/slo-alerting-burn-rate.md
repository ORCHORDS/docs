# slo-alerting-burn-rate

**Issue:** Alerting on SLO burn rate rather than raw error rate
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Raw error rate alerts fire too late or too early. Burn rate alerts catch budget depletion before it becomes critical.

## Pattern / Solution
Burn rate = how fast the error budget is being consumed relative to the budget window.

```promql
# 1-hour burn rate
(
  sum(rate(http_requests_total{status=~"5.."}[1h]))
  / sum(rate(http_requests_total[1h]))
) / 0.001  # 1 - SLO target
```

Alert thresholds (Google SRE model):
- Burn rate > 14.4 for 1h → page (consumes 1-day budget in 1 hour)
- Burn rate > 6 for 6h → ticket (consumes 1-day budget in 4 hours)
- Burn rate > 3 for 3d → warning

## Gotchas
- A single high burn rate window misses slow leaks; use multi-window alerting
- Burn rate alerts need the SLO target baked in; parameterize it
- Different SLOs need different burn rate thresholds

## Related
- `slo-multi-window-alerting.md`
- `error-budget-calculation.md`
- `prometheus-alerting-rules.md`
