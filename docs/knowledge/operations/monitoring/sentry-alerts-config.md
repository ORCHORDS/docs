# sentry-alerts-config

**Issue:** Configuring Sentry alert rules to notify on error spikes and regressions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
New errors are introduced in deployments but go unnoticed until user reports accumulate hours later.

## Pattern / Solution
Issue alerts (error-based):
- Trigger: "A new issue is created" → notify immediately on first occurrence
- Trigger: "Issue changes state to regression" → re-opened after fix
- Filter by environment: `production`

Metric alerts (volume-based):
- Metric: `Number of errors`
- Condition: `> 100 in 5 minutes`
- Filter: `environment:production AND !transaction:healthcheck`

```json
// Sentry API - create metric alert
{
  "name": "High Error Volume",
  "dataset": "events",
  "query": "level:error !transaction:/health",
  "aggregate": "count()",
  "timeWindow": 5,
  "thresholdType": 0,
  "resolveThreshold": 50,
  "triggers": [
    {"label": "critical", "alertThreshold": 100, "actions": [
      {"type": "pagerduty", "targetIdentifier": "P-XXXXXXX"}
    ]}
  ]
}
```

## Gotchas
- New issue alerts fire per unique fingerprint; noisy apps create alert fatigue
- Metric alerts have a minimum 1-minute resolution
- Use `ignoreCount` on known flaky issues to suppress noise

## Related
- `sentry-error-tracking.md`
- `alert-noise-reduction.md`
- `pagerduty-integration.md`
