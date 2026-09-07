# API Gateway Plugin Migration Playbook

## Purpose

Migrate an API gateway plugin / middleware to a new version, a new gateway version, or a new gateway vendor while preserving the route's latency SLO, authentication posture, and authorization policy. The playbook aligns with [API Gateway Architecture Governance](../standards/API_GATEWAY_ARCHITECTURE_GOVERNANCE.md), [API Gateway Authentication & Authorization Governance](../standards/API_GATEWAY_AUTHN_AUTHZ_GOVERNANCE.md), and [API Gateway Observability Governance](../standards/API_GATEWAY_OBSERVABILITY_GOVERNANCE.md).

## Audience

Route owners, API platform engineers, security reviewers, observability reviewers.

## Pre-conditions

1. The target gateway version or vendor is registered in the central gateway catalogue with a documented support tier.
2. The target plugin / middleware version is documented with a changelog and a compatibility matrix.
3. The route's latency SLO, authentication posture, and authorization policy are documented; the evaluation set is current.
4. A staging replica of the gateway cluster is available for the rehearsal run.
5. Security review is complete for any change that affects authentication, authorization, or rate limiting.

## Procedure

1. **Scope the migration.** Identify the source and target plugin / middleware versions, the cutover strategy (canary + switch, or blue / green), the percentage of traffic to migrate, and the abort criteria. Record the plan in the migration ticket.
2. **Rehearse in staging.** Apply the new plugin / middleware to the staging cluster; replay representative traffic; measure latency, error rate, authentication correctness, and authorization correctness against the existing configuration. Resolve any regression before the production run.
3. **Configure the target plugin / middleware.** Pin the plugin / middleware version in the gateway manifest; declare the configuration in code; validate the configuration with the gateway's dry-run tool.
4. **Run the canary in production.** Route a small percentage of traffic (typically 1%–5%) to the new plugin / middleware; surface latency, error rate, and security metrics on the route dashboard.
5. **Validate during the canary.** Sample at least 1,000 requests per minute and compare latency, error rate, and security events against the baseline. Halt the canary if any metric regresses by more than the abort criterion.
6. **Expand the canary.** Gradually increase the traffic percentage in steps (e.g. 5% → 25% → 50% → 100%); at each step, re-validate the abort criteria.
7. **Cut over.** Switch 100% of traffic to the new plugin / middleware; keep the previous configuration available for 24 hours to enable fast rollback.
8. **Quarantine the previous configuration.** Mark the previous plugin / middleware version as `deprecated`; retain the configuration for at least 30 days; do not delete until the migration is signed off.
9. **Sign off.** Confirm the latency SLO is met, authentication is correct, authorization is correct, and security events are within baseline; close the migration ticket.
10. **Decommission the previous configuration.** After the quarantine window, remove the previous plugin / middleware version following the data-lifecycle procedure.

## Rollback

1. Stop the canary and freeze traffic to the new plugin / middleware.
2. Switch 100% of traffic back to the previous plugin / middleware.
3. If a fast rollback is not possible, restore the route manifest from the most recent backup; document the data gap.
4. Open a remediation ticket that captures the regression metric, the abort criterion that was triggered, and the proposed fix.
5. Communicate the rollback to stakeholders and reschedule the migration after the fix is verified.

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
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Google SRE SLI/SLO Practice Governance](../standards/GOOGLE_SRE_SLI_SLO_PRACTICE_GOVERNANCE.md)
- [Prometheus Alerting Adoption Playbook](PROMETHEUS_ALERTING_ADOPTION_PLAYBOOK.md)
