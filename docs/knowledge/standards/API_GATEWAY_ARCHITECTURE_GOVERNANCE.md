# API Gateway Architecture Governance

## 1. Scope

Govern the architecture, selection, and operational use of API gateways (Kong, Envoy, Traefik, Apache APISIX, HAProxy, NGINX Ingress, and managed equivalents) across OrchestrAI products. Covers routing, traffic management, plugin / middleware selection, certificate lifecycle, and integration with authentication, observability, and rate limiting subsystems.

Excludes the underlying service-mesh data planes (Istio, Linkerd, Cilium), which are governed by their own cards. Excludes authentication and authorization mechanisms, which are governed by [API Gateway Authentication & Authorization Governance](API_GATEWAY_AUTHN_AUTHZ_GOVERNANCE.md). Excludes gateway observability, which is governed by [API Gateway Observability Governance](API_GATEWAY_OBSERVABILITY_GOVERNANCE.md).

## 2. Normative references

- [Traefik Proxy Version Governance](../reference/TRAEFIK_PROXY_VERSION_GOVERNANCE.md)
- [Apache APISIX API Gateway Version Governance](../reference/APISIX_VERSION_GOVERNANCE.md)
- [HAProxy Load Balancer Version Governance](../reference/HAPROXY_VERSION_GOVERNANCE.md)
- [Kong API Gateway Version Governance](../reference/KONG_VERSION_GOVERNANCE.md)
- [Envoy Proxy Version Governance](../reference/ENVOY_VERSION_GOVERNANCE.md)
- [NGINX Ingress Controller Version Governance](../reference/NGINX_INGRESS_CONTROLLER_VERSION_GOVERNANCE.md)
- [NGINX Version Governance](../reference/NGINX_VERSION_GOVERNANCE.md)
- [API Gateway Threat Model Review](../playbooks/API_GATEWAY_THREAT_MODEL_REVIEW.md)
- [API Gateway Authentication & Authorization Governance](API_GATEWAY_AUTHN_AUTHZ_GOVERNANCE.md)
- [API Gateway Observability Governance](API_GATEWAY_OBSERVABILITY_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)

## 3. Terms and definitions

- **Route** — a named mapping from a public-facing request pattern to an internal upstream service.
- **Middleware / plugin** — a reusable component that transforms requests or responses (rate limit, auth, header rewrite, transformation).
- **Upstream** — the destination backend that the gateway routes traffic to.
- **Listener** — a network endpoint (host:port) that accepts client connections.
- **Hot reload** — the ability to apply configuration changes without restarting the gateway process.

## 4. Gateway selection

1. Kong is the default API gateway for products that need a mature plugin ecosystem, declarative configuration, and an enterprise support path.
2. Envoy is the default for products that need a service-mesh-aligned data plane, xDS-based dynamic configuration, and WASM filters.
3. Traefik is preferred for cloud-native deployments that need automatic service discovery and Let’s Encrypt integration.
4. Apache APISIX is preferred for products that need high-throughput routing, low-latency plugin execution, and a pluggable storage backend.
5. HAProxy is preferred for extreme connection density, L4 + L7 routing, and stable behaviour under sustained load.
6. NGINX Ingress is preferred for Kubernetes-only deployments with mature ingress-controller expectations.
7. The choice is recorded in the gateway manifest and reviewed annually.

## 5. Route contract

1. Every route declares its name, version, owner, AI risk tier, public host pattern, upstream service, authentication requirement, rate limit, request / response size limits, timeout, retry policy, and downstream consumer list.
2. Route versions are immutable; breaking changes require a new major version.
3. Backwards-compatible additions (new headers, new transformations) are permitted under a new minor version.
4. Deprecated routes remain routable for at least 90 days after deprecation; the deprecation date and the migration target are recorded in the manifest.

## 6. Middleware / plugin selection

1. Middlewares and plugins are selected from the gateway's certified catalog; bespoke middlewares require a security review and a documented maintenance owner.
2. The choice is recorded in the gateway manifest; runtime override is prohibited without a change ticket.
3. Plugin execution order is declared in the manifest; runtime override is prohibited.
4. Plugin hot-reload is permitted only when the gateway's hot-reload contract is documented and validated at adoption time.

## 7. Upstream and load balancing

1. The upstream service is registered with a health check, a circuit breaker, and a connection pool size declared in the manifest.
2. Active health checks are required for production upstreams; passive health checks are permitted as a supplement.
3. Load-balancing algorithm and session-affinity policy are declared in the manifest; runtime override is prohibited.
4. Canary and blue / green deployments use the gateway's traffic-splitting primitives; ad-hoc traffic splitting is prohibited.

## 8. Certificate lifecycle

1. Public certificates are issued by the central certificate authority or Let’s Encrypt; private certificates are issued by the central PKI; see [HashiCorp Vault Transit Version Governance](../reference/VAULT_TRANSIT_VERSION_GOVERNANCE.md).
2. Certificate renewal is automated; the renewal lead time is at least 30 days before expiry.
3. Certificates are pinned to a listener; orphan certificates are removed on rotation.
4. The certificate expiry alert is wired to the on-call paging rotation.

## 9. Rate limiting and quotas

1. Every public-facing route declares a rate-limit policy (requests per second, requests per minute, burst) and a quota policy (requests per day per API key) in the manifest.
2. Rate-limit policies are enforced at the gateway; downstream services may apply additional limits but must not rely on the gateway alone.
3. Rate-limit breaches produce a metric and, for chronic offenders, a security event.
4. Quota exhaustion triggers a 429 response with a Retry-After header.

## 10. Reliability and observability

1. Routes must declare an expected latency SLO and an expected availability SLO; chronic breaches trigger a route-contract review.
2. Gateway access logs are exported to the central log pipeline; see [API Gateway Observability Governance](API_GATEWAY_OBSERVABILITY_GOVERNANCE.md).
3. SLOs are defined per route using the standard SLO template; see [Google SRE SLI/SLO Practice Governance](GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md).
4. Dashboards and alerts are owned by the route owner; see [Grafana Observability Platform Version Governance](../reference/GRAFANA_VERSION_GOVERNANCE.md) and [Prometheus Alerting Adoption Playbook](../playbooks/PROMETHEUS_ALERTING_ADOPTION_PLAYBOOK.md).

## 11. Security

1. TLS is required for all client and upstream traffic.
2. The dashboard, the runtime API, and the Data Plane API are bound to loopback or a private network; direct internet exposure is prohibited.
3. Personal data flowing through the gateway is in scope of the AI risk-tiering standard ([AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)).
4. Authentication and authorization mechanisms are governed by [API Gateway Authentication & Authorization Governance](API_GATEWAY_AUTHN_AUTHZ_GOVERNANCE.md).

## 12. Operating model

1. The Gateway Platform team owns the shared gateway infrastructure and the reference route / middleware templates.
2. Route owners own their routes, rate limits, and SLAs.
3. The Gateway Platform guild meets monthly to review latency regressions, certificate renewals, and adoption of new gateways.
4. New gateway vendors are evaluated by the Gateway Platform team and approved by the Security owner.

## 13. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the Security owner. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 14. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
