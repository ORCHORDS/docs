---
title: Prometheus and OpenMetrics Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Prometheus documentation; CNCF Prometheus project; OpenMetrics specification (CNCF)
---

# Prometheus and OpenMetrics Version Governance

## Scope

This card governs how `orchords-docs` evaluates Prometheus and the OpenMetrics format across versions, scrape protocols, and storage backends.

## Why this card exists

Prometheus is the canonical pull-based monitoring system (CNCF graduated, January 2019). Without an explicit card, the KB cites Prometheus practices that ignore the OpenMetrics format, TSDB storage layers, and remote-write receivers.

## Versions

| Version | Status |
|---|---|
| 1.x–2.30 | legacy |
| 2.31–2.45 | current stable |
| 2.46–2.55 | current |

References: `https://github.com/prometheus/prometheus/releases`.

## Data model

| Concept | Description |
|---|---|
| Counter | monotonically increasing |
| Gauge | arbitrary up/down |
| Histogram | bucketed distribution |
| Summary | quantile summary |
| Info | key-value info |

References: `https://prometheus.io/docs/concepts/metric_types/`.

## Exposition formats

| Format | Status |
|---|---|
| Prometheus text | legacy (still supported) |
| OpenMetrics 1.0.0 | preferred |

OpenMetrics is the canonical exposition format (CNCF), with `OpenMetrics-text` and `OpenMetrics-Protobuf` profiles.

References: `https://openmetrics.io/`.

## Scrape configuration

| Field | Purpose |
|---|---|
| `scrape_interval` | 15s default |
| `scrape_timeout` | 10s default |
| `metrics_path` | /metrics default |
| `scheme` | http / https |
| `bearer_token_file` | bearer auth |
| `tls_config` | client TLS |

References: `https://prometheus.io/docs/prometheus/latest/configuration/configuration/`.

## Storage

| Backend | Use |
|---|---|
| TSDB | local default |
| Thanos | long-term storage |
| Cortex / Mimir | multi-tenant SaaS |
| VictoriaMetrics | compatible drop-in |
| Remote-write | external storage |

References: `https://prometheus.io/docs/prometheus/latest/storage/`.

## Recording rules and alerts

| Type | Use |
|---|---|
| Recording rule | pre-computed metric |
| Alerting rule | alert condition |

Rules files: YAML, evaluated by `rule_files` block.

References: `https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/`.

## Cross-reference

| Domain | Card |
|---|---|
| Kubernetes | `KUBERNETES_VERSION_GOVERNANCE.md` |
| Envoy | `ENVOY_VERSION_GOVERNANCE.md` |
| OTel | `OPENTELEMETRY_VERSION_GOVERNANCE.md` (deferred) |

## Sources

- Prometheus documentation: `https://prometheus.io/docs/`
- Prometheus GitHub: `https://github.com/prometheus/prometheus`
- OpenMetrics: `https://openmetrics.io/`
- CNCF Prometheus: `https://www.cncf.io/projects/prometheus/`
