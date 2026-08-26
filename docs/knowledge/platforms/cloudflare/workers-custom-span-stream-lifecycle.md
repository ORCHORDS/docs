# Workers custom spans for stream lifecycle

**Issue:** Cloudflare Workers now exposes `tracing.enterSpan()` and `tracing.startActiveSpan()`. The second form is a lifecycle contract: it does not end when its callback returns, so a stream must end the span on completion, cancellation, and error.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Enable `observability.traces.enabled` and set an explicit head sampling rate.
- Use `enterSpan()` for ordinary synchronous or promise-scoped work; reserve `startActiveSpan()` for work that truly outlives the callback.
- Put `span.end()` in every terminal path and keep attributes low-cardinality and free of credentials, bodies, or user identifiers.
- Record deployed Worker version attributes when correlating a regression.

## Verification

1. Exercise normal completion, consumer cancellation, transform failure, and upstream abort; each produces one ended span.
2. Confirm nested fetch/binding spans occur inside the callback and do not claim parentage after it returns.
3. Validate sampling and monthly observability-event budgets in staging.

## Gotchas

An open manual span is eventually submitted only as a runtime backstop; relying on that yields misleading durations. `startActiveSpan` remains active only during its callback, even though the span can remain open. Non-I/O work may show 0 ms because runtime time does not advance continuously.

## Official sources

- https://developers.cloudflare.com/workers/observability/traces/custom-spans/
- https://developers.cloudflare.com/workers/observability/traces/known-limitations/
