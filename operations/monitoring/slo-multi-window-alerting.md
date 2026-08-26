# slo-multi-window-alerting

**Issue:** Using multiple time windows to reduce false positives in SLO alerting
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Single-window burn rate alerts either miss slow degradations or produce too many false positives for brief spikes.

## Pattern / Solution
Multi-window alert: fire only when BOTH a short and long window show elevated burn rate.

```yaml
# Prometheus alert rule
- alert: HighBurnRate
  expr: |
    (
      slo:burnrate1h > 14.4
      and
      slo:burnrate5m > 14.4
    )
    or
    (
      slo:burnrate6h > 6
      and
      slo:burnrate30m > 6
    )
  labels:
    severity: critical
```

This catches both fast spikes (1h+5m) and slow burns (6h+30m).

## Gotchas
- Requires pre-computing recording rules for each window to keep query performance acceptable
- The short window must be a fraction (1/12) of the long window
- Test with historical incident data before deploying

## Related
- `slo-alerting-burn-rate.md`
- `prometheus-recording-rules.md`
- `alert-noise-reduction.md`
