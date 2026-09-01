# Sender-Constrained Agent Access Tokens with OAuth DPoP

## Scope

Agents frequently call APIs with OAuth access tokens. A bearer token can be replayed by anyone who obtains it. RFC 9449 defines Demonstrating Proof of Possession (DPoP), an application-layer mechanism that binds a token to a public key and requires a signed proof for token and resource requests. DPoP reduces replay value but does not repair excessive scopes, compromised agent logic, or authorization-server mistakes.

This article applies DPoP to agent workloads that can protect a private key and generate a proof per request. Mutual TLS is another sender-constraining option and may be preferable in managed service environments. The authorization server and resource server must explicitly support the selected mechanism.

## Implementation workflow

Generate a dedicated asymmetric key in the agent workload's protected keystore. Avoid sharing one key across unrelated tenants or environments. The client sends a DPoP proof JWT to the token endpoint; the proof includes the public JWK in its header and claims including the target URI (`htu`), HTTP method (`htm`), issued-at time (`iat`), and unique identifier (`jti`). The authorization server validates the proof and issues a token bound through the confirmation claim.

For each resource request, create a new proof for the exact target URI and method. Include the access-token hash (`ath`) as RFC 9449 requires for protected-resource use. Send the token using the DPoP authorization scheme and the proof in the DPoP header. The resource server validates signature, key binding, method, URI, freshness, `jti`, and token hash before ordinary scope and resource authorization.

Support server nonces when required. On a nonce challenge, accept a nonce only from the relevant authorization or resource server, create a fresh proof, and retry within a strict budget. Keep token audience/resource selection explicit; DPoP binding is not a substitute for resource indicators or audience validation.

## Controls

Store private keys non-exportably where practical and restrict signing operations to the calling workload. Rotate keys through a controlled token reacquisition process; tokens bound to the old key cannot simply be used with a new one. Keep access tokens short lived and narrowly scoped. Never delegate a bound token without a deliberate delegation protocol and key ownership model.

Resource servers need replay detection appropriate to their risk, using `jti`, key thumbprint, and validity window while preventing the replay cache from becoming an unbounded denial-of-service target. Normalize the target URI only as specified; mismatched proxy views can cause false rejection or unsafe comparison. Establish the externally visible URI securely at trusted proxies.

## Validation evidence

Test a valid request and negative cases: wrong key, reused proof, stale `iat`, wrong method, wrong URI, altered token, missing `ath`, token issued as bearer, malformed JWK, and nonce replay. Demonstrate that a copied access token fails without the private key. Also demonstrate that a valid DPoP request with insufficient scope still fails, proving possession does not bypass authorization.

Evidence includes authorization-server metadata, client key lifecycle records, token confirmation claims with tokens redacted, resource-server validation configuration, replay-cache limits, clock synchronization monitoring, and test results. Trace proof failures by reason without logging proofs or tokens in full.

## Failure handling

On proof validation failure, deny the resource request and return only standards-appropriate error information. Do not silently downgrade to bearer authentication. Limit nonce retries and stop loops when clocks, proxy URI construction, or server state are inconsistent. If the private key may be compromised, revoke or expire bound tokens, disable signing, rotate the key, and reauthorize.

If replay detection storage is unavailable, follow a documented fail-closed or risk-limited degradation policy based on operation sensitivity; do not claim replay resistance while checks are bypassed. Reconcile any side effects from suspected replay using idempotency and audit records.

## Canonical sources

- RFC 9449, OAuth 2.0 Demonstrating Proof of Possession: https://www.rfc-editor.org/rfc/rfc9449
- RFC 8705, OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens: https://www.rfc-editor.org/rfc/rfc8705
- RFC 8707, Resource Indicators for OAuth 2.0: https://www.rfc-editor.org/rfc/rfc8707
