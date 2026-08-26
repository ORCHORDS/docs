# jaeger-tracing-setup

**Issue:** Deploying Jaeger for distributed trace collection and visualization
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Distributed traces from OTel-instrumented services have nowhere to land for visualization and querying.

## Pattern / Solution
```yaml
# docker-compose.yml
services:
  jaeger:
    image: jaegertracing/all-in-one:1.58
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
      SPAN_STORAGE_TYPE: elasticsearch
      ES_SERVER_URLS: http://elasticsearch:9200
    ports:
      - "16686:16686"  # UI
      - "4317:4317"    # OTLP gRPC
      - "4318:4318"    # OTLP HTTP
```

Configure OTel SDK to send to Jaeger:
```typescript
new OTLPTraceExporter({ url: "http://jaeger:4317" })
```

For production, deploy Jaeger components separately:
- `jaeger-collector` — receives spans
- `jaeger-query` — serves UI and API
- `jaeger-agent` (legacy) — replaced by OTel Collector

## Gotchas
- `all-in-one` image is for development only; uses in-memory storage
- Production requires Elasticsearch or Cassandra for storage
- Jaeger UI sampling rates should be configured at collector level

## Related
- `opentelemetry-collector-pipelines.md`
- `opentelemetry-custom-spans.md`
- `zipkin-integration.md`
