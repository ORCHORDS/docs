# zipkin-integration

**Issue:** Sending traces to Zipkin from OTel-instrumented applications
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Existing infrastructure uses Zipkin and teams need to ship OTel traces to it without replacing the backend.

## Pattern / Solution
```typescript
import { ZipkinExporter } from "@opentelemetry/exporter-zipkin";

const sdk = new NodeSDK({
  traceExporter: new ZipkinExporter({
    url: "http://zipkin:9411/api/v2/spans",
    serviceName: "my-service",
  }),
});
```

OTel Collector can also export to Zipkin:
```yaml
exporters:
  zipkin:
    endpoint: http://zipkin:9411/api/v2/spans
    format: proto

service:
  pipelines:
    traces:
      exporters: [zipkin]
```

Zipkin Docker:
```bash
docker run -d -p 9411:9411 openzipkin/zipkin:3
```

## Gotchas
- Zipkin does not support OTel metrics or logs; use only for traces
- B3 propagation (Zipkin format) may conflict with W3C traceparent; configure propagators explicitly
- Zipkin's storage defaults to in-memory; configure MySQL or Elasticsearch for production

## Related
- `jaeger-tracing-setup.md`
- `opentelemetry-collector-pipelines.md`
