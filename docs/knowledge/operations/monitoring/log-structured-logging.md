# log-structured-logging

**Issue:** Emitting logs as structured JSON for reliable parsing and querying
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Log lines are free-text strings. Parsing fails on edge cases. Log queries require complex regexes.

## Pattern / Solution
Emit logs as JSON objects with consistent fields: timestamp, level, service, version, trace_id, span_id, message, and context. Use a logging library that enforces structure: pino (Node.js), zerolog (Go), structlog (Python), logrus. Always include trace_id for correlation. Never interpolate variables into the message string — put them as structured fields.

## Gotchas
JSON logging is verbose — log levels control volume. Structured logs are useless without consistent field names across services — define a schema and enforce via lint. Never log PII or secrets in structured fields. Log message field should be a static string; context goes in fields.

## Related
log-correlation-ids, log-sampling-strategies, loki-log-labels, log-security-masking
