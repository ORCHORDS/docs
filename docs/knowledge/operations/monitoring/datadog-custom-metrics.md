# datadog-custom-metrics

**Issue:** Emitting custom business metrics to Datadog via DogStatsD
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Infrastructure metrics are automatic but business KPIs (orders per minute, revenue per hour) require custom instrumentation.

## Pattern / Solution
```typescript
import StatsD from "hot-shots";

const dog = new StatsD({
  host: process.env.DD_AGENT_HOST ?? "localhost",
  port: 8125,
  prefix: "myapp.",
  globalTags: {
    env: process.env.NODE_ENV ?? "development",
    service: "api",
  },
});

// Counter
dog.increment("orders.placed", { payment_method: "card" });

// Gauge
dog.gauge("queue.depth", queue.length, { queue_name: "emails" });

// Histogram (for latency)
dog.histogram("payment.duration_ms", durationMs, { provider: "stripe" });

// Distribution (recommended over histogram for percentiles)
dog.distribution("api.response_time", responseMs);
```

Custom metrics in Datadog count toward billing; keep cardinality in check.

## Gotchas
- Each unique tag combination creates a new metric context (billable)
- Distributions are more accurate than histograms for percentile calculation at scale
- Flush interval is 10s by default; reduce for real-time dashboards

## Related
- `datadog-apm-setup.md`
- `prometheus-labels-best-practices.md`
