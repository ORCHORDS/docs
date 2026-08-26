# backend-for-frontend-bff-pattern

**Issue:** BFF pattern — per-client backend
**Date:** 2026-08-09
**Status:** documented

## Symptom
Web app needs 3 endpoints aggregated. Mobile
needs 2 different endpoints. You write one API
that returns both. Mobile downloads 70% wasted
data. You need BFF.

## Root cause
**One API ≠ all clients.** Per-client BFF.

**Source:** Microsoft + Sam Newman 2026.

## The "BFF" concept

BFF (Backend for Frontend):
- **Per client:** Web, mobile, partner
- **Aggregation:** Compose downstream
- **Shaping:** Trim to need
- **Owned by:** Client team
- **Use:** Diverse clients

The BFF is per client.

## The "PKCE vs BFF" pattern

For auth:
- **PKCE:** Code in transit
- **BFF:** Token at rest
- **For high-risk SPA:** BFF
- **Method:** Confidential client + cookies
- **Why:** Safer

The BFF is the boundary.

## The "BFF + API gateway" pattern

For layered:
- **Gateway:** North-south (TLS, rate)
- **BFF:** South (client-specific)
- **Coexist:** Yes
- **Why:** Different concerns

The layered is both.

## The "GraphQL BFF" pattern

For variable:
- **When:** Client has variable data
- **Schema:** Per client team
- **Colocation:** With client
- **Use:** Greenfield
- **Why:** Standard

The GraphQL is a BFF.

## The "BFF as proxy" anti-pattern

For passthrough:
- **Issue:** Forwards tokens
- **Fix:** Token stays in BFF
- **Why:** Defeats purpose

The token is server-side.

## The "one BFF all clients" anti-pattern

For shared:
- **Issue:** Lowest common denom
- **Fix:** Per client
- **Why:** Diverged needs

The BFF is per client.

## The "logic in BFF" anti-pattern

For business:
- **Issue:** Domain rules in BFF
- **Fix:** In microservices
- **Why:** Duplication

The logic is downstream.

## The "BFF checklist" pattern

For checklist:
- [ ] One per client
- [ ] Confidential OAuth
- [ ] Session cookies
- [ ] Aggregate + shape
- [ ] Owned by client team
- [ ] Independent deploy
- [ ] Cache key versioned
- [ ] No business logic
- [ ] No long-lived flags

The checklist is 9.

## Verification
- **Test:** Per client
- **Test:** Token in BFF
- **Test:** Aggregated
- **Audit:** Per release

## Gotchas
- **The "proxy" anti-pattern.** Token stays.
- **The "shared" anti-pattern.** Per client.
- **The "logic" anti-pattern.** Downstream.

## Related
- `patterns/api-gateway-comparison-2026.md`
- `patterns/api-design-best-practices.md`
- `patterns/caching-strategies-detail.md`
- `security/jwt-best-practices.md`
- Microsoft: https://learn.microsoft.com/en-us/azure/architecture/patterns/backends-for-frontends
- Auth0: https://auth0.com/blog/things-developers-get-wrong-about-the-backend-for-frontend-pattern/
- Sam Newman: https://samnewman.io/patterns/architectural/bff/
