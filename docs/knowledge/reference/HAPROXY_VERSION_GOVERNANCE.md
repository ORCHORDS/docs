---
title: HAProxy Load Balancer Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/haproxy/haproxy/blob/master/CHANGELOG
---

# HAProxy Load Balancer Version Governance

## Why this card exists

HAProxy is the high-performance TCP / HTTP load balancer and reverse proxy used by OrchestrAI products that require extreme connection density, L4 + L7 routing, and stable behaviour under sustained load. HAProxy releases combine the HAProxy daemon, the Data Plane API, and the Lua-based fetch / converter ecosystem. Each major version ships breaking changes in the configuration parser, the runtime API, and the supported fetch functions. This card defines how OrchestrAI selects, upgrades, and retires HAProxy versions across self-hosted deployments and HAProxy Enterprise / HAProxy ALOHA.

## Scope

Applies to HAProxy Community, HAProxy Enterprise, HAProxy ALOHA, and the HAProxy Data Plane API. Excludes the underlying operating systems (Linux distributions) which are governed by their own cards.

## Versioning model

HAProxy follows `<major>.<minor>` for community releases (odd minors are dev, even minors are stable) and `<major>.<minor>.<patch>` for LTS:

- **Major** — incompatible configuration parser, removal of a supported fetch / converter, or breaking runtime API contract.
- **Minor (stable)** — backward-compatible feature additions (new fetch / converter, new log format, new stick table metric); configuration is forward-readable by the next major.
- **Patch** — bug fixes, security patches, performance backports; no schema change.

Long-Term-Support releases are labelled `.<minor>.LTS` and receive patch backports for 5 years (per HAProxy Technologies LTS programme).

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 3.0.x LTS | Primary | 2030-06 | Default for new deployments; introduces the new stick-table metric set and the QUIC / HTTP3 GA. |
| 2.8.x LTS | Maintenance | 2028-12 | Receives security patches; recommended upgrade path for conservative workloads. |
| 2.6.x | End of life | 2026-06 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 2.6 | End of life | — | Not permitted in production. |

## Selection criteria

1. New deployments default to the latest LTS minor (currently 3.0.x LTS).
2. The pin is recorded in the gateway manifest and validated by the platform reconciliation loop.
3. Conservative workloads that depend on legacy Lua fetches may pin to the 2.8.x LTS line for the lifetime of the LTS window.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor (LTS)** — applied within 90 days.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises configuration reload, Data Plane API migration, and stick-table migration.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Deployments on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new frontends / backends cannot be registered on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| Data Plane API | matches server version | Pinned via package manager. |
| Kubernetes Ingress | ingress-nginx v1.10+, HAProxy Ingress v0.14+ | Selection recorded in the gateway manifest. |
| Prometheus exporter | haproxy_exporter 0.14+ | Required for Prometheus metrics. |
| OpenTelemetry | 1.30+ | Tracing via the OpenTelemetry module. |
| Linux kernel | 4.18+ | Required for the newest stick-table features. |

## Security and compliance

- TLS 1.2+ is mandatory for all client and Data Plane API traffic.
- The runtime API and the Data Plane API are bound to loopback or a private network; direct internet exposure is prohibited.
- Frontend-level audit logging is wired through the standard log pipeline; access logs must include `frontend`, `backend`, `client_ip`, `request_method`, `request_path`, `status_code`, and `latency`.
- Personal data flowing through HAProxy is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped via `haproxy_exporter`; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Access and tracing logs are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for connection rate, backend health, and stick-table saturation live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Traefik Proxy Version Governance](TRAEFIK_PROXY_VERSION_GOVERNANCE.md)
- [Apache APISIX API Gateway Version Governance](APISIX_VERSION_GOVERNANCE.md)
- [Kong API Gateway Version Governance](KONG_VERSION_GOVERNANCE.md)
- [Envoy Proxy Version Governance](ENVOY_VERSION_GOVERNANCE.md)
- [NGINX Ingress Controller Version Governance](NGINX_INGRESS_CONTROLLER_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
