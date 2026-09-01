# Protecting Agent Authorization Requests with OAuth JAR

## Scope

An agent may initiate OAuth authorization for access to calendars, records, financial APIs, or other tools. Parameters sent through a browser can be modified, duplicated, logged, or confused across concurrent tasks. RFC 9101 defines JWT-Secured Authorization Request (JAR), which packages authorization parameters in a signed and optionally encrypted request object. JAR protects request integrity and authenticates the client that created the object when signatures and keys are correctly validated.

JAR does not authorize the eventual API operation, prevent excessive scopes, or prove that generated intent matches the user's intent. It protects an authorization request between client and authorization server. Pushed Authorization Requests can complement it by sending parameters directly to the authorization server and using a short request URI at the browser.

## Implementation workflow

Register client signing keys and supported algorithms with the authorization server. Prefer asymmetric signing so the authorization server can validate without holding a client signing secret. Define an algorithm allowlist and reject algorithm substitution. Establish key rotation, overlap, revocation, and issuer-to-key binding before enabling request objects.

Build authorization parameters from trusted application state after validating the agent's proposed operation. Include the response type, client identifier, redirect URI, requested scope or structured authorization details, state, nonce where applicable, and timing claims required by deployment policy. Sign the object and send it using the `request` parameter, or submit it through PAR and redirect with the resulting `request_uri`.

The authorization server validates JWT structure, signature, issuer and audience, client binding, expiration, not-before time if present, and parameter consistency. It must apply RFC 9101 rules when parameters occur both inside and outside the request object. The client binds callback processing to the initiating session and validates state and the authorization response independently.

## Controls

Use short request-object lifetimes and unique identifiers when replay detection is required. Protect signing keys with workload identity and restricted signing access. Never let the model supply redirect URIs, client IDs, key identifiers, algorithms, or arbitrary JWT claims. Keep a server-side transaction record linking the reviewed action, request-object hash, browser session, and expected callback.

Encrypt request objects only when confidentiality is required and all parties have a tested key-management profile; signing remains necessary for integrity in common deployments. Minimize personal and transaction data because request objects may pass through user agents or logs. PAR reduces exposure but does not justify including unnecessary data.

## Validation evidence

Test valid requests plus altered payload, altered signature, wrong issuer, wrong audience, expired and premature objects, unknown key, disallowed algorithm, mismatched client ID, changed redirect URI, replay, duplicate parameters, and callback state mismatch. Demonstrate that modifying one requested privilege after signing causes rejection. Verify key rotation with old, overlap, and revoked keys.

Retain registration metadata, algorithm policy, request-object construction tests, authorization-server validation results, PAR configuration, key lifecycle evidence, and redacted transaction traces. Monitor validation failures by bounded reason codes. Evidence must identify which RFC profile and server configuration were tested rather than claiming universal OAuth conformance.

## Failure handling

Reject invalid request objects before presenting consent. Do not recover by accepting unsigned browser parameters or weakening algorithm checks. On an unknown key, refresh trusted metadata through the controlled registration mechanism and retry only within a bounded policy; never fetch a key from an attacker-selected location.

If a signing key is compromised, revoke it, reject outstanding objects signed by it, rotate the client registration, and identify authorizations initiated during the exposure window. If transaction binding fails at callback, discard the response and require a fresh authorization rather than attaching it to the nearest active agent task.

## Canonical sources

- RFC 9101, JWT-Secured Authorization Request: https://www.rfc-editor.org/rfc/rfc9101
- RFC 9126, OAuth 2.0 Pushed Authorization Requests: https://www.rfc-editor.org/rfc/rfc9126
- RFC 8725, JSON Web Token Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
