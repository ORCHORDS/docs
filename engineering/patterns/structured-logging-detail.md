# structured-logging-detail

**Issue:** Structured JSON logging — best practices
**Date:** 2026-08-09
**Status:** documented

## Symptom
Logs are "User 4821 failed login from 10.0.0.5 after
3 attempts." You can't query by user_id. You can't
filter by status. You can't aggregate. You wish you
had JSON logs.

## Root cause
**Plaintext logs are not queryable.** Use structured
JSON.

**Source:** LogPulse + JSONic 2026.

## The "structured logging" concept

For JSON logs:
```json
{
  "event": "login_failed",
  "user_id": 4821,
  "src_ip": "10.0.0.5",
  "attempts": 3,
  "level": "warn"
}
```

The format is JSON.

## The "JSON log fields" pattern

For standard schema:
```json
{
  "timestamp": "2026-08-09T12:00:00Z",
  "level": "info|warn|error|debug",
  "service": "service-name",
  "environment": "production",
  "version": "1.2.3",
  "correlation_id": "abc-123",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "event": "user_signed_up",
  "user_id": 4821,
  "msg": "User signed up via email"
}
```

The schema is standard.

## The "log level" pattern

For levels:
- **ERROR:** Failure requiring attention
- **WARN:** Unexpected but handled
- **INFO:** Normal business events
- **DEBUG:** Off in prod by default
- **TRACE:** Per-step method tracing

The level is per severity.

## The "log level rules" pattern

For use:
- **Production default:** INFO
- **Investigating:** Temporarily DEBUG
- **Alerting:** ERROR only
- **Healthchecks:** Filter out
- **Per request:** % sampled at DEBUG

The rules are per situation.

## The "correlation ID" pattern

For correlation:
- **Assign:** At request entry
- **Header:** `X-Correlation-ID` (or `traceparent`)
- **Generate:** UUID if missing
- **Propagate:** Through all calls
- **Log:** In every line

The correlation flows.

## The "Pino" pattern

For Node.js:
```typescript
import pino from "pino";

const logger = pino({
  level: process.env.LOG_LEVEL ?? "info",
  redact: {
    paths: [
      "req.headers.authorization",
      "req.headers.cookie",
      "*.password",
      "*.creditCard",
    ],
    censor: "[REDACTED]",
  },
});

const childLogger = logger.child({ requestId: "req-123" });
childLogger.info({ userId: 4821, event: "login" });
```

The Pino is the lib.

## The "structlog" pattern

For Python:
```python
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)

log = structlog.get_logger()
log.info("user_login", user_id=4821, src_ip="10.0.0.5")
```

The structlog is the lib.

## The "Winston" pattern

For Node.js (alt):
```typescript
import winston from "winston";

const logger = winston.createLogger({
  level: "info",
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [new winston.transports.Console()],
});
```

The Winston is the alt.

## The "redaction" pattern

For redaction:
- **Authorization headers**
- **Cookies**
- **Passwords**
- **Credit card numbers**
- **SSN / PII**
- **API keys**
- **JWT tokens**

The redaction is required.

## The "sensitive pattern" pattern

For sanitization:
```typescript
// Allowlist approach (preferred)
const SAFE_FIELDS = ["user_id", "src_ip", "event"];
// Only log these, drop everything else

// Or denylist with regex
const SENSITIVE = [
  /password/i,
  /credit.?card/i,
  /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/,
];
```

The sanitization is built in.

## The "event naming" pattern

For names:
- **Past tense:** order_placed, payment_failed
- **Lowercase:** snake_case
- **Stable:** Don't change per request
- **Specific:** Avoid "operation_done"

The name is stable.

## The "message vs event" pattern

For fields:
- **event:** Stable name (order_placed)
- **msg:** Human detail (order placed for $50)
- **Put data in:** Fields, not message

The pattern is split.

## The "field standardization" pattern

For fields:
- **user_id, NOT uid, userId, user**
- **request_id, NOT reqId, requestId**
- **src_ip, NOT clientIp, remoteAddress**
- **Consistent across services**

The names are standard.

## The "child logger" pattern

For per-request:
```typescript
// In middleware
req.log = logger.child({
  requestId: req.headers["x-request-id"] ?? crypto.randomUUID(),
  userId: req.user?.id,
});

// In handlers
req.log.info({ event: "order_placed", orderId: 123 });
```

The child binds context.

## The "OpenTelemetry integration" pattern

For OTel:
```typescript
import { trace, context } from "@opentelemetry/api";

const span = trace.getActiveSpan();
const { traceId, spanId } = span?.spanContext() ?? {};

// Inject into log
logger.info({
  trace_id: traceId,
  span_id: spanId,
  event: "process_order",
});
```

