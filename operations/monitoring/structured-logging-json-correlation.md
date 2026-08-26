# Structured Logging — JSON Format, Correlation IDs, and Schema Design

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application logs are unstructured text strings — `console.log`
output that varies per developer, with no consistent format. Searching
for "why did this request fail?" requires grepping through gigabytes of
text with fragile regex patterns. You cannot trace a request across
microservices because there is no correlation ID. Log aggregation tools
(Datadog, Grafana Loki, Elasticsearch) ingest your logs but cannot
index or filter on structured fields. Dashboards based on log data
require expensive regex parsing at query time.

## Context

Structured logging emits log events as machine-readable key-value pairs
(typically JSON) instead of free-form text. Every major observability
platform — Datadog, Grafana Loki, Elasticsearch, Splunk, CloudWatch
Logs — can parse, filter, and aggregate structured logs automatically.
In 2026, the standard practice is JSON-formatted logs with consistent
field names, correlation IDs propagated via OpenTelemetry context, and
log levels that follow a severity hierarchy. OpenTelemetry's log SDK
automatically injects `trace_id` and `span_id` into every log record,
correlating logs with distributed traces without per-call-site effort.

## Unstructured vs. structured

```
Unstructured:
  [2026-08-16 14:30:22] ERROR: Payment failed for user 12345, amount $99.99

Structured (JSON):
  {
    "timestamp": "2026-08-16T14:30:22.456Z",
    "level": "error",
    "message": "Payment failed",
    "service": "payment-api",
    "user_id": "12345",
    "amount": 99.99,
    "currency": "USD",
    "error_code": "card_declined",
    "trace_id": "abc123def456",
    "span_id": "789ghi",
    "request_id": "req_aB3cD4eF"
  }
```

## Log schema standard

```json
{
  "timestamp": "ISO 8601 with timezone (required)",
  "level": "debug|info|warn|error|fatal (required)",
  "message": "Human-readable description (required)",
  "service": "Service name (required)",
  "environment": "production|staging|development",

  "trace_id": "OpenTelemetry trace ID",
  "span_id": "OpenTelemetry span ID",
  "request_id": "Unique request identifier",

  "user_id": "Authenticated user (if applicable)",
  "tenant_id": "Multi-tenant identifier",

  "error.type": "Error class name",
  "error.message": "Error description",
  "error.stack": "Stack trace (error level only)",

  "http.method": "GET|POST|PUT|DELETE",
  "http.url": "Request URL path",
  "http.status_code": 200,
  "http.duration_ms": 142,

  "host": "hostname or pod name",
  "version": "Application version / git SHA"
}
```

## Correlation ID propagation

```
Client → API Gateway → Service A → Service B → Database
  │         │              │            │
  └─── request_id: "req_aB3cD4eF" ──────┘
  └─── trace_id:   "abc123def456" ───────┘

Every log line includes the same trace_id and request_id,
enabling end-to-end request tracing across services.
```

### Implementation (Node.js with OpenTelemetry)

```typescript
import { context, trace } from '@opentelemetry/api';
import pino from 'pino';

const logger = pino({
  formatters: {
    log(obj) {
      const span = trace.getSpan(context.active());
      if (span) {
        const ctx = span.spanContext();
        return {
          ...obj,
          trace_id: ctx.traceId,
          span_id: ctx.spanId,
        };
      }
      return obj;
    },
  },
  timestamp: pino.stdTimeFunctions.isoTime,
});

// Usage — trace context is injected automatically
logger.info({ user_id: '12345', action: 'login' }, 'User logged in');
```

### Implementation (Python with structlog)

```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger()

# Bind context for the request lifecycle
log = logger.bind(
    request_id="req_aB3cD4eF",
    user_id="12345",
    service="payment-api",
)

log.info("payment_processed", amount=99.99, currency="USD")
# {"timestamp":"2026-08-16T14:30:22Z","level":"info",
#  "event":"payment_processed","request_id":"req_aB3cD4eF",
#  "user_id":"12345","service":"payment-api",
#  "amount":99.99,"currency":"USD"}
```

## Log levels

| Level | When to use | Examples |
|---|---|---|
| `fatal` | Process must exit | Unrecoverable state, missing critical config |
| `error` | Operation failed, needs attention | Payment declined, database connection lost |
| `warn` | Unexpected but recoverable | Retry succeeded, deprecated API called |
| `info` | Normal operations | Request completed, user logged in, deploy started |
| `debug` | Development diagnostics | SQL queries, cache hits/misses, function entry/exit |

```
Production: info and above
Staging: debug and above
Development: all levels

Never log at debug level in production by default —
use dynamic log level adjustment for targeted debugging.
```

## Anti-patterns

- **Logging sensitive data** — including passwords, API keys, credit
  card numbers, or PII in log fields. Structured logs are indexed
  and searchable, making sensitive data discoverable. Redact or
  mask sensitive fields before logging.
- **Inconsistent field names** — using `userId`, `user_id`,
  `userID`, and `uid` across different services. Queries and
  dashboards break when field names vary. Agree on a schema and
  enforce it with shared logging libraries.
- **High-cardinality fields** — logging unique values (UUIDs,
  timestamps, full URLs with query params) as indexed fields. This
  explodes index size and increases cost. Use high-cardinality values
  in the message, not as indexed fields.
- **Logging everything at info** — using `info` for both "server
  started" and per-request details. High-volume info logs increase
  cost and noise. Use `debug` for per-request details that are not
  needed in production by default.

## Gotchas

- **Log volume cost** — structured JSON logs are larger than
  unstructured text (field names add overhead). At scale, this
  increases storage and ingestion costs. Use sampling for high-volume
  debug logs and set appropriate retention policies.
- **Stack traces in JSON** — multi-line stack traces break JSON
  formatting if not properly escaped. Use your logging library's
  error serializer, which encodes stack traces as a single JSON
  string field.
- **Console output in containers** — Kubernetes captures container
  stdout/stderr. Ensure your application writes one JSON object per
  line (NDJSON) — no pretty-printing in production. Log aggregators
  parse one line = one event.
- **Dynamic log level changes** — changing log levels in production
  to debug a specific issue requires a restart in most setups. Use
  a feature flag or config endpoint to change log levels without
  redeployment.

## Verification

- All services emit JSON-structured logs to stdout.
- Log schema is documented and consistent across services.
- Correlation IDs (trace_id, request_id) are present in every log.
- Sensitive data is never logged (PII, credentials, tokens).
- Log levels follow the severity hierarchy consistently.
- Logs are queryable by structured fields in the aggregation platform.

## Related

- `documentation/categories/monitoring/opentelemetry-collector-pipelines.md`
- `documentation/categories/monitoring/alerting-strategy-routing-escalation.md`
- `documentation/categories/patterns/observability-patterns.md`

## Source URLs (verified 2026-08-16)

- Structured Logging Guide and Best Practices — https://www.dash0.com/guides/structured-logging-for-modern-applications
- Structured Logging Best Practices for Production 2026 — https://www.grepr.ai/blog/structured-logging-best-practices
- Structured Logging: Best Practices & JSON Examples — https://uptrace.dev/glossary/structured-logging
- JSON Logging: A Quick Guide for Engineers — https://www.dash0.com/guides/json-logging
