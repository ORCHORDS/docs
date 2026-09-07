---
title: Traefik Proxy Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: https://github.com/traefik/traefik/releases
---

# Traefik Proxy Version Governance

## Why this card exists

Traefik is the cloud-native reverse proxy and ingress used by OrchestrAI products that require automatic service discovery, dynamic configuration, and Let’s Encrypt integration without a sidecar. Traefik releases combine a Go runtime, a static configuration file, and a dynamic provider model (Docker, Kubernetes, file). Each major version ships breaking changes in the dynamic configuration schema, the router / middleware model, and the metrics export contract. This card defines how OrchestrAI selects, upgrades, and retires Traefik versions across self-hosted deployments and Traefik Hub managed.

## Scope

Applies to Traefik Proxy deployments (Traefik OSS, Traefik Enterprise, Traefik Hub) and the Traefik Kubernetes Ingress provider. Excludes the underlying orchestrators (Docker, Kubernetes, Swarm) which are governed by their own cards.

## Versioning model

Traefik follows `<major>.<minor>.<patch>`:

- **Major** — incompatible dynamic configuration schema, removal of a supported provider, or breaking router / middleware contract.
- **Minor** — backward-compatible feature additions (new providers, new middlewares, new metrics exporters); dynamic configuration schema is forward-readable by the next major.
- **Patch** — bug fixes, security patches, performance backports; no schema change.

## Supported versions

| Version | Status | End of support | Notes |
| --- | --- | --- | --- |
| 3.2.x | Primary | 2027-03 | Default for new deployments; introduces the new plugin SDK v2 contract and the OpenTelemetry-native tracing middleware. |
| 3.1.x | Maintenance | 2026-09 | Receives security patches; recommended upgrade path. |
| 3.0.x | End of life | 2026-03 | Unsupported; clusters must be migrated before renewal of any compliance certification. |
| < 3.0 | End of life | — | Not permitted in production. |

## Selection criteria

1. New deployments default to the latest stable minor in the 3.2.x line.
2. The pin is recorded in the gateway manifest and validated by the platform reconciliation loop.
3. Pre-release builds (`-rc.N`) are restricted to evaluation deployments and never promoted to production.

## Upgrade cadence

- **Patch** — applied within 14 days of upstream release.
- **Minor** — applied within 90 days, after running the cross-version router / middleware regression suite and the dynamic configuration migration rehearsal.
- **Major** — applied within 180 days; gated by a staging rehearsal that exercises provider discovery, dynamic configuration reload, and certificate renewal.

## Deprecation process

1. A version enters "deprecated" status on the OrchestrAI platform inventory on the date upstream announces end of life.
2. Deployments on deprecated versions continue to receive monitoring but are excluded from new feature rollouts.
3. End-of-life enforcement is enforced by the cluster policy controller; new routers cannot be registered on unsupported versions, and reads continue until the next scheduled maintenance window.

## Compatibility matrix

| Component | Compatible versions | Notes |
| --- | --- | --- |
| Kubernetes | 1.28, 1.29, 1.30, 1.31 | Required for the Ingress provider. |
| Docker Engine | 24.x, 25.x, 26.x | Required for the Docker provider. |
| Let’s Encrypt | ACME v2 | Supported via the ACME middleware. |
| HashiCorp Consul | 1.17.x, 1.18.x | Used as a provider for service discovery. |
| etcd | 3.5.x | Used as a KV provider for dynamic configuration. |
| OpenTelemetry | 1.30+ | Tracing via the OTLP middleware. |

## Security and compliance

- TLS 1.2+ is mandatory for all client and provider traffic.
- The dashboard is exposed only on a loopback or via a sidecar auth proxy; direct internet exposure is prohibited.
- Middleware-level audit logging is wired through the standard log pipeline; access logs must include `router`, `middleware_chain`, `client_ip`, `request_method`, `request_path`, and `status_code`.
- Personal data flowing through the gateway is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).

## Observability

- Prometheus metrics are scraped on `:8082/metrics`; alerting rules reference the standard SLO set ([Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)).
- Access and tracing logs are exported via OTLP to the central collector ([OpenTelemetry Collector Contrib Version Governance](OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)).
- Dashboards for request rate, error rate, and certificate-expiry SLO live in Grafana ([Grafana Observability Platform Version Governance](GRAFANA_VERSION_GOVERNANCE.md)).

## Related references

- [Apache APISIX API Gateway Version Governance](APISIX_VERSION_GOVERNANCE.md)
- [HAProxy Load Balancer Version Governance](HAPROXY_VERSION_GOVERNANCE.md)
- [Kong API Gateway Version Governance](KONG_VERSION_GOVERNANCE.md)
- [Envoy Proxy Version Governance](ENVOY_VERSION_GOVERNANCE.md)
- [NGINX Ingress Controller Version Governance](NGINX_INGRESS_CONTROLLER_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
