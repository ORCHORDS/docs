# OAuth 2.1 Client Registration Playbook

## Purpose
This playbook defines the production-grade procedure for enabling OAuth 2.1 dynamic client registration per RFC 7591, lifecycle management per RFC 7592, and governed credential plus PKCE rotation. It standardizes how new workloads, services, and partner integrations are onboarded to the authorization server, ensures secrets and signing keys are rotated on a defensible schedule, and ties every registration event to audit, ownership, and policy controls so that governance, compliance, and security review teams can trace each client end to end.

## Audience
Application security engineers who own client onboarding review and approval. Platform engineers who operate the authorization server and registration endpoints. Identity and access management (IAM) engineers who own token, JWKS, and client lifecycle policy. Secondary readers include SRE on-call for incident handling and internal audit for evidence collection.

## Pre-conditions
The authorization server must have dynamic client registration enabled at `/oauth/register` and conform to RFC 7591 response shape. The registration access token used for the initial call must be bound to either mutual TLS or a signed JWKS assertion per RFC 7592. A durable client storage backend must exist with row-level versioning, soft delete, and a per-client `registration_access_uri`. Audit logging must capture `client_id`, actor, source IP, request body hash, and the SSA subject. A platform certificate authority or JWKS issuer must be reachable for SSA validation. Key material for `private_key_jwt` or `tls_client_auth` must be issued through the approved PKI pipeline before registration begins.

## Procedure
1. Generate a Software Statement Assertion (SSA) signed by the platform CA, embedding the team, environment, owner, and intended grant scope.
2. Submit the SSA to `POST /oauth/register` with the RFC 7592 initial access token in the `Authorization` header.
3. Capture the returned `client_id`, `registration_access_uri`, `registration_access_token`, and `client_secret_expires_at`; persist them in the secrets vault before any downstream call.
4. Choose grant types per use case: `authorization_code` with PKCE for user-facing apps, `client_credentials` for service-to-service, `device_code` for input-constrained clients. Avoid implicit and resource owner password grants.
5. Configure `token_endpoint_auth_method` to `private_key_jwt` for headless services or `tls_client_auth` where mutual TLS is available; reject `client_secret_basic` for high-trust clients.
6. Record redirect URIs using exact match; reject wildcards, fragments, and HTTP schemes outside loopback.
7. Configure refresh token rotation policy: sender-constrained rotation, one-time use, and reuse detection that revokes the entire token family on replay.
8. Subscribe to registration event webhooks (`client.created`, `client.updated`, `client.deleted`, `key.rotated`) and forward them to the SIEM and ticketing system.
9. Initiate credential rotation by `POST`ing to the `registration_access_uri` with the `reg_access_token`, replacing `jwks`, `client_secret`, or token binding; verify the new `registration_access_token` before destroying the old one.
10. Run the FAPI Read-Write or FAPI-CIBA conformance profile validation when the client is in scope; capture the test report alongside the registration record.
11. Publish the Well-Known endpoint (`/.well-known/oauth-authorization-server`) to the internal service catalog so consumers can discover issuer, endpoints, and supported algorithms.
12. Document the registration, including owner, scope, retention, and rotation schedule, then hand over to the on-call rotation; link the runbook entry in the IAM runbook index.

## Rollback
If a registration is unauthorized, compromised, or no longer needed, call `DELETE` on the `registration_access_uri` to revoke the `client_id` per RFC 7592. Immediately rotate any access tokens, refresh tokens, or DPoP keys that were issued to the client; revoke JWKS keys bound to it. Capture the revocation event in the audit log with the triggering ticket, then notify the owner and open an incident review per the IR runbook.

## References
- RFC 7591 Dynamic Client Registration Protocol
- RFC 7592 Dynamic Client Registration Management
- FAPI 2.0 Security Profile (OpenID Foundation)
- Internal cross-refs: [OAuth 2.1 Version Governance](../reference/OAUTH_2_1_VERSION_GOVERNANCE.md), [OIDC FAPI 2.0 Version Governance](../reference/OIDC_FAPI_2_VERSION_GOVERNANCE.md), [Keycloak Version Governance](../reference/KEYCLOAK_VERSION_GOVERNANCE.md).
