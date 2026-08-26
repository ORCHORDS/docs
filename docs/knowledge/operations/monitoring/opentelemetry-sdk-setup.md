# opentelemetry-sdk-setup

**Issue:** Initializing the OpenTelemetry SDK in a Node.js application
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Application emits no telemetry because the SDK is not initialized before the first request.

## Pattern / Solution
```typescript
// instrumentation.ts — must be loaded before any other module
import { NodeSDK } from "@opentelemetry/sdk-node";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-grpc";
import { OTLPMetricExporter } from "@opentelemetry/exporter-metrics-otlp-grpc";
import { PeriodicExportingMetricReader } from "@opentelemetry/sdk-metrics";
import { Resource } from "@opentelemetry/resources";
import { SEMRESATTRS_SERVICE_NAME, SEMRESATTRS_SERVICE_VERSION } from "@opentelemetry/semantic-conventions";

const sdk = new NodeSDK({
  resource: new Resource({
 ?? "unknown",
 ?? "0.0.0",
  }),
  traceExporter: new OTLPTraceExporter({
    url: process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? "http://localhost:4317",
  }),
  metricReader: new PeriodicExportingMetricReader({
    exporter: new OTLPMetricExporter(),
    exportIntervalMillis: 30000,
  }),
});

sdk.start();
process.on("SIGTERM", () => sdk.shutdown());
```

Start with: `node --require ./instrumentation.js server.js`

## Gotchas
- SDK must be required/imported before application code
- Use `OTEL_SDK_DISABLED=true` env var to disable in tests
- `shutdown()` must be called on process exit to flush pending spans

## Related
- `opentelemetry-overview.md`
- `opentelemetry-auto-instrumentation.md`
- `opentelemetry-custom-spans.md`
