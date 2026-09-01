# Tempo Trace ID Linkage and Service Graph

Tempo stores traces keyed by trace ID; everything users actually want from a tracing backend — jump from a slow dashboard panel to the offending span, from a log line to its trace, or a map of who calls whom — depends on that identifier being created once and carried intact through every hop. When propagation breaks, Tempo cannot synthesize it back: you get orphans, partial traces, and service graphs with missing edges. This article covers verifying W3C trace context propagation and building trustworthy service graph metrics from the Tempo metrics-generator.

## Scope

Covers two linked topics: the correctness of distributed trace context propagation (W3C Trace Context `traceparent`/`tracestate` headers, plus baggage as a sibling mechanism) as the precondition for trace ID linkage, and the configuration and interpretation of Tempo's service graphs produced by the metrics-generator, including the red-metrics adjacency. Assumes instrumentation via OpenTelemetry SDKs or auto-instrumentation. Excludes tail sampling policy, span-to-metrics connectors in the Collector, and Tempo storage sizing.

## Workflow or implementation guidance

Work propagation first; graphs second. A service graph generated from broken propagation is worse than no graph, because its missing edges read as absent dependencies.

Step 1: standardize on W3C Trace Context. Every SDK's propagator should be the W3C `tracecontext` propagator (with `baggage` where cross-cutting context is needed); legacy vendor headers or B3 in some hop create translation points where trace IDs mutate or vanish. Configure the propagator explicitly rather than relying on defaults, which vary by SDK language and version.

Step 2: verify the propagation chain hop by hop. The check is mechanical: inject a known trace at the edge, and assert each intermediate service emits spans bearing the same trace ID. A single trace that touches every service in a dependency chain — a synthetic "canary trace" — reveals every break. Gaps cluster at uninstrumented hops: message queues without header passthrough, service mesh sidecars stripping unknown headers, SDK-to-SDK boundaries across language gaps, and any component that starts a fresh trace because it never read the incoming context.

Step 3: link the other signals by policy. Logs and exemplars carry the trace ID so that a metric outlier or a log line can pivot into Tempo. This is the same identifier: exemplars reference trace IDs recorded with metric samples, and log correlation (via OTLP log pipelines putting trace IDs into structured fields) completes the triangle. Declare in the observability standards document which fields carry the ID in each signal, so pivots are uniform.

Step 4: enable service graphs in Tempo's metrics-generator. The metrics-generator consumes spans and derives edges: request calls from client spans, responses from server spans, aggregated per service pair. Enable it with explicit dimensions (low-cardinality ones only — service name, service graph hash; never span-level attributes with unbounded values), and point its generated series at your Prometheus-compatible store. The metrics-generator's output is only as complete as its input: client and server spans for the same logical call must share the trace and span linkage for an edge to form.

Step 5: validate edges against reality. Compare generated edges with the deployment's declared dependencies. A missing edge usually means one side of the call lacks spans (only client or only server), which is the signature of partial instrumentation rather than a Tempo bug. Extra edges from internal calls can be filtered with dimensions or span filtering.

Step 6: alert on graph health. Track the count of distinct edges over time; a sudden drop signals a propagation regression, often deployed in the last release, and is far easier to notice on the graph metric than in individual traces.

## Controls

- Propagator configuration pinned (W3C tracecontext, plus baggage only where used) in every SDK baseline, checked by a config audit job.
- Canary-trace test in CI or a scheduled synthetic runner: one trace traversing every critical path, asserting trace ID continuity and span counts per service.
- Metrics-generator dimensions allow-list reviewed for cardinality before each addition; no unbounded attributes.
- Service graph edge-count dashboard with alerting on step changes.
- Linkage policy documented: which field carries trace ID in logs, exemplars, and spans, enforced by pipeline linting where possible.
- Release gate: new service onboarding checklist includes propagation verification and appears in the service graph within one evaluation window.

## Validation evidence

File three artifacts. The canary trace itself: a Tempo deep-link showing an unbroken trace across all hops with the expected span count and service list — this is the primary propagation proof. The edge-coverage report: generated service graph edges versus the architecture's declared dependencies, listing each missing edge with its cause (uninstrumented side). A red-metrics cross-check: for one service pair, the service graph's request rate and error ratio versus the client-side metrics the services already emit, confirming the derived series aligns with direct measurement.

## Failure modes and correction

- Orphan or single-span traces at one service: that hop never read the incoming `traceparent`. Fix the receiver to extract context before creating spans; verify header passthrough in proxies and queues.
- Trace IDs present but parent-child linkage wrong: a component rewrote rather than continued the context, or sampling flags reset mid-chain. Align propagators and re-run the canary trace.
- Missing service graph edges: one side of the call lacks spans. Instrument the missing side; client-only or server-only spans cannot form an edge.
- Graph explodes in cardinality: an unbounded dimension was added to metrics-generator configuration. Remove it and re-deploy; series count in the target store confirms recovery.
- Graph metrics lag reality: the metrics-generator's processing window is behind. Distinguish this from propagation failure by checking generator ingestion lag before debugging SDKs.
- Baggage absent where expected: the baggage propagator was not configured alongside tracecontext even though baggage headers were sent.

## Limitations

Tempo's service graph is derived from spans it receives after sampling; aggressive head sampling thins edges statistically and can drop rare edges entirely, so graph completeness is bounded by sampling policy. Metrics-generator capabilities and configuration keys evolve between Tempo versions; the deployed version's configuration reference governs. Propagation verification proves linkage only for the exercised paths — untested integrations remain unverified. Cross-vendor header translation (for example, legacy B3 at a boundary) works but adds conversion logic that must be maintained. Finally, service graphs show request relationships, not every interaction type; for example, message-driven relationships depend on messaging semantic conventions being applied by instrumentation.

## Canonical sources

- W3C Trace Context recommendation: https://www.w3.org/TR/trace-context/
- Tempo service graphs (metrics-generator): https://grafana.com/docs/tempo/latest/metrics-generator/service_graphs/
- Tempo span metrics: https://grafana.com/docs/tempo/latest/metrics-generator/span_metrics/
