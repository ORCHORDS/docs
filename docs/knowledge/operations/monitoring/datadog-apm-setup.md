# datadog-apm-setup

**Issue:** Enabling Datadog APM for distributed tracing and service maps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams using Datadog want APM traces correlated with metrics and logs in the same platform.

## Pattern / Solution
```bash
# Install dd-trace for Node.js
npm install dd-trace
```

```typescript
// Must be first line before any require/import
import tracer from "dd-trace";
tracer.init({
  service: "my-api",
  env: process.env.NODE_ENV,
  version: process.env.SERVICE_VERSION,
  logInjection: true,    // inject trace_id into logs
  runtimeMetrics: true,  // V8 heap, GC metrics
  profiling: true,       // continuous profiling
});
export default tracer;
```

Environment variables (for agent):
```bash
DD_AGENT_HOST=datadog-agent
DD_TRACE_AGENT_PORT=8126
DD_ENV=production
DD_SERVICE=my-api
DD_VERSION=1.2.3
```

Docker agent:
```yaml
services:
  datadog-agent:
    image: datadog/agent:7
    environment:
      DD_API_KEY: ${DD_API_KEY}
      DD_APM_ENABLED: "true"
      DD_LOGS_ENABLED: "true"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
```

## Gotchas
- `logInjection: true` requires a JSON-compatible logger (pino, winston)
- Profiling adds ~2% CPU overhead; test before enabling in high-traffic services
- Trace sampling is controlled by the agent, not the SDK

## Related
- `datadog-custom-metrics.md`
- `datadog-log-management.md`
- `opentelemetry-sdk-setup.md`
