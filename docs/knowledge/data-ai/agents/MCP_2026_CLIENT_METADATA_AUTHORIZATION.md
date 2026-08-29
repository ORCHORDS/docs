# MCP 2026 Client Metadata and Authorization Hardening

## Purpose

The Model Context Protocol (MCP) 2026-07-28 specification introduced authorization changes intended to make client identity and routing easier to validate in modern deployments. The release moves away from Dynamic Client Registration as the default direction and toward client metadata documents, while also adding stronger issuer-validation expectations.

## Client metadata documents

A client metadata document gives an authorization server a stable, fetchable description of the client rather than requiring every client to register dynamically at runtime. Treat the document as security-sensitive metadata:

- fetch it only from an expected HTTPS location;
- validate the document against the MCP authorization requirements;
- do not treat arbitrary client-supplied URLs as trusted metadata sources;
- cache only according to explicit policy and revalidate when identity-relevant metadata changes.

## Issuer validation

The 2026 authorization changes include issuer validation aligned with RFC 9207. Clients should verify that the authorization response is associated with the issuer they intended to use. This reduces ambiguity when multiple authorization servers or discovery paths are in play.

## Gateway and routing implications

The 2026 MCP protocol also places method and tool names in HTTP headers so gateways can make routing and authorization decisions without reconstructing a long-lived session. Header visibility does not make a request trustworthy by itself: gateways must still authenticate the caller, validate the target server and method, and enforce least privilege.

## Practical controls

1. Pin or constrain trusted authorization-server origins.
2. Validate issuer identity on authorization responses.
3. Treat client metadata documents as signed-or-origin-trusted configuration, not arbitrary user input.
4. Keep redirect URIs and client identity metadata narrowly scoped.
5. Authorize MCP methods and tools independently from transport acceptance.
6. Log authorization-server, client, method, and tool identity for security review without recording bearer tokens or secrets.
7. Test migration behavior when moving older deployments away from dynamic registration assumptions.

## Sources

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- Model Context Protocol — official specification: https://modelcontextprotocol.io/specification/2026-07-28

## Scope note

This article summarizes protocol-level authorization changes. OAuth deployment choices, identity-provider configuration, and jurisdiction-specific access requirements remain environment-specific.
