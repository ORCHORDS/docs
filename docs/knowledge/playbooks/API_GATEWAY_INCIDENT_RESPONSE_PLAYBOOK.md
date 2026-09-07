# API Gateway Incident Response Playbook

## Purpose

Respond to security and reliability incidents affecting API gateways (Kong, Envoy, Traefik, Apache APISIX, HAProxy, NGINX Ingress) and gateway plugins / middlewares. The playbook aligns with [API Gateway Authentication & Authorization Governance](../standards/API_GATEWAY_AUTHN_AUTHZ_GOVERNANCE.md), [API Gateway Architecture Governance](../standards/API_GATEWAY_ARCHITECTURE_GOVERNANCE.md), [API Gateway Observability Governance](../standards/API_GATEWAY_OBSERVABILITY_GOVERNANCE.md), and the standard security incident response process.

## Audience

On-call engineers, security responders, route owners, API platform engineers.

## Pre-conditions

1. The standard incident severity levels and the on-call rotation are documented.
2. The gateway reference card is current (`KONG_VERSION_GOVERNANCE.md`, `ENVOY_VERSION_GOVERNANCE.md`, `TRAEFIK_PROXY_VERSION_GOVERNANCE.md`, `APISIX_VERSION_GOVERNANCE.md`, `HAPROXY_VERSION_GOVERNANCE.md`, `NGINX_INGRESS_CONTROLLER_VERSION_GOVERNANCE.md`).
3. Audit logging is enabled and routed to the central SIEM; see [Audit Event Coverage Review](AUDIT_EVENT_COVERAGE_REVIEW.md).
4. Backup and configuration retention meet the standard requirements; see [NIST SP 800-189 Immutable Storage Governance](../standards/NIST_SP_800_189_IMMUTABLE_STORAGE_GOVERNANCE.md).
5. The latency SLO alert, the error-rate alert, the certificate-expiry alert, and the authentication-failure alert are wired to the on-call paging rotation.

## Procedure

1. **Detect and triage.** Identify the incident class: token theft, token replay, algorithm confusion, mTLS bypass, API key leakage, privilege escalation, credential stuffing, configuration drift, plugin failure, certificate expiry, latency SLO breach, error-rate breach, or availability outage. Assign severity using the standard matrix.
2. **Contain.** Block malicious source IPs or ASNs at the gateway; revoke the implicated tokens and API keys; freeze configuration changes via the gateway's admission controller; isolate the affected cluster or route.
3. **Eradicate.** Rotate credentials, rebuild the gateway cluster from a known-good configuration snapshot, and remove malicious plugins or middlewares. Confirm the threat is no longer present before recovery.
4. **Recover.** Re-enable routes; restore the workload to the previous latency SLO; verify tenant scoping, authentication posture, and authorization policy before lifting the freeze.
5. **Communicate.** Issue stakeholder updates on the standard incident cadence; for regulated workloads, notify the Security owner and the privacy officer within the SLA.
6. **Investigate.** Reconstruct the timeline from access logs, audit logs, and OTLP traces; identify the affected routes, the auth method, and the workload specification that permitted the exposure.
7. **Document.** Write the incident report with the timeline, the root cause, the affected route manifest, the SLO that was breached, and the customer impact.
8. **Remediate.** Open remediation tickets for control gaps; update the threat model, the route manifest, and the gateway manifest; schedule the verification review.
9. **Verify.** Re-run the security review checklist and the SLO regression suite before closing the incident.
10. **Learn.** Present the incident at the monthly platform guild; incorporate the lessons learned into [API Gateway Authentication & Authorization Governance](../standards/API_GATEWAY_AUTHN_AUTHZ_GOVERNANCE.md) at the next 180-day review.

## Rollback

1. If the freeze causes a workload outage, switch the affected routes to the previous gateway cluster or direct upstream access.
2. If the rebuild fails, restore the gateway configuration from the most recent immutable snapshot; document the configuration gap.
3. If the credential rotation breaks a downstream system, roll back the rotation using the break-glass procedure and re-issue scoped credentials.
4. Communicate the rollback to stakeholders via the standard incident communication channel.
5. Open a follow-up ticket to address the rollback's root cause before re-attempting recovery.

## References

- [API Gateway Authentication & Authorization Governance](../standards/API_GATEWAY_AUTHN_AUTHZ_GOVERNANCE.md)
- [API Gateway Architecture Governance](../standards/API_GATEWAY_ARCHITECTURE_GOVERNANCE.md)
- [API Gateway Observability Governance](../standards/API_GATEWAY_OBSERVABILITY_GOVERNANCE.md)
- [API Gateway Threat Model Review](../playbooks/API_GATEWAY_THREAT_MODEL_REVIEW.md)
- [Traefik Proxy Version Governance](../reference/TRAEFIK_PROXY_VERSION_GOVERNANCE.md)
- [Apache APISIX API Gateway Version Governance](../reference/APISIX_VERSION_GOVERNANCE.md)
- [HAProxy Load Balancer Version Governance](../reference/HAPROXY_VERSION_GOVERNANCE.md)
- [Kong API Gateway Version Governance](../reference/KONG_VERSION_GOVERNANCE.md)
- [Envoy Proxy Version Governance](../reference/ENVOY_VERSION_GOVERNANCE.md)
- [NGINX Ingress Controller Version Governance](../reference/NGINX_INGRESS_CONTROLLER_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [HashiCorp Vault Transit Version Governance](../reference/VAULT_TRANSIT_VERSION_GOVERNANCE.md)
- [Audit Event Coverage Review](AUDIT_EVENT_COVERAGE_REVIEW.md)
- [Audit Storage Capacity Review](AUDIT_STORAGE_CAPACITY_REVIEW.md)
- [Encryption Coverage Review](ENCRYPTION_COVERAGE_REVIEW.md)
