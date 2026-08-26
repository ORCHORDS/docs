# alert-grouping-patterns

**Issue:** Grouping related alerts into single incidents to reduce notification volume
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Ten pods restart at once; ten separate pages fire. Engineer gets ten notifications for one problem.

## Pattern / Solution
Configure Alertmanager group_by per route: group by alertname, cluster, namespace for infra alerts. Set group_wait 30s to collect alerts before sending first notification. Set group_interval 5m to batch subsequent firings. In PagerDuty/OpsGenie configure dedup key based on service and alertname to merge related alerts into one incident.

## Gotchas
Grouping hides individual alert details — include count of firing instances in notification template. Over-grouping can obscure distinct problems. group_wait adds delay to first notification. Test grouping behavior in staging before deploying.

## Related
alert-noise-reduction, alert-inhibition-rules, prometheus-alerting-rules
