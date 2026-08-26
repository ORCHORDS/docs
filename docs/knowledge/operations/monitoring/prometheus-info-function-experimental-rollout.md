# Prometheus info() function experimental rollout

**Issue:** Manual PromQL joins with info metrics can fail during metadata churn, but replacing them wholesale with an experimental function can silently change labels or drop series.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Enable `info()` only in a canary Prometheus pool with `--enable-feature=promql-experimental-functions`, pin the Prometheus version, and inventory every dashboard, recording rule, alert, and API consumer that will use it. In the current implementation, `target_info` is the default info metric and `job` plus `instance` are the identifying labels; use an explicit `__name__` matcher when another supported info metric is intended.

Choose whether enrichment is optional or required through the data-label selector. A matcher that cannot match the empty string can remove an input series when enrichment is unavailable, while optional enrichment can return the original series. Record the expected output label set and cardinality so metadata additions cannot become an accidental alert or storage contract change.

## Verification

Evaluate the old join and `info()` over the same historical windows, including metadata change, missing/stale info series, duplicate candidates, empty labels, and OTLP-created `target_info`. Compare values, series count, labels, query time, alerts, and recording-rule output before promotion.

## Gotchas

- `info()` is experimental and may change or be removed.
- Its current identifying-label assumptions do not fit every info metric.
- Easier enrichment can still increase downstream cardinality.

## Official sources

- [Prometheus query functions: info](https://prometheus.io/docs/prometheus/latest/querying/functions/#info)
- [Prometheus introduction to info()](https://prometheus.io/blog/2025/12/16/introducing-info-function/)
