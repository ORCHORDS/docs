# cpu-throttling-detection

**Issue:** Detecting Kubernetes CPU throttling that causes latency without visible CPU saturation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Container shows 40% CPU usage but responses are slow. CPU limits are causing throttling during bursts.

## Pattern / Solution
Query throttle ratio: rate(container_cpu_cfs_throttled_periods_total) divided by rate(container_cpu_cfs_periods_total). Alert when greater than 0.25 (25% of scheduling periods throttled). Correlate with p99 latency to confirm impact. Resolution: increase CPU limit, or split service to reduce per-instance CPU burst.

## Gotchas
CPU requests and limits have different effects: request affects scheduling placement, limit affects throttling. CPU throttling does not show in kubectl top pods — only CFS throttle counters reveal it. VerticalPodAutoscaler can recommend adjusted requests/limits based on actual usage.

## Related
worker-cpu-monitoring, memory-leak-detection, capacity-planning-metrics
