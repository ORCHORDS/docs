# Cloudflare Tail Workers: PII minimization and observability boundaries

**Category:** Monitoring
**Author:** ORCHORDS
**Primary source:** [Cloudflare Tail Workers](https://developers.cloudflare.com/workers/observability/logs/tail-workers/)

## Problem

Tail Workers receive execution information after each producer Worker invocation. That information can include logs, exceptions, request metadata, and subrequest context. Exporting it unchanged can create a privacy leak and an unbounded paid processing path.

## Practice

- Treat Tail Worker input as sensitive telemetry, not application-safe event data.
- Apply an allowlist of event fields before forwarding; redact or drop headers, query parameters, cookies, request bodies, and exception content unless explicitly justified.
- Emit stable, low-cardinality attributes for aggregation rather than raw identifiers or free-form logs.
- Define CPU and destination-failure budgets. Tail Workers are billed by CPU time and run after every producer invocation.
- Use native OpenTelemetry export or Workers Logs when custom per-event processing is unnecessary; reserve a Tail Worker for deliberate filtering, routing, or derived signals.
- Test sampling and redaction on representative failures, because error paths often contain the most sensitive values.

## Verification

1. Trigger success, handled-error, and uncaught-error producer paths; inspect the emitted event set.
2. Confirm prohibited fields are absent from every downstream destination.
3. Measure Tail Worker CPU under expected traffic and an error burst.
4. Disable or fail the destination intentionally and verify the chosen loss and alerting behavior.

## Failure modes

- Raw event forwarding exports secrets or personal data from console output and exceptions.
- High-cardinality fields turn telemetry into an expensive, unusable dataset.
- A Tail Worker is used as a default log pipeline when simpler native telemetry would be cheaper and safer.

## Related

- [Cloudflare Tail Workers](https://developers.cloudflare.com/workers/observability/logs/tail-workers/)
