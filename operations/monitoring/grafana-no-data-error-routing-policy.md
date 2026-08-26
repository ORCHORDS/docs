# Grafana No Data and Error routing policy

**Issue:** A threshold can remain unbreached because its query returned no series or failed, while default Grafana-generated datasource alerts take a different notification path from the original alert.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

For every Grafana-managed rule, choose No Data and Error behavior from service semantics rather than accepting defaults blindly: dedicated No Data/Error, Alerting, Normal, or Keep Last State. Critical absence-of-signal rules should not resolve to Normal unless a separate pipeline-health rule proves the same failure. Bound evaluation timeout, retry count, and pending period without making failed evaluations invisible.

Grafana's default `DatasourceNoData` and `DatasourceError` instances are separate from the original alert and carry labels such as `alertname`, `datasource_uid`, and `rulename`. Create notification-policy routes and grouping for those labels explicitly; original silences, mute timings, and routing labels may not apply. Preserve `grafana_state_reason` in notifications and incident evidence.

## Verification

Simulate an empty result, all-null result, timeout, permission error, datasource outage, stale series, transient recovery, and rule update. Assert state transitions, pending timing, deduplication, contact point, labels, silences, and resolution notifications for every configured behavior.

## Gotchas

- Keep Last State suppresses flapping but can preserve a stale Normal state indefinitely.
- Expanding query windows may hide gaps and increase evaluation cost.
- Grafana-managed and data-source-managed alert rules have different capabilities.

## Official source

- [Grafana No Data and Error states](https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rule-evaluation/nodata-and-error-states/)
