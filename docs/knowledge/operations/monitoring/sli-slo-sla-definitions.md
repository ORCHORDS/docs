# sli-slo-sla-definitions

**Issue:** Defining SLIs, SLOs, and SLAs correctly and consistently
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams conflate SLOs with SLAs and either over-promise to customers or under-invest in reliability.

## Pattern / Solution
- **SLI (Service Level Indicator)** — the actual measured value. Example: request success rate over 5 minutes.
- **SLO (Service Level Objective)** — internal target. Example: 99.9% success rate over 30 days.
- **SLA (Service Level Agreement)** — external contract with consequences. Example: 99.5% or credits issued.

```yaml
# Example SLO definition
slo:
  name: api-availability
  indicator: sum(rate(http_requests_total{status!~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
  target: 0.999
  window: 30d
```

SLO should always be tighter than SLA to leave buffer.

## Gotchas
- SLIs must measure from the user perspective, not internal server metrics
- Setting SLO = SLA leaves no room for planned maintenance
- Avoid more than 3–5 SLOs per service; too many dilutes focus

## Related
- `error-budget-calculation.md`
- `slo-alerting-burn-rate.md`
