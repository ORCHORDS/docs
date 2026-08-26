# opentelemetry-exemplars-metric-to-trace-links

**Issue:** A latency histogram bucket or error-rate counter spikes on a dashboard, and the on-call engineer then spends 15-30 minutes manually correlating timestamps, service names, and log lines to find one representative request trace. The metric signal and the trace signal live in different systems with no link between them. OpenTelemetry exemplars solve this by attaching representative trace IDs to individual metric data points, so a click on the spiking histogram bucket jumps straight to a real trace that produced it.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Enabling exemplars end to end

1. **Enable trace-metric correlation in the SDK.** OpenTelemetry SDKs attach the current span context (trace ID and span ID) as exemplar attributes on counter and histogram recordings when tracing and metrics share the same context propagation; some languages gate this behind an experimental flag (for example `EXPERIMENTAL_OTEL_DOTNET_EXEMPLARS` in .NET), so verify per-language support before relying on it.
2. **Turn on exemplar storage in Prometheus.** Prometheus ignores exemplars unless started with `--enable-feature=exemplar-storage`, and exemplars are only ingested for counters and histograms exposed in OpenMetrics format. Storage is bounded and configurable via `--storage.exemplars.max-exemplars`, and it is in-memory, so exemplars are lost on restart.
3. **Prefer the OTLP path when possible.** Prometheus classic remote-write does not carry exemplars; OTLP ingestion into backends like Mimir, Tempo, or vendor platforms does. If you export with the OpenTelemetry Collector, keep the OTLP exporter so exemplars survive the hop instead of being stripped at a Prometheus-remote-write conversion.
4. **Configure the Grafana data source.** Exemplars are off by default: enable "Exemplars" on the Prometheus/Mimir data source, map the `trace_id` and `span_id` exemplar labels, and enable internal links to the tracing data source (Tempo, Jaeger, or Zipkin) so exemplar dots deep-link into the trace view.
5. **Verify the pipeline before trusting it.** Chart a request histogram in Explore with "View exemplars" enabled and confirm exemplar dots appear on recent data points and resolve to real traces. An empty exemplar view usually means a broken SDK flag, a scrape-time format issue, or a backend that silently dropped them.

## Where exemplars work and where they do not

1. **Histograms and counters only.** Prometheus and most backends attach exemplars to counter increments and histogram observations (latency, request size), which is exactly where "show me a slow request" questions arise. Gauges and summaries have no exemplar semantics.
2. **High-cardinality context belongs in exemplars, not labels.** Trace IDs, user IDs, and request IDs should never be metric labels; exemplars carry that per-request context without multiplying time series, which is the intended pattern in `prometheus-cardinality-management.md`.
3. **Exemplars are sampled, not exhaustive.** SDKs use exemplar filters (trace-ID-hash based or always-on) so only a subset of recordings carry exemplars; the dots you see are representative samples, not every request behind the bucket.
4. **Metrics not produced inside a span have no trace to link.** Exemplars only carry a trace ID when the measurement happens within an active sampled span; background gauges, cron-collected metrics, and runtime metrics will show no exemplars by design.
5. **Sampled-out traces make dead links.** If tail sampling drops the very trace an exemplar references, the deep link opens a missing trace. Keep the exemplar-producing services' error and slow traces at 100% retention (see `tail-sampling-strategies.md`) so the interesting exemplars resolve.

## Using exemplars during an incident

1. **Jump from the spiking bucket, not from averages.** Open the p99 latency or error-count panel in Explore, enable exemplar display, and click a dot inside the offending time range; this replaces guess-and-check log greps with a one-click pivot to a causal trace.
2. **Filter exemplars by label as a triage shortcut.** Because exemplars inherit the series labels, narrowing the query to a specific route or region first means every exemplar dot you click is already from the affected population.
3. **Share the trace link, not a screenshot.** Paste the exemplar deep link into the incident channel so everyone debugs the same representative trace instead of each person finding a different one.
4. **Use exemplars to validate hypotheses fast.** When checking whether latency moved to a downstream dependency, the exemplar trace shows the exact span timings immediately, which confirms or kills the hypothesis before anyone opens a second dashboard.
5. **Treat missing exemplars as a diagnostic signal.** If exemplars vanish at the exact moment an incident starts, suspect an SDK/context breakage or a scrape-format change rather than assuming the code path stopped producing spans.

## Gotchas and failure modes

1. **Exemplar storage is a bounded, in-memory LRU.** Under heavy churn the oldest exemplars are evicted quickly; on a busy target you may only have minutes of exemplar history, so investigate while the window is live rather than hours later.
2. **Scrape cadence gates exemplar freshness.** Scrape-based exemplars are only those present at scrape time, so short-lived spikes between scrapes may leave no exemplar behind; raising scrape frequency on key targets improves exemplar coverage at the cost of load.
3. **Propagator and context mismatches break the link silently.** If traces and metrics are initialized with different context providers or the propagator loses context at an async boundary, metrics record without span context and no error is raised anywhere.
4. **Backend support varies by ingestion path.** Some vendor ingestion paths and older self-hosted versions accept the metrics but strip exemplars; test the exact exporter-to-backend combination you run in production rather than a local-only proof of concept.
5. **Exemplar volume is not alertable signal.** The density of exemplar dots reflects reservoir sampling, not request volume; never infer rates from exemplar counts, only use them as navigation into traces.
