# MCP Distributed Trace Context

## Purpose

MCP 2026-07-28 documents W3C Trace Context propagation in request metadata so a trace can follow a call from a host application through an MCP client, gateway, server, and downstream dependency.

## Guidance

1. Propagate `traceparent` and `tracestate` according to W3C Trace Context semantics.
2. Treat `baggage` as potentially sensitive and apply explicit allow-listing before forwarding it across trust boundaries.
3. Never place access tokens, secrets, full prompts, or sensitive personal data in tracing metadata.
4. Create child spans for significant tool calls and downstream work so latency and failures are attributable.
5. Preserve correlation across MRTR retries while distinguishing individual request attempts.
6. Apply sampling consistently enough to diagnose distributed failures without turning telemetry into an uncontrolled data store.
7. Validate externally supplied trace fields before forwarding them.

## Sources

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- W3C — Trace Context Recommendation: https://www.w3.org/TR/trace-context/

## Scope note

Trace propagation improves observability. It must be paired with data-minimization, retention, and access controls appropriate to the telemetry environment.
