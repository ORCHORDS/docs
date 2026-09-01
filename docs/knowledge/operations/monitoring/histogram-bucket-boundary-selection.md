# Histogram Bucket Boundary Selection

When a latency SLO promises p99 under 300 milliseconds, the histogram backing that promise must actually resolve values around 300 milliseconds. Bucket boundaries decide that: a quantile is estimated inside the bucket containing it, so if the SLO threshold falls between two boundaries, the estimate is only as good as the bucket's width there. Boundary selection is therefore not a style choice but the difference between an SLO measurement with known error and one that is effectively unmeasured.

## Scope

Covers selecting explicit histogram bucket boundaries for service-level metrics: the relationship between boundaries, quantile error, and SLO thresholds; power-of-two and extended exponential layouts; bucket count budgets and their cost in series and scrape payload; heatmap readability considerations; and the point at which native (exponential) histograms make the whole question moot. Applies to Prometheus-style histograms and OpenTelemetry explicit-bucket histograms alike. Excludes summary-type metrics and aggregation across instances beyond a note.

## Workflow or implementation guidance

Choose boundaries from the questions the histogram must answer, in this order.

Identify the decision thresholds first. Every quantile the organization acts on — the p99 in the SLO, the p95 gating deploys, the p50 on health dashboards — is a value the histogram must resolve. Collect these numbers before touching any layout, because boundaries exist to bracket them. A boundary at 250 and another at 300 bound the 300-millisecond threshold tightly; boundaries at 100 and 500 do not, and any quantile landing between them is an interpolation with up to that bucket's worth of uncertainty.

Understand the error mechanics. Histogram quantile estimation interpolates within the bucket where the target quantile falls; the error is bounded by the bucket width. So the rule is: buckets must be narrow near the thresholds you care about, and can be wide where nobody looks. Uniformly narrow buckets across the entire range waste the budget on regions (sub-millisecond, or multi-second tails) where precision has no consumer.

Apply a power-of-two base with targeted refinement. The standard layout is boundaries at powers of two (or powers of ten if the domain is decimal), which gives constant relative resolution: each bucket spans a factor of two, so relative error stays bounded across the range. Then refine around decision points: split the two-millisecond-to-four-millisecond style gap into finer steps near each SLO threshold. Prometheus client libraries' default latency boundaries follow exactly this shape — coarse powers of ten, refined around common web latencies — and are a reasonable starting point that should then be adjusted to your own thresholds.

Budget the bucket count. Each explicit bucket is a time series per instrument instance: twenty buckets on a metric labeled by ten pods is two hundred series for that instrument alone. Growth in buckets multiplies cardinality directly, inflating scrape payload, storage, and query cost. A practical budget is roughly ten to twenty boundaries for service latency metrics; if your list exceeds that, you are probably resolving regions nobody queries. For instrument families exported fleet-wide, lean toward fewer buckets and compensate by making the ones you keep count.

Check heatmap readability. When the metric is consumed as a Grafana heatmap rather than as scalar quantiles, very wide buckets produce blocky, unreadable visualizations, and very fine buckets make the heatmap expensive to render. Boundaries that look fine in `histogram_quantile` output can render poorly; review the panel after changing a layout, and prefer a roughly log-linear spacing, which both quantile math and human perception handle well.

Plan for aggregation. Quantiles are not averaged across instances; you aggregate by summing bucket counts and computing the quantile of the sum. This preserves correctness but means each instance's buckets must align — mixed boundary sets across versions of a service make the fleet-level histogram lumpy. Pin the layout per metric name and version it in the instrumentation library, and treat a boundary change like a schema change: the quantile series has a discontinuity at the change point.

Finally, evaluate whether to keep choosing at all: native (exponential) histograms replace fixed boundaries with an adaptive scheme, eliminating the threshold-alignment question for new metrics. Explicit buckets remain necessary where the backend or dashboarding does not support native histograms, so both skills coexist.

## Controls

- Boundary layouts declared in the instrumentation library with a comment mapping each refined boundary to the decision threshold it serves.
- SLO change procedure that re-reviews bucket layouts: a new p99 target outside the refined region triggers a layout update before the SLO goes live.
- Bucket-count budget per instrument (declared maximum), checked in instrumentation review.
- Fleet consistency check: one layout per metric name and version, verified by comparing boundary sets across instances during rollout.
- Quantile error audit: for each SLO threshold, the enclosing bucket's width recorded, and the resulting worst-case quantile error stated in the SLO document.
- Panel review after layout changes for heatmap readability.

## Validation evidence

Prove the layout serves its thresholds with a fixture test: emit synthetic observations with a known distribution — for instance, a deterministic set whose true p99 is 305 milliseconds — and assert the histogram-based `histogram_quantile` result falls within the error bound implied by the enclosing bucket. The error audit table (threshold, enclosing bucket boundaries, worst-case error) is the human-readable artifact. For cost, the series-count delta before and after a layout change, taken from the metrics backend, evidences the cardinality budget. Aggregation correctness is shown by a fleet-level quantile over summed buckets matching the quantile computed from the unified raw observations.

## Failure modes and correction

- p99 series flatlines at a boundary value: the quantile falls in a wide bucket and interpolation returns the same number regardless of drift. Refine boundaries around the threshold; the flatline is the symptom of resolution starvation.
- Quantile jumps between adjacent values: same cause — coarse buckets make small traffic shifts move the estimate a full bucket width. Same fix.
- Cardinarity explodes after adding boundaries: the budget was exceeded by the label fan-out multiplication. Remove boundaries resolving unconsumed regions or reduce label cardinality.
- Inconsistent fleet quantiles after a rollout: instances running mixed boundary sets. Complete the rollout or pin the layout by version so queries split correctly.
- Heatmap unreadable after layout change: wide gaps render as blocks. Re-space toward log-linear and re-review the panel.
- SLO error understated: the SLO document claimed tighter accuracy than the enclosing bucket permits. Update the stated error bound from the audit table so the claim matches the instrument.

## Limitations

Explicit-bucket quantiles are always estimates; the error audit bounds but does not eliminate uncertainty. Boundaries optimal for one consumer (the p99 alert) are suboptimal for another (tail diagnosis at ten seconds), and the budget forces a choice. Cross-version boundary changes create discontinuities in long-range quantile charts that no query can repair. The guidance here assumes unimodal latency distributions; multi-modal ones can place quantiles near bucket edges where interpolation error peaks. Native histograms remove boundary selection but bring their own adoption constraints covered in the companion articles — including backend support and resolution ceilings.

## Canonical sources

- Prometheus histograms and summaries practice guide (bucket choice and quantile error): https://prometheus.io/docs/practices/histograms/
- Prometheus query functions (histogram_quantile interpolation): https://prometheus.io/docs/prometheus/latest/querying/functions/
- OpenTelemetry metrics data model (histogram bucket semantics): https://opentelemetry.io/docs/specs/otel/metrics/data-model/
