# spanmetrics-connector-red-metrics-from-traces

**Issue:** Dashboards and alerts are metric-driven, but the team already pays for full distributed tracing; duplicating every rate/error/duration metric in application code doubles instrumentation work and drifts from what spans actually show. Conversely, some services expose spans but cannot be modified to add metrics. The OpenTelemetry Collector spanmetrics connector derives RED (rate, error, duration) metrics from trace spans at the pipeline level, giving metrics and SLO alerting for free from the trace stream.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the connector works

1. **It is a connector, not a processor.** The spanmetrics *processor* is deprecated; the connector consumes spans from the traces pipeline and emits metrics into the metrics pipeline, and it replaces the old processor with breaking config changes.
2. **It emits RED metrics by default.** For every service/span-name/status combination it produces a calls counter and a duration histogram (default explicit bucket boundaries span roughly 100 microseconds to 100 seconds); an optional size histogram covers messaging payloads.
3. **Default dimensions come from stable span fields.** Service name, span name, and status code are always present, so a usable per-service RED dashboard needs zero configuration; anything beyond that must be declared explicitly.
4. **Span attributes become dimensions on request.** The `dimensions` config maps span attributes (for example `http.route`, `messaging.destination`) into metric labels, with a `dimensions_cache_size` bounding how many distinct values are cached during aggregation.
5. **Resource attributes can be curated.** `resource_metrics_key_attributes` limits which resource attributes land on the derived metrics, which matters because every resource attribute multiplied by every dimension multiplies the emitted series count.

## Pipeline wiring

1. **Reference it in two pipelines.** A connector must appear as an exporter in the traces pipeline and as a receiver in the metrics pipeline; declaring it only once is the most common first-attempt error and silently produces no metrics.
2. **Place it before tail sampling for unbiased rates.** If spanmetrics sits downstream of the `tail_sampling` processor, it only sees kept spans, and since tail sampling keeps 100% of errors and slow traces, the derived error rates and duration histograms become badly biased toward the bad cases.
3. **Budget collector memory for the aggregation state.** The connector holds aggregation windows keyed by dimension combinations; high-volume traffic with several dimensions can grow memory meaningfully, so pair it with the memory_limiter processor and watch `otelcol_process_memory_rss` on the collector.
4. **Namespace and naming are configurable.** Default metric names follow the `traces_span_metrics_calls` / `traces_span_metrics_duration` pattern (namespace configurable), so pre-wire dashboards and alert rules against the connector's naming convention instead of renaming later.
5. **Combine with the service graph connector deliberately.** Service-graph metrics (who calls whom) come from the separate servicegraph connector; deploying both from the same traces pipeline is common, but they have independent cardinality and memory profiles that must each be sized.

## Cardinality and cost control

1. **Dimensions are the series multiplier.** Adding `http.route` to duration metrics creates route x method x status x service series; enumerate the expected combinations before enabling a dimension, not after the bill arrives.
2. **Use route templates, never raw paths.** If the span attribute carries raw URLs or unbounded request identifiers, the connector manufactures unbounded series; fix the instrumentation to emit `http.route` templates or drop the dimension entirely.
3. **Cap aggregation cardinality where the distribution supports it.** Collector distributions expose an aggregation cardinality limit for spanmetrics (for example `aggregationCardinalityLimit` in the Coralogix distribution), which stops runaway dimension values from exploding the collector and the backend.
4. **Prefer few dimensions plus exemplars.** Keep derived metrics at dashboard-level dimensions and let exemplars carry the per-request deep links back into traces, which is the same high-cardinality strategy documented in `opentelemetry-exemplars-metric-to-trace-links.md`.
5. **Monitor the connector's own telemetry.** Track emitted series counts and any overflow/dropped-datapoint counters from the collector's internal metrics so dimension explosions are caught at the collector instead of discovered in backend billing.

## Accuracy gotchas

1. **Head sampling upstream shrinks absolute rates.** If the SDK probabilistically samples 10% of traces before export, derived call rates are 10% of truth; either compensate in queries/alert thresholds or keep spanmetrics fed by an unsampled (or fully-exported) stream.
2. **Span name instability creates phantom series.** Client libraries that put parameters or IDs into span names (for example `GET /users/12345`) produce one series per request; enforce stable span names via instrumentation config before enabling the connector.
3. **Consumer and producer spans can double-count.** Both sides of a queue interaction can emit matching spans, so a "calls" metric derived from all spans may report two per message; filter by span kind or scope the connector configuration per pipeline if needed.
4. **Histogram percentiles depend on bucket layout.** The default boundaries are tuned for general web latency; very fast (sub-millisecond) or very slow (multi-minute batch) services need custom `explicit_bucket_boundaries` or p99s will be bucket-truncated garbage.
5. **Reconcile against SDK-side metrics for drift.** When a service also emits native RED metrics, compare the two for a few weeks; persistent divergence usually exposes sampling loss, span-name churn, or status-code mapping differences that would otherwise silently skew SLO math.
