# opentelemetry-auto-instrumentation

**Issue:** Enabling automatic instrumentation for common frameworks without code changes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers must manually instrument HTTP, database, and cache calls, missing coverage on third-party libraries.

## Pattern / Solution
```typescript
// Auto-instrumentation via getNodeAutoInstrumentations
import { getNodeAutoInstrumentations } from "@opentelemetry/auto-instrumentations-node";

const sdk = new NodeSDK({
  instrumentations: [
    getNodeAutoInstrumentations({
      "@opentelemetry/instrumentation-http": {
        ignoreIncomingRequestHook: (req) =>
          req.url?.includes("/health") ?? false,
      },
      "@opentelemetry/instrumentation-pg": { enhancedDatabaseReporting: true },
      "@opentelemetry/instrumentation-redis": { dbStatementSerializer: "default" },
    }),
  ],
});
```

Java zero-code instrumentation:
```bash
java -javaagent:opentelemetry-javaagent.jar \
  -Dotel.service.name=my-service \
  -Dotel.exporter.otlp.endpoint=http://collector:4317 \
  -jar app.jar
```

Python:
```bash
opentelemetry-instrument --service-name my-service python app.py
```

## Gotchas
- Auto-instrumentation patches modules at load time; load SDK before any imports
- `enhancedDatabaseReporting` captures query text; disable if queries contain PII
- Java agent version must match application Java version

## Related
- `opentelemetry-sdk-setup.md`
- `opentelemetry-custom-spans.md`
