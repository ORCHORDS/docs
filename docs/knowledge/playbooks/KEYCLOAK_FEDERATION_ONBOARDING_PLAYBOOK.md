# Keycloak Identity Federation Onboarding Playbook

## Purpose

Stand up a multi-realm Keycloak federation that bridges one or more external OIDC identity providers into a centralized identity plane. The playbook delivers a hardened realm topology with database-backed state, signed token issuance, brokered authentication, and observability hooks so dependent services consume a single, audited identity source.

## Audience

Platform engineers, IAM engineers, security engineers, and SRE on rotation who provision, operate, or recover the federation tier. Assumes working knowledge of OIDC, PostgreSQL operations, and TLS certificate handling.

## Pre-conditions

- PostgreSQL cluster (version 15+) provisioned with logical replication enabled and automated PITR backups.
- Keycloak 26+ Quarkus container image mirrored to the internal registry.
- OIDC client certificates (mTLS) issued by the internal CA for each upstream IdP.
- Egress network policy allowing HTTPS to upstream IdP discovery endpoints and JWKS URLs.
- DNS records published for the issuer URL with valid CAA and HSTS preload.
- KMS-backed database credentials resolvable at runtime via the secrets sidecar.
- Observability stack (Prometheus, OpenTelemetry collector, Grafana) reachable from the Keycloak namespace.
- Audit log destination configured (long-term object storage with immutable retention).

## Procedure

1. Render the Keycloak realm template from the governance repo at `docs/knowledge/templates/keycloak-realm.json.tmpl` and apply via the Keycloak admin REST API.
2. Run database schema migrations by launching the container with `bin/kc.sh start --optimized` against an empty schema; confirm migration completion in the startup log.
3. Wire PostgreSQL via JDBC with TLS: set `DB_URL`, `DB_USERNAME`, `DB_PASSWORD` from the KMS-backed secret; set `DB_SSL_MODE=verify-full` and pin the CA bundle.
4. Configure identity brokering to the upstream OIDC IdP using the mTLS client certificate; import the IdP metadata, validate the discovery document, and map claims through a hardened mapper set.
5. Set up UMA 2.0 authorization services: create resource servers, scopes, and policies; bind the `uma_authorization` and `uma_protection` client scopes to dependent audiences.
6. Configure access token lifecycles (default 5 minutes), refresh token rotation with reuse detection, and revocation grace windows aligned to the [OAuth 2.1 Version Governance](../reference/OAUTH_2_1_VERSION_GOVERNANCE.md).
7. Publish the JWKS URL and issuer endpoint to dependent SPs via the federation metadata card; require each SP to pin the JWKS and verify signature, issuer, and audience claims.
8. Set up admin console RBAC by creating realm-management roles per tier; restrict the `realm-admin` role to break-glass accounts and enforce step-up authentication.
9. Apply audit logging by enabling `jboss-logmanager` JSON appenders to the audit destination, and emit Keycloak metrics on `/metrics` for the Prometheus scraper.
10. Perform conformance validation against the OIDC conformance profile, run the federation smoke suite, and verify token introspection responses match expected claims.
11. Promote to staging behind a canary weight of 10%, monitor error budget for 24 hours, then promote to production with the same rollout pattern.
12. Hand over to IAM ops by updating the federation operations record, recording on-call rotation, runbook links, and credential references.

## Rollback

1. Halt the canary by reverting load balancer weights to 0% for the new realm; keep the previous generation serving traffic.
2. Stop Keycloak containers and remove the realm via admin API or by deleting the namespace, ensuring no active sessions are severed mid-flight.
3. Revoke all active tokens by rotating the realm signing keys and invalidating the JWKS cache at every dependent SP.
4. Drop the PostgreSQL schema only after confirming no retained audit records reference it; otherwise retain the schema in a cold backup.
5. Invoke the disaster recovery runbook if data corruption or key compromise is confirmed.
6. File a post-incident ticket with timeline, blast radius, and credential rotation evidence.

## References

- [OIDC FAPI 2.0 Version Governance](../reference/OIDC_FAPI_2_VERSION_GOVERNANCE.md)
- [OAuth 2.1 Version Governance](../reference/OAUTH_2_1_VERSION_GOVERNANCE.md)
- [Keycloak Version Governance](../reference/KEYCLOAK_VERSION_GOVERNANCE.md)
- Keycloak 26 Server Administration Guide (official project documentation)
- Keycloak 26 Authorization Services Guide (official project documentation)
- OIDC Core 1.0 specification