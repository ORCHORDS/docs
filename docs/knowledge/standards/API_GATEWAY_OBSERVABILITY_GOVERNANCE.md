# API Gateway Observability Governance

## 1. Scope

Govern the observability posture of API gateways (Kong, Envoy, Traefik, Apache APISIX, HAProxy, NGINX Ingress, and equivalents) operated by OrchestrAI. Covers metrics, logs, traces, audit events, and SLO definition; integration with the central observability stack; and reliability engineering.

Excludes general observability platform governance (Prometheus, Grafana, OpenTelemetry Collector, Loki, Jaeger), which is governed by [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md) and the central observability cards. Excludes gateway authentication logging, which is governed by [API Gateway Authentication & Authorization Governance](API_GATEWAY_AUTHN_AUTHZ_GOVERNANCE.md).

## 2. Normative references

- [API Gateway Architecture Governance](API_GATEWAY_ARCHITECTURE_GOVERNANCE.md)
- [API Gateway Authentication & Authorization Governance](API_GATEWAY_AUTHN_AUTHZ_GOVERNANCE.md)
- [API Gateway Threat Model Review](../playbooks/API_GATEWAY_THREAT_MODEL_REVIEW.md)
- [Traefik Proxy Version Governance](../reference/TRAEFIK_PROXY_VERSION_GOVERNANCE.md)
- [Apache APISIX API Gateway Version Governance](../reference/APISIX_VERSION_GOVERNANCE.md)
- [HAProxy Load Balancer Version Governance](../reference/HAPROXY_VERSION_GOVERNANCE.md)
- [Kong API Gateway Version Governance](../reference/KONG_VERSION_GOVERNANCE.md)
- [Envoy Proxy Version Governance](../reference/ENVOY_VERSION_GOVERNANCE.md)
- [NGINX Ingress Controller Version Governance](../reference/NGINX_INGRESS_CONTROLLER_VERSION_GOVERNANCE.md)
- [Prometheus Monitoring System Version Governance](../reference/PROMETHEUS_VERSION_GOVERNANCE.md)
- [Grafana Observability Platform Version Governance](../reference/GRAFANA_VERSION_GOVERNANCE.md)
- [OpenTelemetry Collector Contrib Version Governance](../reference/OTEL_COLLECTOR_CONTRIB_VERSION_GOVERNANCE.md)
- [Jaeger Tracing Version Governance](../reference/JAEGER_VERSION_GOVERNANCE.md)
- [Loki Version Governance](../reference/LOKI_VERSION_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [Alerting Principles Governance](ALERTING_PRINCIPLES_GOVERNANCE.md)

## 3. Terms and definitions

- **Access log** — a structured record of a single request handled by the gateway.
- **Trace** — a distributed record of a request as it traverses multiple services.
- **SLI** — Service Level Indicator, the quantitative measure of a service behaviour.
- **SLO** — Service Level Objective, the target value or range for an SLI.
- **Error budget** — the complement of the SLO; the permissible amount of unreliability over a period.

## 4. Metrics

1. Every gateway emits Prometheus metrics on a stable endpoint; the scraping configuration is recorded in the gateway manifest.
2. Mandatory metrics include `requests_total`, `request_duration_seconds`, `response_size_bytes`, `active_connections`, and `upstream_health`.
3. Metrics are labeled with `route`, `upstream`, `method`, and `status_class` (2xx, 3xx, 4xx, 5xx).
4. Metric cardinality is bounded by route count × status class; cardinality above the budget triggers a remediation ticket.

## 5. Logs

1. Every gateway emits structured access logs in JSON or logfmt; the format is declared in the gateway manifest.
2. Mandatory fields include `timestamp`, `request_id`, `route`, `method`, `path`, `status_code`, `latency_ms`, `client_ip`, `user_agent`, `bytes_sent`, `bytes_received`, `upstream`, and `upstream_status`.
3. Logs are routed to Loki via the central log pipeline; see [Loki Version Governance](../reference/LOKI_VERSION_GOVERNANCE.md) and [Fluent Bit Version Governance](../reference/FLUENTBIT_VERSION_GOVERNANCE.md).
4. Personal data in access logs is redacted at the gateway; see [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).

## 6. Traces

1. Every gateway emits OTLP traces for inbound requests and upstream calls; sampling rate is declared in the manifest.
2. Mandatory trace attributes include `http.method`, `http.route`, `http.status_code`, `http.scheme`, `net.peer.ip`, and `upstream.service`.
3. Traces are routed to the central collector and stored in Jaeger; see [Jaeger Tracing Version Governance](../reference/JAEGER_VERSION_GOVERNANCE.md).
4. Trace sampling rate for new routes defaults to 100% for the first 24 hours, then adjusts to the manifest declaration.

## 7. SLO definition

1. Every public route declares a latency SLO (p50, p95, p99) and an availability SLO (success ratio over a window); see [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md).
2. SLO violations produce an alert routed to the route owner via the standard paging rotation; see [Alerting Principles Governance](ALERTING_PRINCIPLES_GOVERNANCE.md).
3. Error-budget exhaustion triggers a freeze on non-essential changes for the affected route.
4. SLOs are reviewed at least every 180 days.

## 8. Audit events

1. Authentication attempts, authorization decisions, configuration changes, and certificate rotations produce audit events; see [API Gateway Authentication & Authorization Governance](API_GATEWAY_AUTHN_AUTHZ_GOVERNANCE.md).
2. Audit events are routed to the central SIEM via the audit pipeline.
3. Audit retention is at least 24 months.
4. Anomaly detection alerts on unusual access patterns (sudden spike in 5xx, repeated auth failures, traffic from unfamiliar ASNs).

## 9. Reliability engineering

1. The gateway is deployed with redundancy across at least two availability zones; see [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md).
2. Health checks (active and passive) are declared in the manifest; chronic health-check failures trigger an alert.
3. Configuration changes are rolled out gradually (canary → full) using the gateway's traffic-splitting primitives.
4. Chaos testing (latency injection, error injection, partition injection) is run at least every 180 days; results feed back into the SLO and alert tuning.

## 10. Operating model

1. The Gateway Platform team owns the shared observability configuration (dashboards, alerts, SLOs).
2. Route owners own the SLO definitions and the workload-specific dashboards.
3. The Observability guild meets monthly to review SLO breaches, alert noise, and adoption of new observability features.
4. New gateway vendors are evaluated by the Gateway Platform team and approved by the Observability owner.

## 11. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the Observability owner. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 12. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
