# OpenTelemetry Metric Temporality Selection

Every OTLP metric stream carries an aggregation temporality: cumulative points hold a running total since process or stream start, while delta points hold the change since the previous export. Most SDKs default to cumulative for OTLP export, yet several Prometheus-ecosystem and delta-native backends behave differently, and picking the wrong temporality produces doubled counts, broken rate calculations, or silently discarded data after restarts. This article explains how to select temporality per signal, verify what a backend actually accepts, and keep rate math correct across the boundary.

## Scope

Applies to teams exporting metrics via OTLP from OpenTelemetry SDKs or the Collector into any remote backend, especially Prometheus-compatible stores that derive rates from counter deltas. Covers cumulative versus delta semantics, backend compatibility constraints, SDK and Collector configuration points, restart behavior, and conversion between temporalities. Out of scope: trace and log signals, exemplar handling, and provider-specific pricing models.

## Workflow or implementation guidance

Work through temporality as a deliberate, per-pipeline decision rather than accepting the SDK default.

1. Inventory the destination first. Read the backend documentation and confirm whether it ingests cumulative counters, delta counters, or both, and which it expects for histograms and sums. Prometheus-compatible ingestion of OTLP assumes cumulative counter semantics; a delta counter stream converted naively can be interpreted as a gauge and break `rate()` and `increase()` queries.
2. Set temporality at the SDK metric reader where possible. Most language SDKs expose a temporality selector on the periodic exporting metric reader; choosing cumulative there means the stream never changes shape mid-flight. Override only for specific instruments (for example, forcing delta for an instrument whose cumulative value overflows a backend integer range).
3. If you cannot change the source, convert in the Collector. The `deltatocumulative` processor (and the corresponding cumulative-to-delta conversion paths available in some distributions) normalizes streams so the exporter always sees one temporality. Place conversion before the batch processor so points arrive in order, and after resource detection so attributes are final.
4. Account for process restarts. Cumulative streams reset to zero on restart, and every well-behaved backend treats a decreasing counter as a reset. Delta streams lose the unexported tail at crash time, which understates the final interval. Neither is lossless; cumulative makes resets explicit and detectable, which is why rate-based alerting generally prefers it.
5. Confirm alignment for histograms. Bucket counts under cumulative temporality are monotonic totals; under delta they are per-interval additions. Mixing the two in one backend leads to `histogram_quantile` results that drift or clamp. Pick one temporality for all histogram instruments in a pipeline and record it in the pipeline's runbook entry.
6. Document the decision per exporter in configuration comments, including the accepted temporality, so that a future migration to another backend re-evaluates instead of inheriting a stale choice.

## Controls

- Periodic metric reader temporality selector pinned explicitly (no reliance on SDK defaults) in every SDK configuration.
- Collector pipeline lint rule that fails a build when a deltatocumulative-style converter and a cumulative-only exporter appear in the wrong order.
- Acceptance check in staging that greps exported payloads for `aggregation_temporality` values and compares them to a declared expectation per metric stream.
- Restart test in CI that kills an instrumented process mid-interval, restarts it, and asserts the backend's rate query returns to baseline within two scrape intervals.
- Documentation control: each pipeline's temporality choice, rationale, and backend citation recorded alongside the exporter configuration.

## Validation evidence

Evidence that temporality is configured and working includes: OTLP payload captures (for example, from a debug exporter or a tcpdump of the JSON-encoded OTLP/HTTP path) showing the expected `aggregation_temporality` field value on Sum and Histogram data points; backend query results where `rate()` over an ingested counter matches a known synthetic load generator's per-second increment within expected tolerance; and restart drill traces showing a visible reset to zero rather than a negative delta. A diff of pre- and post-migration query output for one golden dashboard panel provides the final human-verifiable artifact.

## Failure modes and correction

- Delta counters ingested into a cumulative-expecting store: `rate()` queries return garbage or zero. Correct by adding the appropriate conversion processor in the Collector or switching the SDK reader to cumulative, then re-verify with a payload capture.
- Cumulative-to-delta conversion with out-of-order or late points: the converter sees a start timestamp that does not match the previous point's end, drops the point, and logs an error. Correct by ensuring a single exporter path per stream and enabling ordered batching; check the processor's dropped-points counter.
- Silence after a temporality change: some backends reject mismatched points with a partial-success response rather than an error the SDK surfaces. Correct by inspecting partial success logs in the Collector exporter helper and re-registering the stream under a new identity if the backend pins temporality per series.
- Unbounded cumulative growth in a backend with 64-bit overflow concerns after months of uptime: prefer delta for that instrument or document a planned process restart cadence.

## Limitations

Temporality is only one axis; instruments, units, and monotonicity flags interact with it and are not covered here. Conversion processors have maturity caveats and may not support every point kind (for example, some do not handle exponential histograms). Backend behavior can differ between self-hosted and managed versions of the same product, so the compatibility table in any vendor document is a point-in-time snapshot. Finally, this article does not cover OpenMetrics scrape-based exposition, which has its own (implicitly cumulative) model.

## Canonical sources

- OpenTelemetry metrics data model, aggregation temporality: https://opentelemetry.io/docs/specs/otel/metrics/data-model/
- OTLP specification, encodings and partial success semantics: https://opentelemetry.io/docs/specs/otlp/
- OpenTelemetry Collector configuration reference: https://opentelemetry.io/docs/collector/configuration/
