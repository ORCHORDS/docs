# API Gateway Authentication & Authorization Governance

## 1. Scope

Govern the authentication, authorization, and identity-brokering posture of API gateways (Kong, Envoy, Traefik, Apache APISIX, HAProxy, NGINX Ingress, and equivalents) operated by OrchestrAI. Covers API key, OAuth 2.0 / OIDC, mTLS, JWT, and custom authn / authz plugins; threat modelling; and incident response.

Excludes identity-provider governance (Okta, Auth0, Keycloak), which is governed by [HashiCorp Vault Transit Version Governance](../reference/VAULT_TRANSIT_VERSION_GOVERNANCE.md) and the central IAM cards. Excludes gateway architecture, which is governed by [API Gateway Architecture Governance](API_GATEWAY_ARCHITECTURE_GOVERNANCE.md).

## 2. Normative references

- [API Gateway Architecture Governance](API_GATEWAY_ARCHITECTURE_GOVERNANCE.md)
- [API Gateway Observability Governance](API_GATEWAY_OBSERVABILITY_GOVERNANCE.md)
- [API Gateway Threat Model Review](../playbooks/API_GATEWAY_THREAT_MODEL_REVIEW.md)
- [Traefik Proxy Version Governance](../reference/TRAEFIK_PROXY_VERSION_GOVERNANCE.md)
- [Apache APISIX API Gateway Version Governance](../reference/APISIX_VERSION_GOVERNANCE.md)
- [HAProxy Load Balancer Version Governance](../reference/HAPROXY_VERSION_GOVERNANCE.md)
- [Kong API Gateway Version Governance](../reference/KONG_VERSION_GOVERNANCE.md)
- [Envoy Proxy Version Governance](../reference/ENVOY_VERSION_GOVERNANCE.md)
- [NGINX Ingress Controller Version Governance](../reference/NGINX_INGRESS_CONTROLLER_VERSION_GOVERNANCE.md)
- [HashiCorp Vault Transit Version Governance](../reference/VAULT_TRANSIT_VERSION_GOVERNANCE.md)
- [HashiCorp Boundary Secure Access Version Governance](../reference/BOUNDARY_VERSION_GOVERNANCE.md)
- [AI Risk Tiering Practice Governance](AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md)
- [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md)

## 3. Terms and definitions

- **Identity provider (IdP)** — an external system that authenticates principals and issues tokens (OAuth 2.0 / OIDC).
- **Token** — a signed assertion of a principal's identity and entitlements (JWT, opaque token).
- **mTLS** — mutual TLS where both client and server present certificates for authentication.
- **Authorization policy** — the rules that determine what an authenticated principal is permitted to do.
- **Token broker** — the gateway plugin that validates tokens issued by an external IdP.

## 4. Threat model

The standard threat model for API gateway authentication includes:

1. **Token theft** — an attacker exfiltrates a JWT or opaque token and replays it against the gateway.
2. **Token replay** — an attacker reuses a captured token across multiple requests or sessions.
3. **Algorithm confusion** — an attacker submits a JWT with a forged `alg` header (e.g. `none`, `HS256` with the public key as the secret).
4. **mTLS bypass** — an attacker downgrades the connection to plaintext or uses an expired / revoked certificate.
5. **API key leakage** — an attacker extracts an API key from a public repository, a log file, or a developer endpoint.
6. **Privilege escalation** — an attacker exploits a misconfigured authorization policy to access routes above their tier.
7. **Credential stuffing** — an attacker submits large volumes of stolen credentials against the gateway.

Each threat is mapped to a control in this standard and reviewed annually.

## 5. Identity brokering

1. The gateway is configured as an OAuth 2.0 / OIDC relying party; the IdP is registered in the central IAM registry.
2. Token validation is performed locally at the gateway (signature, issuer, audience, expiry, revocation list); the gateway does not call the IdP on every request.
3. Tokens are validated against a JWKS endpoint with a key rotation interval declared in the manifest.
4. The gateway refuses tokens with mismatched `aud`, `iss`, `exp`, or `nbf` claims; failures produce an audit event.

## 6. mTLS

1. mTLS is required for routes that serve internal service-to-service traffic; the client certificate authority is the central PKI.
2. The gateway validates the client certificate chain, the expiry, and the revocation status against the central CRL or OCSP responder.
3. Routes that accept mTLS reject plaintext connections; the connection downgrade alert is wired to the on-call paging rotation.
4. mTLS certificates are rotated automatically with a lead time of at least 14 days.

## 7. API keys

1. API keys are issued by the central API key registry; the gateway validates the key against the registry with a local cache TTL declared in the manifest.
2. API keys are scoped per consumer, per route, and per environment; cross-environment reuse is prohibited.
3. API key rotation is enforced at least every 180 days; expired keys are rejected by the gateway.
4. API keys are never logged in plaintext; access logs include only the key hash and the key ID.

## 8. Authorization policy

1. Authorization is enforced at the gateway; downstream services may apply additional checks but must not rely on the gateway alone.
2. Authorization policies are declared in the manifest; runtime override is prohibited without a change ticket.
3. Policies are evaluated using a deny-by-default model; explicit allow rules are required for every route.
4. Privilege escalation tests are run at least every 90 days; failures open a remediation ticket.

## 9. Encryption

1. TLS 1.2+ is required for all client and upstream traffic.
2. Tokens and API keys at rest are encrypted using envelope encryption with keys stored in the central KMS; see [Encryption Coverage Review](../playbooks/ENCRYPTION_COVERAGE_REVIEW.md).
3. Token signing keys are rotated automatically with a lead time of at least 14 days.
4. The token rotation alert is wired to the on-call paging rotation.

## 10. Audit logging

1. All authentication attempts, authorization decisions, and token-issuance events produce audit events; see [Audit Event Coverage Review](../playbooks/AUDIT_EVENT_COVERAGE_REVIEW.md).
2. Audit events include `actor`, `route`, `authn_method`, `authz_decision`, `source_ip`, and `user_agent`.
3. Audit logs are replicated to the central SIEM with retention of at least 24 months.
4. Anomaly detection alerts on unusual auth patterns (sudden spike in failed logins, repeated token reuse from different source IPs, auth attempts outside business hours).

## 11. Incident response

1. Suspected token theft, token replay, algorithm confusion, mTLS bypass, API key leakage, privilege escalation, or credential stuffing triggers the standard security incident response process.
2. Affected tokens and API keys are revoked within one hour of incident confirmation.
3. The incident post-mortem identifies the route, the auth method, and the workload specification that permitted the exposure.
4. Post-incident actions are tracked in the remediation backlog and reviewed at the monthly platform guild.

## 12. Operating model

1. The Security team owns the threat model, the security review process, and the incident response process.
2. The Gateway Platform team owns the implementation of the controls in this standard across shared infrastructure.
3. Route owners are accountable for authorization policy, API key scoping, and downstream enforcement.
4. The security and platform guilds meet jointly each quarter to review the threat model and the control coverage.

## 13. Exceptions

Exceptions require a documented waiver approved by the Knowledge Engineering owner and the Security owner. Each waiver has a maximum lifetime of 90 days and is reviewed at expiry.

## 14. Review cycle

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
