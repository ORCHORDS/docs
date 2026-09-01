# Integrity-Protecting Agent Tool Calls with HTTP Message Signatures

## Scope

RFC 9421 defines HTTP Message Signatures, a mechanism for signing selected HTTP message components and derived values. Agent-to-tool traffic can cross gateways and service meshes where method, target, authority, content, or selected headers need end-to-end integrity and signer authentication. Message signatures can complement TLS when verification must survive intermediaries or be recorded at the application boundary.

A signature proves possession of a signing key over covered components. It does not establish that the agent was authorized, that the payload is safe, or that an intermediary preserved unsigned fields. Deployment profiles must specify exactly which components are covered, accepted algorithms, key discovery, time windows, and replay controls.

## Implementation workflow

Define a bilateral or ecosystem profile before implementation. For a state-changing JSON tool call, coverage commonly needs the method, target URI components relevant to routing, authority, content digest, content type, and a transaction or idempotency identifier. Use RFC 9530 Content-Digest to bind the body rather than inventing a digest header. Decide how proxy rewriting affects each covered component.

Assign each workload a signing identity and managed key. The signer creates `Signature-Input`, including a label, covered component identifiers, creation time, expiration where used, nonce where required, key identifier, and algorithm under the profile. It computes the signature base exactly as RFC 9421 specifies and sends the `Signature` field.

The tool endpoint parses structured fields, resolves the key only through trusted configuration, rebuilds the signature base from the received message, verifies the signature, enforces time and nonce policy, and then performs normal authentication and authorization. Verification should happen before parsing expensive bodies or invoking business logic, subject to safe streaming limits.

## Controls

Use explicit component allowlists and require a minimum covered set per operation class. Reject signatures that are cryptographically valid but omit a required method, target, or digest. Bind key identifiers to expected agent identities and permitted algorithms; never allow an arbitrary key URL supplied in the message. Separate keys by environment and signer role.

Set narrow clock windows, synchronize clocks, and use nonces or unique signed request identifiers for replay-sensitive actions. A replay cache must be bounded and scoped to signer identity. Preserve idempotency independently because rejecting exact replay does not prevent semantically duplicated requests with new signatures.

Treat intermediaries deliberately. If a gateway changes a covered value, either verify before transformation and create a new downstream signature with explicit identity, or choose stable derived components in the profile. Do not silently drop failed signatures and continue as an unsigned request.

## Validation evidence

Use RFC test vectors where available and cross-implementation tests for serialization. Negative tests should alter method, path, query, authority, body, digest, content type, creation time, nonce, key ID, signature parameters, and whitespace-sensitive structured-field serialization. Test duplicate fields, proxy normalization, chunked transfer, and multiple signature labels.

Evidence includes the profile, key-to-identity registry, algorithm policy, gateway transformation map, replay-cache configuration, clock monitoring, interoperability captures with payloads redacted, and authorization tests. Prove that a valid signature from an unauthorized signer is denied and that a permitted signer cannot modify a covered tool argument unnoticed.

## Failure handling

On missing required coverage, invalid signature, stale time, unknown trusted key, digest mismatch, or replay, reject before side effects and emit a bounded reason code. Do not reveal key-resolution internals. During verifier outages, state-changing operations should fail closed unless a documented alternative authenticated channel is independently verified.

If a signing key is compromised, disable the key, reject its pending signed requests, rotate credentials, and identify accepted messages in the exposure window. Reconcile their side effects using signed request IDs and business audit records. Update the profile if an intermediary transformation created ambiguous verification.

## Canonical sources

- RFC 9421, HTTP Message Signatures: https://www.rfc-editor.org/rfc/rfc9421
- RFC 9530, Digest Fields: https://www.rfc-editor.org/rfc/rfc9530
- RFC 8941, Structured Field Values for HTTP: https://www.rfc-editor.org/rfc/rfc8941
