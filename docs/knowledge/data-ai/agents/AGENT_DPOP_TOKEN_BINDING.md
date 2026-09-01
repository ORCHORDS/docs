# Agent DPoP Token Binding

Agents run with credentials that outlive a single request, which makes their access tokens attractive theft targets. DPoP (Demonstrating Proof of Possession, RFC 9449) converts a bearer token into one that only works when presented alongside a fresh proof signed by a private key the agent holds. A stolen token string becomes useless without the key. This article walks the mechanics as they apply to agent workloads, the failure modes that catch teams during rollout, and how to demonstrate the binding actually holds. It complements the higher-level article on sender-constrained tokens by focusing on proof construction, validation order, and operational drift.

## Scope

Applies to agent clients obtaining OAuth 2.0 access tokens from an authorization server that supports DPoP, and to resource servers validating DPoP-bound tokens on agent API calls. Covers proof JWT construction, token-endpoint binding, per-request proofs, nonce handling, and replay checks. Does not cover mutual-TLS binding (an alternative sender-constraint), token exchange semantics, or choosing scopes, each of which interacts with DPoP but is governed separately.

## Workflow or implementation guidance

1. Provision one asymmetric key pair per agent workload instance in a protected store: OS keychain, TPM-backed store, KMS-held key, or a sealed volume with strict file permissions. The public key travels in proofs; the private key never does. One key per instance, never one shared key across a fleet, because a shared key collapses per-instance revocation.
2. Request tokens with a DPoP proof JWT in the `DPoP` header. The proof header carries the key's public JWK and a type value of `dpop+jwt`. Claims include `htu` (the HTTP target URI), `htm` (the method), `iat`, a unique `jti`, and for token requests the token being refreshed where applicable.
3. Expect the issued token to carry a confirmation method (`cnf`) claim binding it to your key's thumbprint. If the token comes back without `cnf`, you received a bearer token; do not send it with a DPoP header and call it bound. Treat the mismatch as a configuration error.
4. For every resource request, mint a fresh proof: new `jti`, current `iat`, the exact `htu` and `htm` of this call, and the `ath` claim containing the base64url SHA-256 hash of the access token. The `ath` binding is what stops an attacker pairing their own proof with your token.
5. Send the access token with the `DPoP` authorization scheme and the proof in the `DPoP` header. Build `htu` from the URI as the client sees it after trusted proxy normalization; mismatched proxy rewrites are the most common false-rejection cause.
6. Handle server nonces. A resource server may reply with a `DPoP-Nonce` challenge; the next proof must include that nonce as its `nonce` claim. Scope nonce acceptance to the specific server that issued it, and cap retry loops so a misbehaving server cannot pin the agent in a challenge cycle.
7. Rotate the key deliberately: generate a successor, request fresh tokens bound to it, let old tokens expire or revoke them, then retire the old key. Tokens do not migrate between keys.
8. On the resource server side, validate in fixed order: proof syntax and signature against the embedded JWK, `htm`/`htu` match, `iat` freshness window, `jti` not replayed, nonce correctness when required, `ath` equals the presented token's hash, and finally the token's `cnf` thumbprint equals the proof key's thumbprint. Only then proceed to ordinary scope and audience checks.

## Controls

- Non-exportable key storage enforced by deployment policy; a startup self-check verifies the key is readable for signing but not extractable where the platform supports the distinction.
- Replay detection store for `jti` values with a TTL matching the freshness window, size-bounded and partitioned so it cannot become a denial-of-service amplifier.
- Clock synchronization monitoring on both agent and resource server; DPoP freshness windows are tight enough that drift is a routine outage cause.
- Configuration assertions that fail the pipeline if an authorization server stops returning `cnf` on DPoP-flagged requests, or a resource server accepts bearer fallback for bound tokens.
- Key inventory tying each signing key to workload identity, creation, and rotation state, so incident responders can map a compromised key to blast radius fast.

## Validation evidence

- Positive path: a valid proof plus bound token succeeds, and the response includes the expected resource, proving the whole chain end to end.
- Negative matrix, each returning the correct error: reused `jti`, expired `iat`, wrong `htm`, wrong `htu`, proof signed by a different key than `cnf`, token without `cnf`, missing `ath`, `ath` computed over a different token, and a plain bearer presentation of a DPoP-bound token.
- Exfiltration drill: extract the access token from a captured request and replay it bare and with an attacker-generated proof; both must fail, demonstrating the theft scenario is covered.
- Operational evidence: nonce-challenge rates, freshness-window rejection rates, and clock-drift alerts across a representative deployment period, showing the controls are tuned rather than decorative.

## Failure modes and correction

- Proxy rewrites the visible URI so client-computed `htu` differs from the server's; rejections spike. Correction: pin the externally visible URI at the trusted proxy and derive `htu` from deployed configuration, not from the local socket target.
- Nonce cache is in-memory per pod behind a load balancer, so proofs bounce between pods that never saw the nonce. Correction: shared nonce store or sticky routing for the validation path, chosen deliberately and documented.
- A library upgrades and silently stops sending `ath`; token still validates at lenient servers. Correction: conformance test asserting the full claim set, run in CI against a reference validator.
- Compromised key suspicion. Correction: revoke tokens bound to that thumbprint at the authorization server where supported, rotate the key, and mine replay logs for `jti` anomalies in the exposure window.

## Limitations

DPoP binds possession, not intent: malware running inside the agent process signs valid proofs. Replay windows mean near-simultaneous interception can still race within the freshness interval, especially without server nonces. Validation adds a signature check per request and a replay lookup, which is a real cost at high throughput. Authorization servers and gateways must explicitly support DPoP; partial deployments leave bearer fallbacks that negate the guarantee for those routes. Finally, nonce mechanisms concentrate state on the server, trading client complexity for server availability risk.

## Canonical sources

- RFC 9449, OAuth 2.0 Demonstrating Proof of Possession (DPoP): https://www.rfc-editor.org/rfc/rfc9449
- RFC 6749, The OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- RFC 7636, Proof Key for Code Exchange by OAuth Public Clients (PKCE): https://www.rfc-editor.org/rfc/rfc7636
