# cost-monitoring-dashboards

**Issue:** Building dashboards that surface cloud and infrastructure spend tied to engineering decisions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Monthly cloud bill is a surprise. No visibility into which service, team, or feature drives cost.

## Pattern / Solution
Tag all cloud resources with team, service, environment tags. Use AWS Cost Explorer, GCP Billing, or Azure Cost Management APIs to pull spend by tag into Grafana. Track cost per unit of value: cost per API request, cost per active user. Set budget alerts at 80% of monthly forecast. For Cloudflare, track Workers CPU milliseconds as billed unit.

## Gotchas
Tagging compliance is the hardest part — enforce tags via IaC and CI checks. Reserved instance discounts must be attributed proportionally. Data transfer costs are often the biggest surprise. Cost anomaly alerts catch unexpected spend spikes within hours.

## Related
capacity-planning-metrics, cloudflare-workers-analytics, monitoring-as-code
