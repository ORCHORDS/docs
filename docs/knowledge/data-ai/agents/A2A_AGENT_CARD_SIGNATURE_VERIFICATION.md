# A2A Agent Card Signature Verification

## Purpose

A2A v1.0 Agent Cards can carry signatures so clients can verify that discovery metadata has not been altered. Signature support strengthens discovery trust but does not replace transport security or authorization.

## Controls

1. Retrieve public Agent Cards over authenticated HTTPS.
2. When an Agent Card signature is present, validate it according to the A2A AgentCardSignature/JWS representation before trusting signed metadata.
3. Bind trusted verification keys to the expected agent identity or trust domain rather than accepting arbitrary signing keys from the same untrusted document.
4. Reject malformed, unverifiable, expired, or policy-disallowed signatures.
5. Revalidate after card refreshes and capability/version changes.
6. Do not place credentials or other secrets in public Agent Cards merely because the document can be signed.

## Source

- A2A Protocol v1.0 specification, AgentCard and AgentCardSignature: https://a2a-protocol.org/dev/specification/

## Scope note

Key distribution, certificate policy, rotation, revocation, and trust-anchor management are deployment responsibilities outside the core protocol.
