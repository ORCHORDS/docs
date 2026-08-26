# histogram-vs-summary-metric-types

**Issue:** Prometheus offers two metric types for latency distributions, and teams routinely pick the wrong one. Summaries compute quantiles client-side (p50, p90, p99 at scrape time) but cannot be aggregated: you cannot average two instances' p99s to get a fleet p99, so a summary is dead weight the moment you scale past one replica. Classic histograms bucket observations into fixed, pre-chosen lebes and are aggregatable, but the bucket boundaries must be picked before you know the distribution, and tail percentiles (p99, p999) computed from coarse buckets are approximations that can be badly wrong. Native histograms (experimental since Prometheus 2.40, with active development through 2025 to make them a summary replacement) use exponential buckets that need no upfront boundary choice, aggregate cleanly, and give much better tail accuracy at lower effective cardinality. The engineering problem is choosing the right type per metric, designing bucket boundaries where classic histograms remain necessary, and planning the migration path to native histograms.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing the metric type

1. **Default to histograms, not summaries.** The 2025 consensus is explicit: use histograms for anything that will ever be aggregated across instances, routes, or time (which is essentially every service latency metric in a horizontally scaled fleet); summaries only fit single-process metrics that will never be merged.
2. **Summaries' defining limitation.** A summary precomputes fixed quantiles in the client; you cannot compute new quantiles later, cannot aggregate across targets, and cannot compute an SLO percentage from stored data the way you can with histogram buckets.
3. **Classic histograms' defining limitation.** Bucket boundaries are frozen at instrumentation time; if latency shifts from 50ms to 900ms and your buckets cluster below 100ms, every quantile estimate becomes worthless until you redeploy with new buckets.
4. **Native histograms as the direction of travel.** Development issues track complementing and ultimately replacing summaries with native histograms; managed platforms (Grafana Cloud, Amazon Managed Prometheus) and VictoriaMetrics already support them, offering predefined-bucket-free capture, aggregation, and higher-resolution tail-latency insight with cardinality savings.

## Designing classic histogram buckets

1. **Anchor buckets to the SLO threshold.** The bucket immediately above your SLO target (for example, 250ms for a 250ms p95 objective) is the load-bearing one, because SLO compliance is computed as the ratio of observations under that boundary; without it, your SLO accuracy is interpolation.
2. **Cover the distribution you might have, not just the one you have.** Add headroom buckets above current latency so regressions register as degraded-but-measured rather than saturating the top bucket, and low buckets so improvements are visible too.
3. **Use defaults only if they fit.** SDK default buckets are tuned for seconds-scale HTTP latency; sub-100ms APIs or multi-second batch jobs need custom boundaries, and shipping defaults is how teams end up with every observation in one bucket.
4. **Keep bucket counts modest.** Each bucket is a series per label combination; a dozen well-placed buckets is usually enough, and more buckets is rarely better than better-placed buckets.

## Computing SLIs from histograms

1. **The bucket-ratio formula.** Availability-style SLIs come from the fraction of events in buckets at or under the threshold versus total events; this works across instances because counters sum, which is exactly what summaries cannot do.
2. **Quantile estimation is approximate by design.** histogram_quantile interpolates within a bucket; report the bucket structure alongside the p99, or alert on the raw bucket ratio instead of the derived quantile when precision at the tail matters most.
3. **Make burn-rate alerts bucket-native.** Multi-window burn-rate SLO alerts work naturally on the under-threshold bucket ratio, and expressing the SLI that way keeps the alert math honest instead of stacking quantile approximations on top of error budgets.

## Migrating toward native histograms

1. **Verify stack support end to end.** Prometheus (experimental flag), Grafana visualization, remote-write backends, and managed offerings vary in support; confirm each hop handles native histogram payloads before instrumenting critical metrics with them.
2. **Dual-emit during evaluation.** Instrument new metrics as native histograms where supported and keep classic equivalents in parallel for comparison, mirroring how teams validated query behavior against real distributions before cutting over.
3. **Exploit the cardinality win deliberately.** Because exponential buckets replace dozens of fixed-boundary series, native histograms reduce series count for the same fidelity; take that saving explicitly rather than adding new labels until the bill returns.
4. **Track the experimental label honestly.** Native histograms remain marked experimental; run them in production with eyes open (as practitioners already do), pin versions, and re-verify visualization and alerting after Prometheus upgrades rather than assuming stability across experimental evolution.