The trace is in log.

## The "Pino + OTel" pattern

For integration:
```typescript
// Pino has built-in OTel support
const logger = pino({
  mixin: () => {
    const span = trace.getActiveSpan();
    if (!span) return {};
    const { traceId, spanId } = span.spanContext();
    return { trace_id: traceId, span_id: spanId };
  },
});
```

The mixin injects.

## The "log level adjustment" pattern

For runtime:
```typescript
// Expose protected endpoint
app.post("/admin/log-level", (req, res) => {
  const { level } = req.body;
  if (["trace", "debug", "info", "warn", "error"].includes(level)) {
    logger.level = level;
    res.json({ level });
  } else {
    res.status(400).json({ error: "Invalid level" });
  }
});
```

The level is dynamic.

## The "log volume" pattern

For volume:
- **Healthchecks:** Filter
- **Heartbeats:** Filter
- **Per-request DEBUG:** Sample 1%
- **High-frequency:** Suppress or sample
- **Cost:** Per GB ingested

The volume is controlled.

## The "log retention" pattern

For retention:
- **Hot:** 7-30 days (searchable)
- **Warm:** 90 days (compressed)
- **Cold:** 1-7 years (archive, compliance)
- **Tier:** Per cost

The retention is per tier.

## The "GDPR + logs" pattern

For GDPR:
- **Minimize:** Don't log PII
- **Pseudonymize:** Hash user IDs
- **Retention:** Per GDPR (limit)
- **Right to erasure:** Suppress in logs
- **Audit:** Quarterly

The GDPR is applied.

## The "log shipping" pattern

For shipping:
- **Agent:** Vector, Fluent Bit, Filebeat
- **Direct:** OTLP, syslog
- **Cloud-native:** CloudWatch, Stackdriver
- **SaaS:** Datadog, Splunk

The shipper is per stack.

## The "log query" pattern

For queries:
- **Datadog:** `@user_id:4821 AND @event:login_failed`
- **Loki:** `{service="auth"} |= "user_id=4821"`
- **Splunk:** `index=auth user_id=4821 event=login_failed`
- **CloudWatch:** Parse JSON fields

The query is per backend.

## The "log review" pattern

For review:
- **Per log statement, ask:**
  - Does anyone look at this?
  - Does it drive an alert?
  - Would we miss it during incident?
- **If no:** Remove or DEBUG
- **If yes:** Keep

The review is periodic.

## The "log schema evolution" pattern

For evolution:
- **Versioned:** schema_version field
- **Backward compatible:** Add new fields
- **Breaking change:** New event name
- **Document:** In repo

The schema evolves.

## The "log + trace correlation" pattern

For correlation:
- **trace_id:** In every log
- **span_id:** Current span
- **Search:** By trace_id in logs
- **Click:** From log to trace UI

The correlation works.

## The "unstructured log" anti-pattern

For unstructured:
- **Issue:** Not parseable
- **Fix:** JSON

The logs are JSON.

## The "no correlation ID" anti-pattern

For no correlation:
- **Issue:** Can't trace across services
- **Fix:** Propagate correlation_id

The correlation is required.

## The "PII in logs" anti-pattern

For PII:
- **Issue:** GDPR violation
- **Fix:** Allowlist + redact

The PII is not logged.

## The "DEBUG in prod" anti-pattern

For DEBUG:
- **Issue:** Volume + cost
- **Fix:** INFO default, temp DEBUG

The DEBUG is off.

## The "log + metric + trace" pattern

For observability:
- **Logs:** Discrete events
- **Metrics:** Aggregated
- **Traces:** Request flow
- **All correlated:** By trace_id

The three are linked.

## Verification
- **Test:** Logs are JSON
- **Test:** correlation_id flows
- **Test:** Redaction works
- **Test:** Levels are correct
- **Test:** OTel trace_id present

## Gotchas
- **The "unstructured" anti-pattern.** JSON.
- **The "no correlation" anti-pattern.** Propagate.
- **The "PII in logs" anti-pattern.** Redact.

## Related
- `patterns/observability-three-pillars.md`
- `patterns/distributed-tracing-otel.md`
- `patterns/slo-error-budget-deep-dive.md`
- `patterns/incident-response.md`
- `security/gdpr-article-17-erasure.md`
- GreprSum: https://www.grepr.ai/blog/structured-logging-best-practices
- LogPulse: https://logpulse.io/guides/structured-logging/
- JSONic: https://jsonic.io/guides/json-logging
