# opsgenie-setup

**Issue:** Configuring OpsGenie for alert routing, on-call scheduling, and escalation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Need an alternative to PagerDuty with similar capabilities; OpsGenie is often bundled with the Atlassian stack.

## Pattern / Solution
Create OpsGenie team and API integration. In Alertmanager configure opsgenie_configs receiver with api_key and tags mapped from alert labels. Create routing rules in OpsGenie to direct alerts to teams. Build on-call schedules with rotation. Define escalation policies: notify primary > 5min > escalate to secondary > 15min > manager. Use OpsGenie heartbeat for dead man's switch on batch jobs.

## Gotchas
OpsGenie free tier limits team size and integrations. Alert priority maps differently than PagerDuty severity — map explicitly. The heartbeat feature is excellent for cron job monitoring. Maintenance windows suppress alerts during planned downtime.

## Related
pagerduty-integration, victorops-patterns, alert-severity-levels, cron-job-monitoring
