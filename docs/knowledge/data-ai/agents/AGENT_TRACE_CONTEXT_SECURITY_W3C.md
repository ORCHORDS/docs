# Secure Trace Context Propagation Across Agent Boundaries

## Scope

W3C Trace Context standardizes the `traceparent` and `tracestate` HTTP headers used to correlate distributed work. Agents often cross model gateways, policy services, tool servers, queues, and partner domains, so propagation is valuable. It also creates a security and privacy channel: identifiers supplied by an untrusted caller can poison correlation, and vendor state can leak topology or tenant information.

This article focuses on safely accepting, creating, forwarding, and storing trace context. It does not define agent-specific span names or replace authentication. A trace identifier is correlation metadata, never proof of identity, consent, or authorization.

## Implementation workflow

Document every ingress and egress where trace headers may appear, including HTTP, asynchronous messages, webhooks, and protocol adapters. Classify boundaries as internal, controlled partner, or public. Define whether each boundary accepts an upstream context, starts a new trace with a link, forwards selected `tracestate`, or strips all incoming state.

Implement W3C parsing exactly: validate version, field lengths, hexadecimal constraints, prohibited all-zero identifiers, and future-version handling. Invalid `traceparent` causes creation of a new context rather than partial reuse. Keep parsing separate from authorization middleware so no application decision depends on a trace value.

At public ingress, consider starting a new internal trace and linking to a valid external context when the telemetry system supports links. This limits hostile trace joining while preserving diagnostic association. At egress, forward context only to destinations that need distributed correlation. Apply a boundary policy to `tracestate`, whose list-members are vendor-defined and may carry information inappropriate for another domain.

For asynchronous work, serialize context in a documented message envelope. Consumers should create a child span for single-parent work or links for batch and fan-in processing. Record causal agent task identifiers as separate validated attributes rather than overloading trace IDs.

## Controls

Cap header sizes and enforce the W3C limits before allocation or logging. Never place user IDs, email addresses, prompts, credentials, resource names, or security classifications in `traceparent` or `tracestate`. Protect telemetry export with authenticated transport and least-privilege collector credentials. Restrict who can query traces because correlated tool and model metadata can reveal sensitive activity even without payloads.

Regenerate context at boundaries where accepting external correlation could join unrelated tenants. Sanitize log output to prevent control-character injection. Sampling flags are advisory telemetry input; they must not enable verbose sensitive logging or bypass local collection policy. Apply retention independently from business records and avoid recording raw model inputs by default.

## Validation evidence

Conformance tests should cover valid version 00 headers, malformed lengths, non-hex characters, zero IDs, extra fields, multiple headers, oversized `tracestate`, and unknown future versions according to the specification. End-to-end tests should show one authorized workflow correlating across services while two tenants using the same attacker-supplied header remain isolated by the boundary policy.

Capture evidence of header transformations at each boundary, collector access controls, retention settings, and sampling decisions. Verify that traces remain useful when payload capture is disabled. Scan telemetry for prohibited personal or credential patterns. Test queue retries and fan-out to ensure they preserve causal relationships without creating false parentage.

## Failure handling

On malformed or prohibited context, discard it, create fresh context if tracing is enabled, and continue the business request unless another independent control rejects it. Rate-limit repeated malformed input and emit a bounded security event without reflecting attacker-controlled content. If trace data leaks, restrict query access, stop the offending exporter, rotate collector credentials if needed, and apply deletion procedures to affected backends.

When correlation breaks, do not compensate by logging full prompts. Use release manifests, task IDs, links, and bounded diagnostic sampling. Record gaps explicitly so operators do not infer an unbroken causal chain from incomplete evidence.

## Canonical sources

- W3C Trace Context Recommendation: https://www.w3.org/TR/trace-context/
- W3C Baggage Recommendation: https://www.w3.org/TR/baggage/
- OpenTelemetry specification, context: https://opentelemetry.io/docs/specs/otel/context/
