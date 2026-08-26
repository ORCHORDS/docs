# distributed-tracing-architecture

**Issue:** A request crossing a dozen services fails or slows for reasons invisible to any single service's logs: service 7's 200ms database query, service 3's retry storm, or a queue hop that doubled latency. Metrics say error rate is 2 percent but not which path; logs are scattered and lack correlation. Distributed tracing solves this by propagating a trace context (trace id, span ids, flags) through every hop and assembling per-request trees of spans with timing and attributes. The architectural challenges in the OpenTelemetry era are instrumenting without drowning services in overhead, keeping sampling decisions coherent across services, and storing/querying traces at a cost that does not dwarf the application itself — head-based sampling is cheap but blind, tail-based sampling is smart but stateful and operationally tricky.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Instrumentation Architecture

1. **OpenTelemetry as the vendor-neutral layer.** Standardize on OTel SDKs and the W3C Trace Context propagation headers (traceparent/tracestate), not vendor agents, so backends (Tempo, Jaeger, Zipkin, Datadog, Honeycomb) remain swappable. Auto-instrumentation for HTTP, gRPC, databases, and queues covers the bulk of spans with near-zero code; reserve manual spans for business-relevant phases (e.g. a "validate-eligibility" span).
2. **Trace context through every transport.** Context propagation must cover message queues and schedulers, not just request/response: inject context into Kafka/SQS message headers and job payloads so async legs attach to the same trace. Missing this is the most common cause of "traces that end at the queue."
3. **The collector tier is mandatory at scale.** Emit from services to a local OpenTelemetry Collector agent, forwarding to a gateway tier that handles batching, retries, enrichment (env, region, tenant attributes), and — critically — sampling. Application-to-collector keeps SDK failure modes decoupled from vendor outages and lets you change pipeline behavior without redeploys.
4. **Attributes as the query surface.** Traces are only as useful as their dimensions: standardize resource attributes (service.name, service.version, deployment.environment) and span attributes (tenant.id, order.id, feature flags) in a schema enforced by convention or by collector transforms. Cardinality discipline applies — no raw user input as attributes.
5. **Link tracing to logs and metrics.** Inject trace ids into log records and exemplars into metrics so an alert on a RED metric jumps to representative traces. This correlation loop — metric anomaly to trace to log — is the entire point of the architecture; without it, each signal is an island.

## Sampling Strategy

1. **Head-based (decide at trace start).** The SDK samples at the root span and propagates the decision via trace flags; every downstream service honors it, so traces are complete or absent, never partial. It is nearly free, but blind: you sample before knowing whether the request errors or runs slow, so at 1 percent you likely miss the rare expensive failure entirely.
2. **Tail-based (decide at trace end).** The OTel Collector's tailsamplingprocessor buffers all spans per trace and decides after completion: keep all errors, keep traces above a latency threshold, keep rare high-value operations, sample the remainder probabilistically. This is the current best-practice core — 2025-2026 guidance uniformly centers tail sampling for cost/coverage balance — but it requires buffering complete traces in collector memory, sizing for that, and tolerating decision delay.
3. **Latency-policy pitfalls.** The tail-sampling latency policy is known to misbehave with late spans (collector-contrib discussion #9949): if spans arrive after the wait threshold, a slow trace can be misclassified or its late segments lost. Use generous wait times, order policies from most to least selective, and monitor the processor's dropped-late-span metrics.
4. **Hybrid head+tail.** To cap tail-sampling volume at very high traffic, pre-filter at the head (sample 100 percent of flagged tenants or endpoints, probabilistic elsewhere) and let tail sampling refine within each stream. This keeps tail collector fleets affordable while preserving error and latency coverage for what matters.
5. **Consistency across services.** Mixed head-sampling decisions across services produce broken partial traces — child dropped while parent kept. Use parent-based sampling (OTel default) everywhere so a sampled root forces downstream capture, and never enable independent probability sampling per service on the same path.

## Operations and Cost

1. **Overhead budget.** Span creation is cheap but not free: set explicit per-request span limits, disable debug-level instrumentation in production defaults, and load-test with tracing on — tail latency inflation from serialization and export is the failure you are hunting becoming worse.
2. **Storage economics.** Trace storage dominates cost; combine tail sampling with retention tiers (hot 3-7 days, archived longer) and compression. Estimate bytes per trace from span count and attribute size before choosing retention, not after the first surprising bill.
3. **Collector as critical infrastructure.** A saturated gateway drops traces silently and can back-pressure applications; run collectors with their own metrics dashboards (accept/queue/drop rates, memory), autoscale the gateway tier, and treat collector outages as page-worthy — though applications should keep-queueing (SDK internal buffers) rather than block on export.
4. **Security and privacy.** Spans capture payloads and headers if you let them: scrub or never record authorization headers, tokens, and PII via collector redaction processors; traces flow through more systems than your application does.
5. **SLO-driven usage.** Derive service-level objectives from trace-derived RED metrics (rate, errors, duration) rather than treating tracing purely as debugging — the same pipeline then powers alerts on p99 latency by route and error-rate burn, making the cost self-justifying.

## Related Patterns

1. **Observability architecture.** Tracing is one pillar alongside metrics and logs; the correlation design (exemplars, trace ids in logs) belongs in the overall observability plan.
2. **Service mesh.** Mesh sidecars/ambient layers can generate spans at L7 without app changes — useful baseline coverage, but combine with in-process spans or you only see hop boundaries, not causes.
3. **Circuit breakers and retries.** Traces that expose retry spans and breaker state transitions turn "mysterious 3x latency" into a legible cascade diagram.
