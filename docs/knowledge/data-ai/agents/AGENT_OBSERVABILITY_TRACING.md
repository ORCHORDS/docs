# Agent Observability and Tracing

## Purpose

Agentic workflows often span model calls, tool calls, retrieval, handoffs, retries, and external services. Observability should make those steps inspectable without logging sensitive prompts, credentials, or private data unnecessarily.

## What to trace

Useful traces commonly include:

- workflow or run identifier;
- agent or component name;
- model invocation boundaries;
- tool name and execution status;
- latency and retry counts;
- token or usage measurements where available;
- handoff or delegation boundaries;
- error category and recovery path; and
- final completion or cancellation state.

Keep correlation identifiers stable enough to follow one workflow across components, but avoid embedding secrets or raw personal data in identifiers.

## Span design

Represent meaningful operations as separate spans rather than one opaque workflow span. This makes it possible to distinguish model latency from tool latency and to identify repeated retries, slow dependencies, or failing handoffs.

OpenTelemetry's GenAI semantic conventions define attributes and span patterns for generative-AI operations. Implementations should follow the version of those conventions supported by their telemetry stack and should treat experimental conventions as subject to change.

## Sensitive data

Prompt bodies, model outputs, retrieved documents, and tool parameters can contain secrets or personal information. Prefer metadata-first telemetry. Capture full content only when there is a specific debugging or evaluation need, access is controlled, retention is bounded, and the data classification permits it.

## Metrics to derive

Tracing data can support metrics such as:

- successful workflow rate;
- tool failure rate;
- retry frequency;
- end-to-end latency;
- model and tool latency distributions;
- handoff count;
- cancellation rate; and
- cost or usage per completed workflow where reliable usage data exists.

Metrics should not be interpreted without context. For example, fewer tool calls may indicate efficiency, but it can also indicate that an agent skipped required work.

## Operational use

Use traces to answer concrete questions: where did a workflow fail, which dependency was slow, why was a tool retried, which handoff lost context, or which step consumed most of the run time. Avoid collecting telemetry merely because it is available.

## References

- OpenTelemetry — Generative AI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- OpenTelemetry — Traces: https://opentelemetry.io/docs/concepts/signals/traces/

## Scope note

This article describes project-neutral observability patterns. Exact fields, retention periods, and content-capture rules depend on the telemetry backend and the system's privacy and security requirements.
