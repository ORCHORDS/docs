---
title: "OAuth 2.1 Client Integration Playbook"
owner: "Identity and Access Management Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# OAuth 2.1 Client Integration Playbook

## Trigger

Use this playbook when a new application, service, or integration must obtain OAuth 2.1 tokens to access protected resources, or when an existing integration is being upgraded, audited, or migrated between authorization servers.

## Scope

Apply the process to confidential public clients, machine-to-machine clients, native applications, single-page applications, and backend services that act as OAuth clients or resource servers, including token storage, refresh, and revocation.

## Inputs

- target authorization server endpoint, supported flows, and discovery URL;
- client identity and redirect URI registration;
- required scopes, claims, audience, and PKCE posture;
- token lifetime, refresh window, and revocation policy;
- security profile of the client (public, confidential, first-party, third-party).

## Steps

1. **Register the client.** Register the client identifier, redirect URIs (exact match), grant types, scopes, token endpoint authentication method, and client authentication keys with the authorization server; record the registration metadata.
2. **Choose the appropriate flow.** Use authorization code with PKCE for interactive clients; use client credentials for machine-to-machine; use device authorization for input-constrained devices; avoid the implicit and resource owner password credentials grants.
3. **Implement PKCE.** Generate a high-entropy code verifier per attempt; derive the code challenge with S256; send the challenge with the authorization request and the verifier with the token request.
4. **Validate the redirect URI.** Reject any redirect that does not exactly match a registered URI; never use wildcards, open redirects, or path-only matches.
5. **Authenticate the client.** For confidential clients, present client credentials at the token endpoint using the registered method (private_key_jwt, tls_client_auth, client_secret_basic, or client_secret_post) appropriate to the channel security.
6. **Request minimal scopes.** Request only the scopes necessary for the operation; reject broader scope grants when narrower scopes suffice; document the rationale for each scope requested.
7. **Validate tokens.** Verify the issuer, audience, expiration, signature, and nonce where applicable; reject tokens that do not validate or that have been replayed.
8. **Handle refresh securely.** Rotate refresh tokens on use when the server supports sender-constrained or rotating refresh tokens; bind refresh tokens to the client and the channel where supported.
9. **Store tokens safely.** Store access tokens in memory where possible; store refresh tokens in a secure keystore or trusted platform module; never store tokens in local storage, session storage, or cookies without `Secure`, `HttpOnly`, and `SameSite` protections.
10. **Handle logout and revocation.** Implement RP-initiated logout, front-channel and back-channel logout, and reactive token revocation on logout, password change, or privilege change.
11. **Monitor and audit.** Log authorization requests, token issuances, refreshes, and revocation events; detect anomalous token use (issuer mismatch, audience mismatch, replay, scope inflation).

## Escalation

Escalate to the IAM Lead and Application Security Lead when:
- a client cannot meet confidential client posture;
- the authorization server does not support PKCE or sender-constrained tokens;
- token theft, replay, or unauthorized issuance is suspected;
- a third-party integration requests broader scopes than operationally required.

## Evidence

- client registration record and metadata;
- authorization and token request logs;
- token validation and refresh audit trail;
- logout and revocation events;
- periodic integration review and scope justification.

## Completion Criteria

The OAuth 2.1 client integration is considered complete when:
- client registration is recorded and aligned with the application owner;
- the implemented flow is the strongest flow supported by the client and server;
- PKCE and exact redirect URI matching are enforced;
- tokens are stored and refreshed per policy;
- monitoring and revocation paths are operational.

## Exceptions

Document deviations with the approver, scope, expiration, compensating control, and review schedule. Reassess at every material change to the client or the authorization server.

## Related Documents

- [IETF OAuth 2.1 Authorization Framework](IETF_OAUTH_2_1_AUTHORIZATION_FRAMEWORK.md)
- [IETF RFC 9700 OAuth 2.0 Security Best Current Practice](IETF_RFC_9700_OAUTH_2_0_SECURITY_BCP.md)
- [OpenID Connect Core 1.0](OPENID_CONNECT_CORE_1_0.md)
- [FAPI 2.0 Security Profile](FAPI_2_0_SECURITY_PROFILE.md)
- [Token Storage Best Practices](TOKEN_STORAGE_BEST_PRACTICES.md)
