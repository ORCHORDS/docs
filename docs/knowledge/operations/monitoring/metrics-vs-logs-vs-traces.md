# metrics-vs-logs-vs-traces

**Issue:** Choosing the right observability signal for a given problem
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Engineers default to logs for everything, leading to high storage costs and slow queries, or rely only on metrics and miss root-cause details.

## Pattern / Solution
| Signal  | Storage cost | Query speed | Detail level | Best for |
|---------|-------------|-------------|--------------|----------|
| Metrics | Low         | Fast        | Low          | Alerting, dashboards |
| Logs    | High        | Slow        | High         | Debugging, auditing |
| Traces  | Medium      | Medium      | Medium       | Latency, call graphs |

Decision tree:
1. Alerting on threshold? → Metric
2. Need full event payload? → Log
3. Need cross-service latency? → Trace

```yaml
# Emit all three for critical paths
span.set_attribute("user_id", uid)          # trace
logger.info("payment.processed", amount=99) # log
payment_counter.inc()                        # metric
```

## Gotchas
- High-cardinality labels on metrics explode storage (use traces instead)
- Sampling logs loses rare events; use head/tail sampling carefully
- Traces require clock synchronization across services

## Related
- `observability-three-pillars-overview.md`
- `prometheus-cardinality-management.md`
- `log-sampling-strategies.md`
