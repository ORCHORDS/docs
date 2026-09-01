# Agent Telemetry with OpenTelemetry GenAI Semantic Conventions

## Purpose

Agent operations cross model calls, retrieval, tool execution, orchestration, and external services. OpenTelemetry provides common tracing, metrics, logs, context propagation, and semantic conventions. Its generative AI semantic conventions define names and structures for telemetry about model operations and agent-related workflows. Using them can make telemetry portable across instrumentation and backends, while ordinary OpenTelemetry spans remain appropriate for databases, HTTP, queues, and other dependencies.

Semantic-convention maturity can vary by signal and release. Implementations should pin a documented OpenTelemetry specification and semantic-convention version, inspect the stability labels for the attributes they use, and avoid claiming a convention is stable unless the cited version says so.

## Implementation workflow

1. Define observability questions first: model latency, tool failure, token usage, handoff delay, policy denial, and end-to-end run outcome. Do not collect fields without a use case and owner.
2. Choose the GenAI operation and span model that matches each action. Create spans around actual model or agent operations rather than every internal function. Instrument downstream HTTP, database, messaging, and tool calls with their applicable conventions.
3. Configure W3C Trace Context propagation across trusted service boundaries. Link asynchronous work when direct parent-child propagation does not represent causality.
4. Populate low-risk standardized attributes from runtime facts: operation name, provider or system identifier where defined, request model, response model, finish reasons, and token-usage measurements when available. Follow the exact names and requirements of the pinned convention version.
5. Export through an OpenTelemetry SDK and Collector. Apply resource attributes that identify service and deployment without embedding secrets or high-cardinality session content.
6. Build dashboards and alerts from bounded dimensions. Keep run IDs and user-specific identifiers in trace-search fields only when needed, not as unbounded metric labels.

## Controls

Prompt and completion content can contain credentials, personal data, confidential documents, and attacker-controlled strings. Content capture should be disabled by default. If a justified debugging mode records it, require explicit authorization, sampling, redaction, encryption, short retention, and access logging. Attribute limits must prevent oversized content from overwhelming exporters.

Treat telemetry as untrusted input at the backend. Escape displayed data, enforce query authorization, and isolate tenants. Do not let a remote caller choose resource attributes or service identity. Generate trace IDs through the SDK and accept incoming trace context only according to boundary policy; public requests may carry attacker-chosen identifiers even though they cannot forge protected logs by themselves.

Prevent cardinality explosions. Model-generated tool names, URLs, prompt fragments, error strings, and document IDs should not become metric attributes. Normalize known tool identifiers and error classes. Use exemplars or trace links to investigate individual events.

## Validation and evidence

Run a deterministic test workflow containing one model request, one successful tool call, one denied tool call, and one asynchronous handoff. Inspect exported traces to verify operation naming, parentage or links, status, timestamps, token units, and correlation with logs. Confirm downstream libraries propagate `traceparent` and `tracestate` according to policy.

Inject exporter outage, Collector backpressure, oversized attributes, invalid incoming trace headers, and sampling changes. Agent execution should not depend on telemetry success unless a separately documented audit requirement says otherwise. Measure dropped spans, queue utilization, export failures, and Collector refusal metrics.

Keep the instrumentation source revision, pinned semantic-convention version, Collector configuration, redaction tests, sample sanitized traces, dashboard definitions, and alert tests as evidence. Review telemetry after upgrades because an attribute rename or stability change may split dashboards or leak newly captured data.

## Failure handling

Telemetry export failures should degrade observability, not alter the tool operation or cause uncontrolled retries. Bound SDK queues and memory, prefer dropping telemetry over exhausting the agent, and alert from exporter health signals. Preserve security audit events through their dedicated durable path rather than assuming best-effort traces are an audit ledger.

If sensitive content is exported, disable the responsible instrumentation or Collector route, restrict backend access, identify affected telemetry using time and resource filters, and follow the organization’s incident and deletion procedures. Rotate credentials only when exposure evidence warrants it. Correct dashboards when convention changes produce incompatible fields; do not merge attributes with superficially similar names without checking semantics.

## Canonical sources

- OpenTelemetry, *Generative AI semantic conventions*: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- OpenTelemetry, *Trace semantic conventions*: https://opentelemetry.io/docs/specs/semconv/general/trace/
- W3C, *Trace Context*: https://www.w3.org/TR/trace-context/
- OpenTelemetry specification: https://opentelemetry.io/docs/specs/otel/
- OpenTelemetry Collector documentation: https://opentelemetry.io/docs/collector/
