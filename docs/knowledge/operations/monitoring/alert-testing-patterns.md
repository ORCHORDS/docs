# alert-testing-patterns

**Issue:** Testing alert rules and notification pipelines before they are needed in a real incident
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An alert fires for the first time during a real incident and the runbook link is broken or PagerDuty routing is misconfigured.

## Pattern / Solution
Test alert rules with promtool test rules using unit test files that define input time series and expected alert states. Trigger synthetic alert events in staging by injecting metric values that breach thresholds and verifying end-to-end notification delivery. Run alert pipeline drills monthly. Validate runbook links in CI using link checkers. Use amtool to test routing rules without firing real alerts.

## Gotchas
promtool test rules tests Prometheus rule logic but not Alertmanager routing — test both separately. Alert routing tests should cover group_by, inhibition, and silencing behavior. Integration test your full pipeline at least quarterly. Staging environments should have realistic alert thresholds, not disabled alerts.

## Related
alerting-runbook-linking, alert-severity-levels, prometheus-alerting-rules, on-call-rotation-setup
