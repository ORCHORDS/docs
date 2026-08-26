# OAuth token exchange: delegation, impersonation, and audience narrowing

**Category:** Security
**Author:** ORCHORDS
**Primary source:** [RFC 8693: OAuth 2.0 Token Exchange](https://datatracker.ietf.org/doc/html/rfc8693)

## Problem

A backend that forwards an incoming access token to another service gives the downstream service more authority and less context than it needs. Token exchange can narrow a credential for a target service, but only if delegation and impersonation are explicit policy choices.

## Practice

- Validate the subject token and authenticate the exchanging client before issuing any replacement token.
- Allow exchanges only for registered resources, audiences, scopes, and token types; reject client-chosen arbitrary targets.
- Issue the smallest target-specific scope and short expiry. Never make exchange a way to enlarge authority.
- Decide whether the result represents delegation (actor remains visible) or impersonation (actor is not visible); record that decision in policy and audit events.
- Preserve the actor chain where delegation is required, and make downstream authorization evaluate both subject and actor when appropriate.
- Log only safe token metadata such as issuer, client, target audience, exchange outcome, and correlation ID—never token values.

## Verification

1. Exchange a valid token for an allowed target and confirm the result cannot call another resource.
2. Attempt an exchange to an unregistered audience or broader scope; it must fail.
3. Attempt an exchange with an unauthorized client or expired token; it must fail.
4. Inspect an auditable delegated request and confirm the subject and acting service are distinguishable.

## Failure modes

- A generic exchange endpoint becomes a privilege-escalation bridge between services.
- Delegation is implemented as silent impersonation, destroying accountability.
- A downstream service accepts the exchanged token without validating issuer, audience, expiry, and applicable actor context.

## Related

- [RFC 8693](https://datatracker.ietf.org/doc/html/rfc8693)
