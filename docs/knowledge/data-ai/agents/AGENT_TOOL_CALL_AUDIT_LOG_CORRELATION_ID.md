# Tool Call Audit Log Correlation Identifiers Using OpenTelemetry GenAI Conventions

## Scope

An agent's tool calls scatter across traces, logs, and downstream system records. Without correlation, the operator cannot answer the question "what was the agent doing when this downstream action occurred?" with confidence. Correlation identifiers make the answer possible by binding a tool call's distributed evidence to a single traceable lineage that survives tool boundaries, retries, and model changes.

The OpenTelemetry GenAI semantic conventions define attribute names and span semantics for generative AI systems, including conventions for tool calls. This article applies those conventions as the contract for audit correlation, treating the OTel attribute names as the minimum field set rather than an optional enhancement. The correlation identifier is what turns a collection of logs into evidence.

## Workflow or implementation guidance

1. Generate the correlation identifier at the request entry point and propagate it through every subsequent step. The OpenTelemetry trace and span identifiers are the primary correlation keys; agent-specific correlation fields extend rather than replace them.
2. For every tool call, emit a span with the GenAI semantic convention attributes: `gen_ai.system`, `gen_ai.request.model`, `gen_ai.operation.name`, the tool identifier, and arguments under a defined attribute. The schema is published and should be followed exactly so cross-tool correlation works.
3. Pair each tool call span with a model invocation span that produced the call. The tool span is the effect; the model span is the cause. Correlation must let an investigator walk from effect to cause without guessing which model invocation led to a given tool call.
4. Record arguments and results in a form that supports correlation without leaking sensitive content. Hash or pseudonymize sensitive values where possible, and keep the structural facts - argument keys, result shape, error type - in the audit record. The audit goal is correlation, not value retention.
5. Carry the correlation identifier into downstream systems. Pass `traceparent` on outbound HTTP requests, set correlation identifiers on database sessions where supported, and propagate to background work via task identifiers. Cross-system correlation is where audit logs earn their keep.
6. Emit one span per attempt on retry, not a single span with multiple internal attempts. A retry storm is invisible when the spans are aggregated, and the audit log should make retry behavior observable. Attempt counts should be carried as span attributes rather than hidden in logs.
7. Standardize error representation on the OTel conventions for status and events. Free-form error strings are harder to correlate than structured events with consistent attribute names. A consistent error vocabulary is a force multiplier for analysis.
8. Treat the audit log as a security log. Apply the same access controls, retention rules, and integrity protections to the audit log as to other security-relevant evidence. A tool-call audit log without those properties is decoration rather than control.

## Controls

Span emission must be guaranteed under failure. A tool call that crashes before emitting a span leaves a hole in the audit, and a span that survives only on the happy path distorts analysis. Ensure span emission is in the failure path, ideally with a finalizer or context manager that emits even on exception.

Sampling and audit have a tense relationship. Sampling for performance must not silently drop audit records. Where sampling is applied at the trace level, prefer a configuration where security-relevant traces are exempt from sampling, and where trace-level sampling decisions are recorded.

Time synchronization underpins correlation. Use NTP or equivalent and monitor clock drift; correlation across systems depends on comparable timestamps within an acceptable tolerance. A drift of seconds can break correlation between events that occurred within a single tool call.

## Validation evidence

Demonstrate a happy-path scenario: a user request, a model invocation, a tool call, and a downstream system response, all carrying the same correlation identifier and the expected OTel attributes. Demonstrate that the audit log can be searched by the correlation identifier and that the result reconstructs the full sequence.

Show failure evidence. A tool call that throws, a retry that succeeds, and a downstream system that times out should each be present in the audit log with the same correlation identifier and appropriate OTel attributes for status, exception type, and attempt number. Demonstrate that an aborted tool call still emits its span.

Show cross-system correlation. A downstream service's record carries the correlation identifier and can be joined to the agent's audit log. Show that a downstream record lacking the identifier is detected and investigated rather than accepted as unrelated. Show that argument values can be reconstructed where permitted and remain opaque where they must.

## Failure modes and correction

A common failure is partial attribute adoption, where some spans use OTel conventions and others use legacy or proprietary names. Correlation breaks at the boundary. Correct by enforcing a single vocabulary per environment, validating spans at emission where possible, and reviewing deviations on a defined cadence.

A subtler failure is correlation identifiers that depend on a fragile infrastructure. When the identifier relies on a header propagation mechanism that fails across certain proxies, downstream records appear uncorrelated. Correct by detecting missing identifier headers on entry and refusing or quarantining such requests, and by propagating the identifier through redundant channels where possible.

Another failure is correlation that drifts over time. A property named one thing in last year's logs and something else in this year's logs breaks queries that span the transition. Correct by versioning the attribute vocabulary and maintaining explicit mapping at transition boundaries.

## Limitations

OpenTelemetry GenAI conventions are evolving and may introduce backward-incompatible attribute changes. Cross-vendor adoption of the conventions is uneven, and correlation across vendors may require translation layers. The conventions do not specify every domain-specific tool attribute, and a project inevitably extends the vocabulary, which adds maintenance cost. The audit log is also only as reliable as the underlying infrastructure: spans lost to a crash without span emission are gaps, not absences.

## Canonical sources

- **OpenTelemetry, Semantic Conventions for Generative AI systems:** https://opentelemetry.io/docs/specs/semconv/gen-ai/
- **OpenTelemetry, GenAI spans reference:** https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/
- **W3C, Trace Context Level 2 (cross-system propagation underpinning OTel correlation):** https://www.w3.org/TR/trace-context-2/
