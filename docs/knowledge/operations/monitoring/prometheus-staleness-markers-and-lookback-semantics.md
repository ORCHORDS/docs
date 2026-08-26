# Prometheus staleness markers and lookback semantics

**Issue:** Dashboards and alerts can misread disappeared time series as a recent valid value or confuse missing data with zero.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Prometheus selects the newest sample within its lookback window for instant selectors and marks series stale after they disappear from a scrape or target. After the stale marker, the series is omitted until new samples arrive.

## Controls and verification

- Write explicit missing-series alerts for expected targets.
- Avoid changing lookback globally to hide scrape problems.
- Distinguish zero, absent, stale, and delayed samples.
- Test service discovery removal and exporter omission separately.
- Review recording-rule behavior during gaps.
- Stop and restore a target and verify query, dashboard, and alert timelines at each evaluation point.

## Sources

- [Prometheus: Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Prometheus: Instrumentation practices](https://prometheus.io/docs/practices/instrumentation/)
