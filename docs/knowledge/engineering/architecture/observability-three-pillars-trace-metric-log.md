# Observability Three Pillars Trace Metric Log

## Scope

This article addresses the three pillars of observability—traces, metrics, and logs—as the standard taxonomy for understanding system behaviour. It explains what each pillar provides, where it excels, where it falls short, and how the three are combined into a single operational picture. The discussion covers distributed tracing, RED/USE metrics, structured logging, correlation identifiers, sampling strategies, and the role of OpenTelemetry in unifying the three pillars. The article applies to any system that must be operated at scale, including microservices on Kubernetes, edge runtimes such as Cloudflare Workers, and monolithic applications with sufficient internal complexity to need structured observation.

## Workflow or implementation guidance

Observability is the ability to ask arbitrary questions about a system's behaviour without having to predict those questions in advance. The three pillars are the standard taxonomy for the data that makes this possible: traces (the path of a single request through the system), metrics (aggregated numerical measurements over time), and logs (discrete events with structured or unstructured detail).

The first pillar, metrics, is the oldest and the most familiar. Metrics are numerical measurements collected at regular intervals and aggregated into time series. They answer questions like "what is the request rate?", "what is the error rate?", "what is the p99 latency?". The standard set of metrics for a request-driven service is the RED metrics: Rate (requests per second), Errors (failed requests per second), Duration (request latency distribution). The standard set for an infrastructure resource is the USE metrics: Utilisation (percentage of time the resource is busy), Saturation (queue depth or backlog), Errors (error events).

The second pillar, logs, are the most flexible. A log entry is a timestamped record of an event: a request arrived, a user authenticated, a database query failed. Logs can be structured (JSON, key-value) or unstructured (free text). Structured logs are searchable and aggregatable; unstructured logs are not. The trend is strongly toward structured logging, because the cost of producing structured logs is negligible and the operational benefit is large.

The third pillar, traces, are the most recent. A trace is the path of a single request through a distributed system, with each hop represented as a span. Traces are sampled (typically 1–10 percent of requests), propagated through the system via trace context headers (W3C Trace Context, B3), and aggregated into a trace store (Jaeger, Zipkin, Honeycomb, Tempo). Traces answer questions like "why was this specific request slow?" and "which downstream service caused the latency?".

The three pillars are not independent. A trace contains logs; a metric is derived from logs; a slow span in a trace is a starting point for a metric investigation. The operational discipline is to use metrics to detect ("p99 latency is up"), logs to diagnose ("which requests are slow"), and traces to understand ("which downstream is causing the slow requests"). OpenTelemetry is the modern standard that unifies the three: it provides a single SDK that emits traces, metrics, and logs with consistent context, propagated through the system via a single set of headers.

The first step in implementation is to choose the backends: a metrics store (Prometheus, Datadog, CloudWatch), a log store (Loki, Elasticsearch, CloudWatch Logs), and a trace store (Jaeger, Tempo, Honeycomb). The second step is to instrument the application with OpenTelemetry. The third step is to define the metric, log, and trace conventions: what counts as a request, what counts as an error, what fields are in every log entry, what attributes are in every span.

## Controls

Observability controls cover data quality, retention, cost, and access. Data quality: metrics must be consistent across services (the same definition of "error rate"); logs must be structured; traces must be sampled and propagated correctly. Retention: metrics are typically retained at high resolution for days and at low resolution for months; logs are retained for weeks; traces are retained for days or weeks depending on the sampling rate. Cost: traces are expensive at high sampling; metrics and logs are cheap but can grow quickly if the cardinality is uncontrolled. Access: observability data is sensitive; access controls must prevent leakage of PII from logs and traces.

The observability stack itself must be reliable. Loss of the metrics store means loss of alerting; loss of the log store means loss of forensic capability; loss of the trace store means loss of root-causing. The stack must be designed for high availability, and the application must degrade gracefully when the stack is unavailable.

## Validation evidence

Validation of observability is structural and behavioural. Structural validation: every service emits the agreed metric set, the agreed log fields, and propagates the agreed trace context. The build pipeline can enforce this with lint rules. Behavioural validation: a synthetic test generates a request that takes a known time and traverses a known path; the trace must show the expected spans, the metrics must show the expected counts, and the logs must contain the expected entries.

Validation must also prove that the three pillars agree. A trace that shows a request took 500 ms must correspond to a log entry that records the request with a 500 ms duration, and a metric that shows the request was counted in the latency histogram. Disagreement between pillars is a sign of instrumentation drift and must be investigated.

## Failure modes and correction

The dominant failure is missing context. A log entry says "request failed" without a request ID, a user ID, or a trace ID. The engineer cannot correlate the log with a trace or with the metric. The cure is to enforce structured logging with mandatory fields (correlation ID, trace ID, span ID, user ID). A second failure is high-cardinality metrics. A metric that includes the user ID as a label creates one time series per user, and the metric store collapses under the cardinality. The cure is to bound cardinality: only low-cardinality fields are used as labels.

A third failure is insufficient sampling. A trace store that samples 100 percent of requests is too expensive; a trace store that samples 0.1 percent of requests cannot root-cause the long tail. The cure is adaptive sampling: sample more from errors, sample less from successful fast requests. A fourth failure is the observability stack being treated as separate from the application. The application emits logs that no one queries, metrics that no one dashboards, and traces that no one inspects. The cure is to align the observability data with the questions the team actually asks.

A fifth failure is the observability stack itself being a source of latency. Logging synchronously on the request path slows the request; tracing with a high-overhead SDK slows the request. The cure is to make observability asynchronous and to use lightweight SDKs (OpenTelemetry's default batching, sampled logging).

## Limitations

The three-pillar model is powerful but not complete. Events (state changes, business events) are sometimes a fourth pillar in their own right. Real User Monitoring (RUM) and synthetic monitoring are sometimes called the fourth or fifth pillars. The taxonomy is a useful starting point, but observability is broader than any taxonomy can capture. The three-pillar model also assumes that the data is being collected at all; an unobservable system is still unobservable no matter how good the model is.

Observability does not replace good operational discipline. A team that has great observability but does not act on what it sees is no better than a team that has no observability. The data must drive action: alerts must be actionable, dashboards must be reviewed, traces must be inspected during incidents.

## Canonical sources

- Google — *Site Reliability Engineering* book, the chapter on monitoring distributed systems, defining the white-box/black-box monitoring distinction: https://sre.google/sre-book/monitoring-distributed-systems/
- Google — *Site Reliability Workbook*, the chapter on practical alerting and the definition of SLO-based alerting: https://sre.google/workbook/monitoring/
- OpenTelemetry documentation, the unified specification and SDKs for traces, metrics, and logs: https://opentelemetry.io/docs/
- Cindy Sridharan — *Distributed Systems Observability* (O'Reilly), the influential book on the three pillars and the role of each in modern operations
