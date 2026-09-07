---
title: Apache APISIX API Gateway Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/apache/apisix/releases
---

# Apache APISIX API Gateway Version Governance

## Why this card exists

Apache APISIX is the high-performance, plugin-driven API gateway used by OrchestrAI products that require low-latency routing, hot-reloadable plugins, and a pluggable storage backend. APISIX releases combine a Lua + etcd-based control plane, a multi-language plugin runtime, and the APISIX Dashboard. Each major version ships breaking changes in the route / upstream / plugin schema, the storage backend contract, and the plugin SDK. This card defines how OrchestrAI selects, upgrades, and retires APISIX versions across self-hosted deployments and APISIX Cloud.

## Scope

Applies to Apache APISIX deployments (APISIX OSS, APISIX Cloud, APISIX Dashboard, the ingress-controller for Kubernetes) operated by OrchestrAI. Excludes the underlying storage engine (etcd) which is governed by its own card.

## Versioning model

APISIX follows `<major>.<minor>.<patch>`:

- **Major** — incompatible route / upstream schema, removal of a supported plugin, or breaking storage backend contract.
- **Minor** — backward-compatible feature additions (new plugins, new authn / authz methods, new observability exporters); schema is forward-readable by the next major.
- **Patch** — bug fixes, security patches, performance backports; no schema change.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 3.12.x | Primary | 2027-03 | Default for new deployments; introduces the new plugin metadata contract and the Wasm-based plugin runtime GA. |
| 3.11.x | Maintenance | 2026-09 | Receives security patches; recommended upgrade path. |
| 3.10.x | End of life | 2026-03 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 3.10 | End of life | — | Not permitted in production. |

## Selection criteria

1. New deployments default to the latest stable minor in the 3.12.x line.
2. The pin is recorded in the gateway manifest and validated by the platform reconciliation loop.
3. Pre-release builds are restricted to evaluation deployments and never promoted to production.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor** — applied within 90 days, after running the cross-version route / plugin regression suite and the etcd schema migration rehearsal.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises hot-reload, plugin upgrade, and route export / import.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Deployments on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new routes cannot be registered on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| etcd | 3.5.x | Required for the control plane; see [etcd Version Governance](../reference/ETCD_VERSION_GOVERNANCE.md). |
| OpenResty | 1.21.x, 1.23.x | Required for the data plane. |
| Kubernetes | 1.28, 1.29, 1.30, 1.31 | Required for the ingress controller. |
| Apache APISIX Dashboard | matches server minor | Version pinned via Helm chart. |
| Plugin runtimes | Lua, Java, Go, Python, Wasm | Multi-language plugin runtime supported from 3.10+. |

## Security and compliance

- TLS 1.2+ is mandatory for all client and control-plane traffic.
- The dashboard is exposed only on a loopback or via a sidecar auth proxy; direct internet exposure is prohibited.
- Route-level audit logging is wired through the standard log pipeline; access logs must include `route_id`, `upstream`, `client_ip`, `request_method`, `request_path`, `status_code`, and `latency`.
- Personal data flowing through the gateway is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on `:9091/apisix/prometheus/metrics`; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Access and tracing logs are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for request rate, error rate, and upstream health live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Traefik Proxy Version Governance](TRAEFIK_PROXY_VERSION_GOVERNANCE.md)
- [HAProxy Load Balancer Version Governance](HAPROXY_VERSION_GOVERNANCE.md)
- [Kong API Gateway Version Governance](KONG_VERSION_GOVERNANCE.md)
- [Envoy Proxy Version Governance](ENVOY_VERSION_GOVERNANCE.md)
- [NGINX Ingress Controller Version Governance](NGINX_INGRESS_CONTROLLER_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
