# capacity-planning-forecasting

**Issue:** Forecasting resource needs to avoid both under-provisioning (outages) and over-provisioning (waste)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Infrastructure sized based on gut feeling. Surprise capacity exhaustion during product launches. No data-driven process for quarterly hardware/cloud budget requests.

## Pattern / Solution
Capacity planning process:
```
1. Collect metrics: CPU, memory, storage, network — at least 3 months of data
2. Identify trend: linear growth? Seasonal patterns? Event-driven spikes?
3. Model growth: extrapolate with safety margin
4. Find bottleneck: which resource hits ceiling first?
5. Plan: reservation purchases, instance type changes, architecture changes
```

Prometheus-based growth forecast:
```promql
# Current usage
avg_over_time(node_memory_MemUsed_bytes[30d])

# Linear regression prediction (30d ahead)
predict_linear(node_memory_MemUsed_bytes[30d], 30 * 24 * 3600)

# Days until disk full
(node_filesystem_size_bytes - node_filesystem_avail_bytes)
/ deriv(node_filesystem_avail_bytes[7d]) * -1 / 86400
```

Capacity model spreadsheet columns:
```
Metric     | Current | 30d avg | 90d trend | 180d forecast | Headroom | Action
CPU (p95)  | 45%     | 42%     | +2%/mo    | 54%           | 46%      | OK
Memory     | 78%     | 75%     | +3%/mo    | 93%           | 7%       | Upgrade next quarter
DB IOPS    | 12K     | 11K     | +500/mo   | 14K           | 4K       | OK for 6 months
Disk       | 2.1 TB  | —       | +50GB/mo  | 2.6 TB (3TB)  | 400 GB   | Expand Q4
```

Traffic capacity planning:
```python
# Given SLO target p99 < 200ms at 95% CPU, what's max RPS?
# Load test to find breaking point, then apply safety factor

max_rps = load_test_breaking_point * 0.7   # 70% of breaking point
instances_needed = ceil(target_peak_rps / (max_rps_per_instance))
```

## Gotchas
- Plan for peak, not average — capacity must handle your worst expected traffic
- Add 20–30% buffer above forecast for unexpected growth
- Storage growth is often underestimated — binary data (media, logs) grows faster than row counts
- Review and re-forecast quarterly; annual plans are obsolete within 6 months in fast-growing products

## Related
- `auto-scaling-policies.md`
- `cloud-cost-optimization-rightsizing.md`
- `monitoring-sla-slo-sli.md`
