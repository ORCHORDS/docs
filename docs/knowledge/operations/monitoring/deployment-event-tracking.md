# deployment-event-tracking

**Issue:** Correlating metric changes with deployment events to identify regressions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Error rate spiked after a deployment but it is unclear which deployment caused it without annotations.

## Pattern / Solution
Emit deployment events to your monitoring system: Grafana annotations via API, Datadog deployment markers, or a custom Prometheus metric with version and service labels. Trigger from CI/CD pipeline on successful deploy. In Grafana, POST to /api/annotations with text, tags, and time. In dashboards, overlay annotations on all time-series graphs. Correlate with change in error rate, latency, and memory post-deploy.

## Gotchas
Include rollback events as annotations too. Deployment annotations should include git SHA, version, deployer, and environment. Store deployment history in a queryable DB for post-mortem lookups. Multiple services deploying simultaneously should have per-service annotations.

## Related
feature-flag-impact-monitoring, monitoring-as-code, batch-job-monitoring
