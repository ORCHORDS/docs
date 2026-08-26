# monitoring-as-code

**Issue:** Managing monitoring configuration (dashboards, alerts, synthetic tests) in version control
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Dashboards and alerts are configured via UI only. Changes are undocumented and not reversible. Config drifts between environments.

## Pattern / Solution
Use Terraform or Pulumi to manage Grafana dashboards (via Grafana provider), Prometheus alert rules (as ConfigMaps or via Alertmanager Operator CRDs), and Datadog monitors. Store Grafana dashboards as JSON in git. Use Jsonnet or grafonnet library to templatize dashboards. Apply changes via CI pipeline. Validate alert rule syntax in CI with promtool check rules.

## Gotchas
Grafana dashboard JSON is verbose and diffs poorly — use Jsonnet to generate it. Terraform state for monitoring resources can drift if someone edits via UI. Jsonnet has a steep learning curve — start with JSON in git. Include monitoring config changes in deployment PRs for reviewer awareness.

## Related
deployment-event-tracking, prometheus-alerting-rules, grafana-alerts-setup
