# alert-inhibition-rules

**Issue:** Suppressing downstream alerts when a root-cause alert is already firing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Database down triggers ten alerts from services that depend on it. On-call gets ten pages for one root cause.

## Pattern / Solution
Configure Alertmanager inhibit_rules: source match (e.g. alertname=DatabaseDown) inhibits target match (e.g. service=api). Use equal labels to ensure you only inhibit alerts in the same cluster/environment. Example: node unreachable inhibits all pod alerts on that node.

## Gotchas
Inhibition is not the same as grouping — inhibited alerts are hidden, not merged. Do not inhibit alerts that represent independent problems. Inhibition applies only within Alertmanager — alerts already sent to PagerDuty will not be recalled. Test with amtool config routes test.

## Related
alert-grouping-patterns, alert-noise-reduction, alert-silencing-strategy, prometheus-alerting-rules
