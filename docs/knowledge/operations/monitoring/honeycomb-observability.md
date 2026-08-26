# honeycomb-observability

**Issue:** Using Honeycomb for high-cardinality event-driven observability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Prometheus pre-aggregates data, losing the ability to query arbitrary combinations of high-cardinality attributes after the fact.

## Pattern / Solution
Honeycomb stores raw events and allows arbitrary slicing at query time.

```typescript
import Libhoney from "libhoney";

const honey = new Libhoney({
  writeKey: process.env.HONEYCOMB_API_KEY,
  dataset: "production",
});

// Rich event with many attributes
const event = honey.newEvent();
event.add({
  service: "api",
  endpoint: "/checkout",
  user_id: userId,
  tenant_id: tenantId,
  duration_ms: elapsed,
  db_query_count: queryCount,
  cache_hits: cacheHits,
  payment_provider: "stripe",
  cart_item_count: cart.length,
});
event.send();
```

BubbleUp query to find what's different in slow requests:
```
HEATMAP(duration_ms)
WHERE duration_ms > p99
```

## Gotchas
- Honeycomb pricing is based on events per month; high-traffic services need sampling
- Unlike Prometheus, there are no pre-defined dashboards; all views are ad-hoc
- Use OTel SDK with Honeycomb exporter for standardized instrumentation

## Related
- `opentelemetry-sdk-setup.md`
- `log-sampling-strategies.md`
- `metrics-vs-logs-vs-traces.md`
