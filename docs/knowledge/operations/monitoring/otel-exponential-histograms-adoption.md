# OpenTelemetry Exponential Histograms Adoption

Explicit-bucket histograms force an up-front guess about latency ranges: pick boundaries wrong and every observation lands in the overflow bucket, or resolution vanishes where it matters. The OpenTelemetry exponential histogram (also called the base-2 or-higher-resolution histogram) removes that guess by computing bucket boundaries from the data itself using an integer scale factor. Adoption is attractive but not free — scale selection, bucket merging, and uneven backend support all shape whether the migration delivers accurate quantiles or new classes of query errors.

## Scope

Covers the decision and mechanics of moving latency and size instruments from explicit-bucket to exponential histograms in OTLP pipelines: how scale factors control resolution, how producers and consumers merge buckets with different scales, and which parts of the Prometheus and Grafana ecosystems can store and query these streams today. Intended for engineers operating SDKs and Collectors feeding Prometheus-family backends. Not covered: classic Prometheus native histograms as a scrape-side feature (treated in a companion article), span metrics generation, and cost modeling.

## Workflow or implementation guidance

Treat adoption as three gates: producer capability, backend capability, and query compatibility.

First gate — producer. Verify the SDK version supports the exponential histogram aggregation and enable it per instrument, ideally only for new instruments initially. Configure the maximum scale (zero is common for latency; positive scales double resolution per step, negative scales halve it) and the max bucket count. The instrument's own measurement range drives the choice: sub-millisecond to multi-second latencies are well served at scale zero because the relative error stays bounded, while tightly clustered measurements benefit from a positive scale. Keep the explicit-bucket instrument running in parallel during evaluation so dashboards can be compared side by side.

Second gate — backend. Confirm the storage backend accepts the exponential histogram OTLP point kind and converts it into its own representation. Prometheus's OTLP ingestion translates exponential histograms into native histograms, which require the native histogram feature flag enabled and a sufficiently recent release; Mimir has its own ingestion switch. Where the backend does not accept the point kind, exports fail with partial success, so gate the rollout behind a staging pipeline that mirrors production versions.

Third gate — queries. Rewrite quantile expressions. Explicit-bucket workflows use `histogram_quantile()` over le-bucket series; native histograms use the histogram family of functions directly on the single series. Confirm recording rules, alerts, and dashboard panels all reference the new form before deleting the old instrument, and keep both for one full retention window if long-range comparison matters.

Ongoing operation: watch the per-stream bucket count. An instrument whose measurement range drifts wider than the configured maximum forces bucket merging at reduced resolution; this is automatic but should be monitored so you know when resolution degrades. Also watch for zero-count and negative-value handling differences across SDK languages, since a single instrument emitting empty buckets can bloat payloads.

## Controls

- SDK configuration pinning explicit `aggregation` (exponential histogram) with declared max scale and max size, per instrument rather than globally.
- Backend feature flag check (native histogram ingestion enabled) verified in staging with a payload capture before any production switch.
- Parallel-run period with both explicit-bucket and exponential instruments, and a dashboard overlaying the two quantile estimates to expose divergence.
- Alert rule unit tests using `promtool test rules` fixtures with synthetic histogram samples, so quantile expressions are executable specifications rather than prose.
- Payload size budget check in the Collector batch processor, with an alert if average export size grows past the declared ceiling after adoption.

## Validation evidence

Prove adoption worked with three artifacts: an OTLP payload capture showing `ExponentialHistogram` data points with the chosen scale factor; a backend query returning the expected quantile for a synthetic workload with known distribution (for instance, a deterministic load generator producing a two-millisecond median, and the query returning within the instrumented error bound); and a before/after quantile plot over the parallel-run window demonstrating that error at p99 shrank or stayed flat while bucket configuration shrank from dozens of fixed buckets to the adaptive set. A `promtool test rules` pass over converted alert rules closes the loop.

## Failure modes and correction

- Backend rejects exponential histograms (partial success or full 400): rollout predates the feature flag. Correct by enabling native histogram ingestion or pinning the backend version, then re-exporting from a canary.
- Quantile cliffs: quantile estimates jump between adjacent buckets when resolution is too coarse. Correct by raising the scale by one, which doubles bucket density, at the cost of more buckets per stream.
- Bucket count ceiling hit on wide-ranging instruments: the producer downshifts scale automatically, degrading resolution silently. Correct by splitting the instrument (separate fast and slow paths) or accepting and documenting the reduced resolution.
- Cross-scale merging errors when one stream arrives at scale 2 and a query backend must merge with scale 0: verify the consumer supports scale reduction, which is a defined operation, and report mismatches if the backend errors instead of merging.
- Divergent p99s between old and new instruments during parallel run: confirm the explicit bucket set actually bracketed the interesting range before declaring the new instrument wrong; often the old instrument was the inaccurate one.

## Limitations

Exponential histograms only admit positive values; measurements at or below zero need a different instrument or shifting. Scale changes over a stream's life mean quantile accuracy is not constant, only bounded. Support across third-party dashboards, managed offerings, and long-term stores is uneven and changes release to release, so compatibility claims must be re-verified per upgrade. Finally, exemplar support on exponential histograms has lagged explicit buckets in several SDKs, which can matter if exemplar-driven drill-down is part of the workflow.

## Canonical sources

- OpenTelemetry metrics data model, ExponentialHistogram point kind: https://opentelemetry.io/docs/specs/otel/metrics/data-model/
- Prometheus histograms and summaries practice guide (native histogram guidance): https://prometheus.io/docs/practices/histograms/
- Mimir native histograms ingestion configuration: https://grafana.com/docs/mimir/latest/configure/configure-native-histograms-ingestion/
