# OAuth 2.0/2.1 Integration Playbook

## Purpose

Stand up a new OAuth 2.0/2.1 client integration against an Authorization Server (AS) end-to-end: client registration, scopes, token storage, refresh rotation, and on-call runbook. The playbook avoids the deprecated patterns (Implicit, ROPC) and enforces the security BCP (RFC 9700).

## Audience

Platform engineers, API gateway operators, application owners.

## Pre-conditions

1. The AS supports OAuth 2.0 (RFC 6749) or OAuth 2.1 (draft-ietf-oauth-v2-1).
2. The AS supports PKCE (RFC 7636) with `S256`.
3. The AS supports RFC 9207 `iss` parameter.
4. The reference card for the protocol is current: `OAUTH_2_1_VERSION_GOVERNANCE.md`.
5. The AS supports exact redirect URI matching.

## Procedure

### 1. Client registration

1. Register the client with the AS using one of:
   - Dynamic client registration (RFC 7591) for automated registration.
   - Manual registration via AS portal for human-controlled registrations.
2. Choose client type:
   - `public` for SPAs and native apps (uses PKCE; never `client_secret`).
   - `confidential` for backend services.
3. Choose client authentication method:
   - `none` for public clients (PKCE only).
   - `client_secret_basic` or `client_secret_post` for confidential clients (legacy).
   - `private_key_jwt` for FAPI 2.0 / high-security.
   - `tls_client_auth` for service-to-service / FAPI 2.0.
4. Pin redirect URIs to exact strings. No prefix matching. No path parameters.
5. Configure scopes based on the principle of least privilege.

### 2. Authorization request

1. Generate PKCE: `code_verifier` = 43-128 char base64url; `code_challenge` = base64url(SHA-256(code_verifier)).
2. Generate `state` parameter: high-entropy random string, ≤ 256 bytes, base64url-encoded.
3. Generate `nonce` parameter: high-entropy random string, base64url-encoded. Required for OIDC ID Token.
4. Set `response_type=code`.
5. Set `code_challenge_method=S256`.
6. Include `iss` parameter (RFC 9207): the issuer URL.
7. If FAPI 2.0: use JAR (RFC 9101) to sign the request object; use PAR (RFC 9126) for pushed authorization.

### 3. Token exchange

1. Send the `code` + `code_verifier` to the token endpoint.
2. Authenticate the client per the registered method.
3. Validate the response: `access_token`, `id_token` (OIDC), `refresh_token`, `token_type=Bearer`, `expires_in`, `scope`.
4. For OIDC: validate the ID Token per `OIDC_VERSION_GOVERNANCE.md` (issuer, audience, signature, exp, iat, nonce).
5. Store the access token in memory (preferred) or in a sealed storage mechanism.
6. Store the refresh token in a vault per `SECRET_ROTATION_PLAYBOOK.md`.

### 4. Token use

1. Send `Authorization: Bearer <access_token>` on every API request.
2. Add `DPoP` header (RFC 9449) for sender-constrained tokens (recommended for FAPI 2.0).
3. Validate response: handle 401 with `WWW-Authenticate` header per RFC 6750.
4. Handle 403 with `error=insufficient_scope` per RFC 6750.

### 5. Refresh rotation

1. When access token is within 60 seconds of expiry, request a new token using the refresh token.
2. Use the new access token and the new refresh token.
3. If the AS returns `error=invalid_grant`, the refresh token is invalid: re-initiate the authorization flow.
4. Refresh token reuse detection: if a previously used refresh token is presented, the AS invalidates the entire refresh-token family. Treat as an incident.

### 6. Logout / revocation

1. Send `end_session_endpoint` request (OIDC) for browser-based logout.
2. Send `revoke` request (RFC 7009) for the refresh token (and access token, if applicable).
3. Clear local token storage.
4. Validate the response (200 OK).

### 7. Observability

- Token request rate (per client, per AS).
- Token issuance latency.
- Token refresh rate.
- Token revocation rate.
- `invalid_grant` rate.
- 401 / 403 response rate (per scope, per client).

Audit log captures: client_id, subject (if OIDC), scope, audience, issuer, token id (jti), timestamp, source IP.

### 8. Launch validation

1. Run integration test suite covering happy path, token expiry, refresh rotation, revocation, error handling.
2. Confirm PKCE flow end-to-end.
3. Confirm redirect URI exact match (test that a wrong URI is rejected).
4. Confirm ID Token signature validation.
5. Confirm refresh token rotation works.
6. Confirm RFC 7009 revocation works.
7. Confirm 401 / 403 error handling per RFC 6750.

## Rollback

Rollback decisions:

- p99 token issuance latency > 2x baseline → revert.
- 401 / 403 rate > 5% for 5 minutes → revert.
- Refresh token family invalidation rate > 0 → treat as incident.

Rollback procedure:

1. Revert the integration to the last-known-good configuration.
2. Page the on-call owner.
3. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## References

- `OAUTH_2_1_VERSION_GOVERNANCE.md`
- `OIDC_VERSION_GOVERNANCE.md`
- `SECRET_ROTATION_PLAYBOOK.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- RFC 6749: `https://www.rfc-editor.org/rfc/rfc6749`
- RFC 9700 (OAuth Security BCP): `https://www.rfc-editor.org/rfc/rfc9700`
- RFC 7636 (PKCE): `https://www.rfc-editor.org/rfc/rfc7636`
- RFC 9449 (DPoP): `https://www.rfc-editor.org/rfc/rfc9449`
