# Prometheus missing-series alerts with absent_over_time

**Issue:** An alert expression can silently return no series when a target or metric disappears, making missing telemetry look healthy.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Use PromQL absence functions such as `absent()` or `absent_over_time()` when disappearance is itself actionable. Choose a range longer than normal scrape and evaluation jitter but shorter than the detection objective.

Scope selectors carefully. Dynamic entities may disappear legitimately, so join absence detection with an authoritative inventory or expected-target signal where possible.

## Controls

- Separate missing telemetry from a measured healthy zero.
- Account for deployment, discovery, and maintenance windows.
- Avoid high-cardinality synthetic expectations.
- Include ownership and runbook context.
- Pair with Prometheus target and rule evaluation health.
- Unit-test label derivation.

## Verification

1. Stop an expected exporter and confirm the alert timeline.
2. Restore it and confirm resolution.
3. Remove a legitimately decommissioned target and ensure inventory prevents a false alert.
4. Simulate delayed scrapes.
5. Run promtool rule tests.

## Sources

- [Prometheus: Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Prometheus: Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
