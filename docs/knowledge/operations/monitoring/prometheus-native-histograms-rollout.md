# Prometheus Native Histograms Rollout

Native histograms replace the fixed, pre-declared bucket sets of classic histograms with an exponential bucket scheme stored inside a single time series. A latency metric that previously exploded into dozens of `_bucket` series with explicit `le` labels collapses into one series carrying count, sum, and a bucket layout that adapts to observed values. The rollout story is about cost and correctness at the same time: scrape payloads shrink or grow depending on bucket settings, query syntax changes, and the feature still ships behind a feature flag.

## Scope

Covers enabling and operating native histograms in a Prometheus-compatible stack: the feature flag, instrumentation choices (client library support versus OTLP ingestion), scrape payload and storage cost implications, the query surface (`histogram_quantile`, `histogram_count`, `histogram_sum`, `histogram_fraction`, `histogram_avg`, `histogram_stddev`, and `rate` on histograms), and migration coexistence with classic buckets. Assumes self-managed Prometheus or a Prometheus-compatible store that documents native histogram support. Does not cover summaries, recording rule refactoring beyond histogram expressions, or Thanos-specific compaction behavior.

## Workflow or implementation guidance

Phase the rollout so each step is independently reversible.

1. Enable the feature flag on a staging Prometheus. Native histograms are gated behind the `native-histograms-in-scrape-protocol` style flags (the exact flag set has evolved across releases; consult the feature flags page for the running version) and require the scrape protocol negotiation to offer the protobuf-based exposition format, since native histograms are not representable in the text format.
2. Pick the ingestion path. Two exist: client libraries that expose native histograms natively over the scrape protobuf format, and OTLP ingestion where the Prometheus translation layer maps OTLP exponential histograms into native histograms. The OTLP path lets SDK-first deployments keep their pipeline; the scrape path keeps Prometheus-centric instrumentation. Choose one primary path per metric family to avoid duplicate series.
3. Configure the resolution and bucket budget on the producer. Native histograms use a resolution expressed as a power-of-two bucket count per factor (the schema), plus an optional maximum bucket limit and custom bucket factor beyond base 2. Higher resolution means more buckets per series, which increases scrape payload size and storage even though series count collapses versus classic buckets. Start with the default resolution and a modest bucket ceiling, then adjust based on measured payload deltas.
4. Measure scrape cost before and after. Because classic buckets scale with series (many `_bucket` series per metric), and native histograms scale with occupied buckets inside one series, the crossover depends on bucket occupancy: sparse traffic with wide value ranges can make a native histogram with a high bucket ceiling larger than the classic equivalent. Record scrape duration, response size, and ingestion rates from both sides of a canary split.
5. Migrate queries per panel. Wrap histogram series expressions with the histogram-aware functions; `histogram_quantile` works directly on native histogram series, while classic usage required the le-vector form. Convert recording rules that produce le-based intermediates, and unit-test them with `promtool test rules` fixtures.
6. Retire classic buckets on a schedule. Once dashboards, alerts, and long-term stores all serve the native form, drop the classic instrument from clients. Keep both during the overlap window only where historical comparison requires it, and set an explicit end date so the overlap does not become permanent.

## Controls

- Feature flag declaration pinned and versioned in the Prometheus configuration repository, with a CI check that staging and production flags match before rollout steps proceed.
- Per-producer bucket budget: maximum bucket count and schema declared in instrumentation configuration, with the resulting per-series size reviewed at rollout review.
- Canary split with a scrape-cost dashboard comparing response bytes, scrape duration, and samples-per-second between classic and native paths.
- `promtool test rules` coverage for every converted alert and recording rule, committed as fixtures alongside the rules.
- Rollback plan documented: disable the feature flag or revert the client instrumentation, with the series naming kept distinct so old and new do not merge accidentally.

## Validation evidence

Collect four artifacts. First, a canary scrape-cost report showing response size and scrape duration deltas across the split. Second, `promtool test rules` output passing on converted rules with synthetic native histogram fixtures. Third, a quantile parity plot: the same p50/p95/p99 computed from the classic and native instruments over the overlap window, with divergence quantified (native histograms generally produce tighter error bounds). Fourth, a storage-side confirmation that the metric family's series count dropped by the expected factor (bucket count minus one, roughly, since classic buckets each become a series) while per-series sample size grew proportionally less.

## Failure modes and correction

- Native histograms silently absent: the scrape fell back to the text format, either because protocol negotiation is not enabled or the client did not receive the protobuf offer. Correct by enabling scrape protocol negotiation and verifying the negotiated protocol in the target's scrape metadata.
- Bucket ceiling exceeded on wide-ranging instruments: the producer merges buckets, lowering resolution. Either raise the ceiling (accepting larger payloads) or split the instrument by code path.
- Duplicate series after adding the OTLP path alongside scrape: two ingestion paths for the same logical metric create two series. Correct by relabeling one path out or consolidating on a single path.
- Alerts firing on stale le-based expressions after classic buckets are removed: rules referenced `_bucket` series that no longer exist. The `promtool` fixtures catch this pre-merge; if it slips through, restore classic instrumentation temporarily and fix the rule.
- Long-term store rejects native histogram samples: the remote backend predates native histogram support. Filter native histogram series out of that remote write stream until the backend is upgraded.

## Limitations

Native histograms remain behind feature flags in Prometheus, so availability and flag names are version-dependent and must be rechecked each upgrade. Client library support is uneven across languages; the OTLP translation path is the most portable but adds a translation layer whose bucket mapping can differ from a native client's. Some ecosystem tooling — certain exporters, older Grafana panel types, third-party analyzers — still assumes le-labeled series. Aggregation semantics across native histograms (summing histograms with different schemas) work but reduce to the coarsest schema, so mixed-resolution fleets pay a resolution cost. Finally, scrape payload savings are workload-dependent, not guaranteed.

## Canonical sources

- Prometheus histogram practice guide: https://prometheus.io/docs/practices/histograms/
- Prometheus feature flags (native histograms enablement): https://prometheus.io/docs/prometheus/latest/feature_flags/
- Prometheus query functions (histogram functions): https://prometheus.io/docs/prometheus/latest/querying/functions/
- Mimir native histograms ingestion: https://grafana.com/docs/mimir/latest/configure/configure-native-histograms-ingestion/
