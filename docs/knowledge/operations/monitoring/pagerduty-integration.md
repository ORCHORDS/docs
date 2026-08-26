# pagerduty-integration

**Issue:** Routing Prometheus or Grafana alerts to PagerDuty with proper escalation and deduplication
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Need reliable alert delivery with on-call scheduling, escalation, and incident management.

## Pattern / Solution
Create PagerDuty service with Events API v2 integration. In Alertmanager configure pagerduty_configs receiver with routing_key from integration key and severity from alert label. Set group_by to deduplicate related alerts into one incident. Use resolve_timeout to auto-resolve when alerts clear. Configure escalation policy: primary on-call > 5min > secondary > 15min > manager.

## Gotchas
PagerDuty dedup key defaults to the alert fingerprint; customize dedup_key for better grouping. group_wait in Alertmanager delays initial notification. Enable PagerDuty webhook to push incident status back to Slack. Test with amtool alert add before going live.

## Related
opsgenie-setup, alerting-runbook-linking, alert-severity-levels, on-call-rotation-setup
