# opentelemetry-overview

**Issue:** Understanding the OpenTelemetry project and its components
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams evaluate multiple observability vendors and need a vendor-neutral instrumentation standard.

## Pattern / Solution
OpenTelemetry (OTel) provides:
- **API** — language-specific interfaces for emitting telemetry (no-op by default)
- **SDK** — implementation of the API with exporters and processors
- **Collector** — agent/gateway to receive, process, and export telemetry
- **Semantic Conventions** — standard attribute names (http.method, db.system, etc.)

Signal support matrix:
| Signal  | Stability |
|---------|-----------|
| Traces  | Stable    |
| Metrics | Stable    |
| Logs    | Stable    |
| Profiles| Beta      |

Data flow:
```
App (SDK) → OTLP → Collector → Prometheus / Jaeger / Loki / Datadog
```

Protocol: OTLP (OpenTelemetry Protocol) over gRPC or HTTP/protobuf.

## Gotchas
- OTel API is stable but SDK configuration changes between minor versions
- Not all languages have feature parity; check maturity per language
- Collector adds a hop; skip for low-traffic services, use for fan-out/filtering

## Related
- `opentelemetry-sdk-setup.md`
- `opentelemetry-collector-pipelines.md`
- `opentelemetry-auto-instrumentation.md`
