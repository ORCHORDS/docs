# capacity-planning-metrics

**Issue:** Tracking metrics that predict resource exhaustion before it causes incidents
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Service runs out of disk, memory, or connections with no advance warning. Need leading indicators.

## Pattern / Solution
Track resource saturation metrics with trend forecasts: disk fill rate using predict_linear, memory growth over 24h, connection pool usage trend. Alert at 80% for 4h-ahead exhaustion, critical at 90%. Build capacity dashboard: current usage, growth rate, days-to-exhaustion at current rate. Review monthly; adjust provisioning when trend exceeds 70% within 30 days.

## Gotchas
Linear prediction fails for spiky workloads — use predict_linear over longer windows to smooth. CPU saturation is trickier than disk — throttling starts before 100%. Review capacity metrics after each major feature launch.

## Related
anomaly-detection-alerts, cost-monitoring-dashboards, worker-cpu-monitoring, memory-leak-detection
