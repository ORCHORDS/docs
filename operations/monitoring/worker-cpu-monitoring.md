# worker-cpu-monitoring

**Issue:** Tracking CPU utilization and throttling in worker processes and containers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Workers are slow but no obvious errors. CPU throttling in containers can cause latency without high CPU usage numbers.

## Pattern / Solution
Track container_cpu_usage_seconds_total and compare against CPU limits. CPU throttle ratio: rate(container_cpu_cfs_throttled_seconds_total) divided by rate(container_cpu_cfs_periods_total). Alert when throttle ratio exceeds 25%. For bare-metal workers track node_cpu_seconds_total by mode (user, system, iowait).

## Gotchas
CPU throttling is invisible in kubectl top — it shows average usage, not throttled periods. A container using 50% of its limit can still be heavily throttled with bursty workloads. Increase CPU limits before increasing replicas when throttling is the bottleneck.

## Related
memory-leak-detection, gc-pressure-monitoring, cpu-throttling-detection, capacity-planning-metrics
