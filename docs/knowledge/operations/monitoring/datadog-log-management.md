# datadog-log-management

**Issue:** Shipping and managing logs in Datadog Log Management
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Application logs need centralized storage, parsing, and correlation with APM traces in Datadog.

## Pattern / Solution
Configure JSON logging with trace injection:
```typescript
import pino from "pino";
import tracer from "dd-trace";

const logger = pino({
  formatters: {
    log(obj) {
      const span = tracer.scope().active();
      if (span) {
        const ctx = span.context();
        obj.dd = {
          trace_id: ctx.toTraceId(),
          span_id: ctx.toSpanId(),
          service: "my-api",
          env: process.env.NODE_ENV,
        };
      }
      return obj;
    },
  },
});
```

Datadog agent log collection:
```yaml
# /etc/datadog-agent/conf.d/app.d/conf.yaml
logs:
  - type: file
    path: /var/log/app/*.log
    service: my-api
    source: nodejs
    tags:
      - env:production
```

## Gotchas
- Logs must be JSON-formatted for automatic field extraction
- `dd.trace_id` format differs from OTel; use dd-trace injection, not manual
- Log retention defaults to 15 days; increase in organization settings

## Related
- `datadog-apm-setup.md`
- `log-structured-logging.md`
- `log-correlation-ids.md`
