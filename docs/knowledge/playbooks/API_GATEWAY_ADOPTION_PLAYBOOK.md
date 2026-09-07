# API Gateway Adoption Playbook

## Purpose

Adopt an API gateway (Kong, Envoy, Traefik, Apache APISIX, HAProxy, NGINX Ingress, or managed equivalent) for a new product that requires public-facing API routing, authentication, rate limiting, and integration with the central observability stack. The playbook aligns with [API Gateway Architecture Governance](../standards/API_GATEWAY_ARCHITECTURE_GOVERNANCE.md), [API Gateway Authentication & Authorization Governance](../standards/API_GATEWAY_AUTHN_AUTHZ_GOVERNANCE.md), and [API Gateway Observability Governance](../standards/API_GATEWAY_OBSERVABILITY_GOVERNANCE.md).

## Audience

Route owners, API platform engineers, security reviewers, observability reviewers.

## Pre-conditions

1. The gateway reference card is current (`KONG_VERSION_GOVERNANCE.md`, `ENVOY_VERSION_GOVERNANCE.md`, `TRAEFIK_PROXY_VERSION_GOVERNANCE.md`, `APISIX_VERSION_GOVERNANCE.md`, `HAPROXY_VERSION_GOVERNANCE.md`, `NGINX_INGRESS_CONTROLLER_VERSION_GOVERNANCE.md`).
2. AI Impact Assessment is filed for the workload; see [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md).
3. Tenant scoping and data-classification decisions are documented.
4. Upstream services are registered in the service catalogue with declared SLAs.
5. The certificate issuance flow (central CA or Let’s Encrypt) is documented.

## Procedure

1. **Select the gateway.** Choose Kong for mature plugin ecosystem; Envoy for service-mesh alignment; Traefik for cloud-native service discovery; Apache APISIX for high-throughput routing; HAProxy for extreme connection density; NGINX Ingress for Kubernetes-only deployments.
2. **Provision the gateway cluster.** Apply the platform Helm chart or Terraform module pinned to the supported minor; record the gateway manifest in the inventory.
3. **Configure certificate issuance.** Wire the central CA or Let’s Encrypt; declare the renewal lead time and the rotation alert.
4. **Configure identity brokering.** Register the gateway as an OAuth 2.0 / OIDC relying party with the central IdP; configure JWKS caching, token validation, and audience / issuer checks.
5. **Author the route manifests.** Declare each route's name, version, owner, AI risk tier, public host pattern, upstream service, authentication requirement, rate limit, request / response size limits, timeout, retry policy, and downstream consumer list.
6. **Select and order middlewares / plugins.** Choose from the gateway's certified catalog; declare the order in the manifest; document any bespoke plugin ownership.
7. **Wire observability.** Enable Prometheus metrics, OTLP traces, access logs, SLO dashboards, and breach alerts following [API Gateway Observability Governance](../standards/API_GATEWAY_OBSERVABILITY_GOVERNANCE.md).
8. **Run a security review.** Walk through the [API Gateway Threat Model Review](../playbooks/API_GATEWAY_THREAT_MODEL_REVIEW.md) and the [API Gateway Authentication & Authorization Governance](../standards/API_GATEWAY_AUTHN_AUTHZ_GOVERNANCE.md) threat model; document mitigations and residual risk; file waivers for any unmet controls.
9. **Pilot in staging.** Route 5% of production traffic to the staging cluster; compare latency, error rate, and authentication correctness with the baseline.
10. **Promote to production.** Enable the production cluster with canary routing; set the latency SLO alert, the error-rate alert, and the certificate-expiry alert; hand off to the on-call rotation.
11. **Adopt the operating cadence.** Schedule the quarterly privilege-escalation test, the annual threat-model review, the 180-day chaos test, and the 180-day standard review.

## Rollback

1. Stop routing traffic to the new gateway cluster via DNS or upstream load balancer.
2. Switch the public-facing traffic back to the previous gateway or direct upstream access.
3. Quarantine the route manifests for forensic review; do not delete until the security review is complete.
4. Open a remediation ticket that captures the latency regression, the authentication failure, or the security finding.
5. Communicate the rollback to stakeholders via the standard incident communication channel.
6. Update the workload specification with the lessons learned before the next adoption attempt.

## References

- [API Gateway Architecture Governance](../standards/API_GATEWAY_ARCHITECTURE_GOVERNANCE.md)
- [API Gateway Authentication & Authorization Governance](../standards/API_GATEWAY_AUTHN_AUTHZ_GOVERNANCE.md)
- [API Gateway Observability Governance](../standards/API_GATEWAY_OBSERVABILITY_GOVERNANCE.md)
- [API Gateway Threat Model Review](../playbooks/API_GATEWAY_THREAT_MODEL_REVIEW.md)
- [Traefik Proxy Version Governance](../reference/TRAEFIK_PROXY_VERSION_GOVERNANCE.md)
- [Apache APISIX API Gateway Version Governance](../reference/APISIX_VERSION_GOVERNANCE.md)
- [HAProxy Load Balancer Version Governance](../reference/HAPROXY_VERSION_GOVERNANCE.md)
- [Kong API Gateway Version Governance](../reference/KONG_VERSION_GOVERNANCE.md)
- [Envoy Proxy Version Governance](../reference/ENVOY_VERSION_GOVERNANCE.md)
- [NGINX Ingress Controller Version Governance](../reference/NGINX_INGRESS_CONTROLLER_VERSION_GOVERNANCE.md)
- [HashiCorp Vault Transit Version Governance](../reference/VAULT_TRANSIT_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
