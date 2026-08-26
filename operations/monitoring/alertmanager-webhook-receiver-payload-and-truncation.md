# Alertmanager webhook receiver payload and truncation

**Issue:** A webhook consumer assumes one alert per request or an unlimited payload, then loses alerts, creates duplicate incidents, or mishandles resolved groups when Alertmanager batches and truncates notifications.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Version the receiver against Alertmanager's webhook schema and validate `version`, group `status`, `groupKey`, receiver, common labels/annotations, and each alert's status, timestamps, fingerprint, and generator URL.
- Set `send_resolved` explicitly from the incident lifecycle. Make firing and resolved handling idempotent by group key plus alert fingerprints.
- Choose `max_alerts` from the receiver's request-size and processing limits. When `truncatedAlerts` is nonzero, surface an error or retrieval workflow instead of treating the partial list as complete.
- Authenticate and encrypt the endpoint, apply a request/body limit, and redact secrets or personal data from labels, annotations, and logs.
- Acknowledge only after durable acceptance. Separate malformed-payload failures from transient downstream failures and bound retries and queue growth.

## Verification

Replay schema-valid firing and resolved groups, duplicate deliveries, reordered alerts, zero/one/many alerts, truncation, oversized annotations, unknown fields, bad timestamps, slow responses, 4xx/5xx, timeout, and receiver restart. Assert no alert is silently dropped and duplicate requests converge on one incident state.

## Gotchas

- Alert grouping means one HTTP request is not one incident or one alert.
- `max_alerts: 0` is unlimited and can exceed downstream limits.
- Common labels contain only values shared by the group; they cannot replace per-alert labels.

## Official source

- [Alertmanager webhook configuration and payload](https://prometheus.io/docs/alerting/latest/configuration/#webhook_config)
