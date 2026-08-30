# A2A Authenticated Extended Agent Cards

## Purpose

A2A v1.0 permits an agent to expose a richer Agent Card to authenticated clients when `supportsAuthenticatedExtendedCard` is declared. This allows sensitive capability metadata to remain outside the public discovery document.

## Controls

1. Publish only the minimum discovery information required in the public Agent Card.
2. Require authentication for the extended-card endpoint and return authorization failures without leaking protected details.
3. Verify that the capability is actually implemented before advertising support.
4. Scope extended metadata to the authenticated principal where capabilities or skills differ by tenant, customer, or role.
5. Cache authenticated cards only for an appropriate authenticated session or validity period and refresh them when the card version changes.
6. Never include long-lived credentials or unrelated secrets in either public or extended cards.

## Source

- A2A Protocol v1.0 specification, authenticated extended Agent Card support: https://a2a-protocol.org/dev/specification/

## Scope note

The extended card is an authorization-controlled metadata surface, not a credential delivery mechanism.
