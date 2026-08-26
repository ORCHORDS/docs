# Mobile Clients Need a Stable Service Boundary

**Issue:** Adding an installed mobile client exposes business logic that exists only inside server-rendered controllers, browser sessions, or presentation-specific response paths.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Lesson

Design business capabilities behind a stable, client-neutral service boundary before binding them to a web or mobile presentation. This does not require every server-rendered page to call a public HTTP API. It requires reusable domain operations, explicit authorization, and contracts that can evolve for independently released clients.

## Controls

- Keep domain rules and authorization outside templates, view controllers, and transport adapters.
- Define the mobile-facing HTTP contract with explicit schemas, errors, pagination, idempotency, and compatibility policy.
- Treat installed applications as public clients that cannot keep a distributed client secret.
- For OAuth authorization, use an external user-agent and authorization code with PKCE as required by RFC 8252.
- Separate browser-session behavior from native-app token handling; do not replace cookies with an undifferentiated API key or long-lived JWT.
- Support older client versions during an evidence-based upgrade window because deployed apps cannot be updated atomically with the server.
- Measure payload, round trips, retry safety, and degraded-network behavior for each client journey.

## Verification

- Exercise the same business invariant through web and mobile adapters and compare authorization and state transitions.
- Contract-test the oldest supported client against the current server.
- Attempt native authorization without PKCE, with an embedded user-agent, and with a copied client secret; assert rejection.
- Simulate retry, offline replay, schema evolution, and partial response handling.

## Gotchas

“API first” is not “publish every internal operation” and does not make the browser UI another network client by necessity. REST versus GraphQL is secondary to a stable domain boundary. Native apps require different authorization assumptions from confidential server clients.

## Official sources

- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [RFC 8252: OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252.html)
