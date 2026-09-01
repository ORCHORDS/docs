# Fine-Grained Agent Authorization Requests with OAuth RAR

## Scope

OAuth scopes are often too coarse to describe a consequential agent action. RFC 9396, Rich Authorization Requests (RAR), lets a client convey structured `authorization_details` describing requested access. It can express transaction-specific constraints while leaving the authorization server responsible for policy and consent. RAR does not standardize every domain's detail type; ecosystems must define and govern their schemas.

For agents, generated intent is not authorization. The application converts a reviewed action into a validated authorization detail, obtains an authorization result, and binds execution to that result. This is distinct from general tool permission scopes because it addresses structured, transaction-level OAuth requests.

## Implementation workflow

Define a registered or ecosystem-governed authorization-detail type for the resource domain. Specify required and optional fields, semantics, canonical encoding if signatures or hashes are used, privacy considerations, and how the resource server maps details to operations. Fields might constrain account, action, amount ceiling, beneficiary, time window, or document set, but they must reflect the real API rather than model language.

Construct details from trusted application state and explicitly confirmed user choices. Validate against a strict schema, reject unknown security-relevant fields, and request the least authority needed. Send details through the authorization request using a protected method suitable for the deployment. The authorization server authenticates the user and client, evaluates policy, and may narrow or reject the request.

Bind the issued access token to granted authorization details in the manner supported by the authorization server and resource server. At execution, compare the proposed tool call with the granted details; do not assume the original request was granted unchanged. Couple this with token audience validation and sender constraint where available.

## Controls

Keep a deterministic mapping between user-visible review and structured fields. Display resource, action, constraints, and consequences from validated data, not an untrusted agent summary. Changes after approval require a new authorization decision. Prevent the model from choosing the authorization-detail `type` or inserting arbitrary extension fields without application validation.

Authorization servers should reject unsupported types and conflicting combinations. Resource servers must enforce the details, not merely scopes. Avoid packing unnecessary personal or transaction data into requests, browser history, logs, or tokens. Prefer pushed authorization requests when confidentiality, integrity, or request size warrants it, following the server's supported standards.

## Validation evidence

Maintain schema versions, type governance decisions, client mapping tests, authorization-server policy tests, and resource enforcement tests. Negative cases include altered amount, different resource, expired time window, unknown type, omitted required field, duplicate or conflicting details, grant narrowing, token substitution, and replay to another resource server.

An end-to-end test should capture the reviewed structured action, authorization request, granted constraints, and actual API operation with sensitive values redacted. Prove that a one-field mutation after approval is denied. Verify accessibility and clarity of the review interface with representative users; cryptographically correct requests can still produce invalid consent if the action is obscured.

## Failure handling

If details are invalid or unsupported, stop before authorization and explain which application capability cannot proceed without exposing raw server diagnostics. If the server narrows authority, either adapt execution strictly within the grant and obtain renewed user confirmation when meaning changes, or abort. Never fall back automatically to a broad scope.

On mismatch at the resource server, deny the action, invalidate the pending execution attempt, and emit a bounded audit event. If schema semantics were ambiguous, suspend that detail type, identify grants issued under affected versions, and resolve outstanding actions before re-enabling it.

## Canonical sources

- RFC 9396, OAuth 2.0 Rich Authorization Requests: https://www.rfc-editor.org/rfc/rfc9396
- RFC 9126, OAuth 2.0 Pushed Authorization Requests: https://www.rfc-editor.org/rfc/rfc9126
- RFC 8707, Resource Indicators for OAuth 2.0: https://www.rfc-editor.org/rfc/rfc8707
