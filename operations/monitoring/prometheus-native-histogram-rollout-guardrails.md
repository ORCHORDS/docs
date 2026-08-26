# Prometheus native histogram rollout guardrails

**Issue:** Enabling native histograms without an end-to-end compatibility and resource plan can silently drop distribution data or cause unexpected memory, storage, query, and remote-write behavior.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Treat native histograms as an end-to-end migration across instrumentation, scraping, storage, PromQL, recording rules, dashboards, alerts, federation, and remote write. Prometheus documents them as stable starting with v3.8, but scraping remains explicitly controlled by `scrape_native_histograms`; remote write uses `send_native_histograms`.

Their sparse representation and mergeable exponential schemas can improve resolution and reduce series overhead compared with classic buckets. However, dynamically populated buckets still consume resources, and externally influenced value ranges can create memory pressure. Choose bucket-factor, zero-threshold, and bucket-limiting controls intentionally.

## Operational controls

- Inventory every receiver and remote endpoint for native-histogram support before enabling transmission.
- Canary a bounded set of metrics and retain classic histograms during comparison where the client library permits.
- Alert on scrape failures, rejected schemas, remote-write failures, and unexpected sample or bucket growth.
- Rewrite PromQL carefully: native histogram aggregation generally does not use the classic `le` label.
- Validate recording rules and dashboards with representative counter resets and mixed-version periods.
- Set instrumentation limits against adversarial or unbounded observation ranges.

## Verification

1. Confirm the scraper ingests native histogram samples only for intended jobs.
2. Compare counts, sums, quantiles, and alert behavior with the prior classic histogram.
3. Verify remote-write receivers preserve the samples.
4. Measure memory, storage, query latency, and network effects under production-like cardinality.
5. Test rollback to classic-only ingestion without losing required alerts.

## Sources

- [Prometheus: Native Histograms](https://prometheus.io/docs/specs/native_histograms/)
- [Prometheus: Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
