---
title: Grafana Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Grafana documentation; Grafana Labs; Grafana OSS / Enterprise / Cloud
---

# Grafana Version Governance

## Scope

This card governs how `orchords-docs` evaluates Grafana across versions, data sources, and dashboard provisioning.

## Why this card exists

Grafana is the canonical observability dashboard. Without an explicit card, the KB cites Grafana practices that ignore the data-source model (Prometheus, Loki, Tempo, Pyroscope, Elasticsearch), provisioning via files, and OSS / Enterprise / Cloud tiers.

## Versions

| Version | Status |
|---|---|
| 8.x | legacy LTS |
| 9.x | legacy |
| 10.x | current |
| 11.x | current (latest) |

References: `https://github.com/grafana/grafana/releases`.

## Editions

| Edition | Use |
|---|---|
| OSS | free |
| Enterprise | self-hosted paid |
| Cloud | managed by Grafana Labs |

## Data sources

| Source | Use |
|---|---|
| Prometheus | metrics |
| Loki | logs |
| Tempo | traces |
| Pyroscope | profiles |
| Elasticsearch | metrics / logs |
| InfluxDB | metrics |
| MySQL / Postgres | SQL |
| CloudWatch | AWS |
| BigQuery | GCP |

References: `https://grafana.com/docs/grafana/latest/datasources/`.

## Provisioning

| Type | Use |
|---|---|
| Dashboard | YAML / JSON files |
| Data source | YAML |
| Alerting | YAML |
| Plugins | YAML |

Provisioning via file: `provisioning/<type>/<name>.yaml`.

References: `https://grafana.com/docs/grafana/latest/administration/provisioning/`.

## Dashboards

| Concept | Description |
|---|---|
| Panel | visualization |
| Row | grouping |
| Variable | templated input |
| Query | data source query |
| Transform | data manipulation |

## Alerting

Grafana 9+ uses Unified Alerting:

- `Alert rules` — query + condition.
- `Contact points` — email, Slack, PagerDuty, webhook.
- `Notification policies` — grouping / routing.
- `Silences` — temporary mute.

References: `https://grafana.com/docs/grafana/latest/alerting/`.

## Authentication

| Provider | Use |
|---|---|
| Local | user/pass |
| LDAP | directory |
| OAuth2 | generic |
| SAML | federation |
| Google / GitHub / Azure AD | social / enterprise |

References: `https://grafana.com/docs/grafana/latest/auth/`.

## Cross-reference

| Domain | Card |
|---|---|
| Prometheus | `PROMETHEUS_VERSION_GOVERNANCE.md` |
| Loki | `LOKI_VERSION_GOVERNANCE.md` (deferred) |
| Tempo | (deferred) |

## Sources

- Grafana documentation: `https://grafana.com/docs/grafana/latest/`
- Grafana GitHub: `https://github.com/grafana/grafana`
- Grafana provisioning: `https://grafana.com/docs/grafana/latest/administration/provisioning/`
