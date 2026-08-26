# feature-flag-impact-monitoring

**Issue:** Measuring the effect of feature flag changes on system metrics and user behavior
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A flag is turned on and something degrades, but there is no automated signal connecting the flag change to the metric change.

## Pattern / Solution
Emit a feature_flag_change event whenever a flag is toggled, including flag name, old value, new value, and actor. Annotate Grafana dashboards with flag events. Tag requests with active flag variants using log correlation or trace attributes. In your feature flag tool configure metric tracking per flag. Build a dashboard comparing p99 latency and error rate between flag=on and flag=off cohorts in real time.

## Gotchas
Flag changes are not atomic across a fleet — during rollout you have mixed populations. Analyze metrics per flag variant, not just before/after. A flag on for 1% of traffic may not show signal in aggregate metrics. Clean up stale flag instrumentation when flags are removed.

## Related
deployment-event-tracking, a-b-test-metrics, monitoring-as-code
