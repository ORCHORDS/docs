# anomaly-detection-alerts

**Issue:** Alerting on unusual patterns rather than fixed thresholds to catch unknown-unknown failures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Fixed thresholds miss gradual degradation and flag during normal traffic spikes. Need adaptive alerting.

## Pattern / Solution
Use rate-of-change alerts: alert when metric changes by more than N% from baseline over same period last week. Use moving averages: alert when current value deviates from 7-day rolling average by more than 2 standard deviations. For traffic-dependent metrics, use ratio-based alerts (error rate) rather than absolute counts. Grafana and Datadog have built-in anomaly detection algorithms.

## Gotchas
Anomaly detection has higher false positive rate than static thresholds — use for early warning, not primary alerting. Requires sufficient historical data (2+ weeks) for seasonal baselines. Business events (launches, sales) skew baselines — annotate them.

## Related
alert-noise-reduction, slo-alerting-burn-rate, capacity-planning-metrics
