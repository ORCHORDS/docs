# A2A Multi-Tenancy and Routing

## Purpose

A2A v1.0 supports multi-tenant and multi-agent deployments where multiple agents may share infrastructure. Routing can use distinct URLs, authenticated identity, or the optional `tenant` value advertised by an Agent Interface.

## Guidance

1. Treat `tenant` as an opaque routing value, not as proof of identity or authorization.
2. When an Agent Interface advertises a tenant value, echo that value consistently on requests using that interface.
3. Keep authentication and authorization scoped to the selected tenant/agent independently of routing.
4. Prevent a caller from changing routing values to cross tenant boundaries without authorization.
5. Prefer Agent Card-discovered interface metadata over guessed route conventions.
6. Keep logs and metrics tenant-aware without exposing one tenant's sensitive data to another.
7. Test URL-, credential-, and body-based routing combinations for confused-deputy and cross-tenant failures.

## Sources

- A2A Protocol — Multi-Tenancy and Multi-Agent Routing: https://a2a-protocol.org/latest/topics/multi-tenancy/
- A2A Protocol — What's New in v1.0: https://a2a-protocol.org/latest/whats-new-v1/

## Scope note

A2A defines routing mechanisms but does not prescribe a tenant-isolation architecture. Isolation and authorization are operator responsibilities.
