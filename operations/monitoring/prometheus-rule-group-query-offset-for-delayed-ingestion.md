# Prometheus rule-group query offset for delayed ingestion

**Issue:** Recording or alerting rules evaluated at the current timestamp can see incomplete data when remote ingestion, exporters, or batch pipelines consistently arrive late.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Apply a rule-group `query_offset` only after measuring a stable ingestion-delay distribution. Keep latency-sensitive rules unshifted, document the additional detection delay, and align lookback, range windows, and notification expectations with the offset. Alert separately on ingestion delay so the offset does not conceal worsening pipelines.

## Verification

Replay timestamped samples with on-time, expected-late, and excessively late arrival. Use rule tests and Prometheus query logs to prove the group evaluates the intended historical instant, alerts at the documented wall-clock delay, and still detects missing data.

## Gotchas

An offset trades freshness for completeness and cannot recover samples arriving outside retention or query windows. Oversized offsets delay incidents, while mixed offsets can make dashboards and alerts appear inconsistent.

## Official sources

- https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/
- https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
- https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/
