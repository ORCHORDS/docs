# MCP Protected Resource Metadata Discovery

## Purpose

Remote MCP deployments that use OAuth need a trustworthy way for clients to discover which authorization server protects a resource. OAuth 2.0 Protected Resource Metadata, standardized in RFC 9728, provides that resource-side discovery document.

## Core model

A protected resource publishes metadata at an RFC 9728 well-known location. The metadata identifies the protected resource and can advertise authorization servers, supported scopes, token presentation methods, and other resource-specific authorization information.

For MCP deployments, keep resource discovery separate from authorization-server discovery. The resource metadata tells the client which authorization server or servers are valid for the MCP resource; authorization-server metadata then describes authorization and token endpoints.

## Practical controls

1. Publish protected-resource metadata from an authoritative HTTPS origin for the MCP resource.
2. Keep the `resource` identifier aligned with the canonical MCP resource URI used during OAuth authorization.
3. Validate advertised authorization-server issuers instead of accepting arbitrary issuer URLs supplied by an untrusted peer.
4. Treat `WWW-Authenticate` resource metadata hints as discovery input, not as proof that a token issuer is trusted.
5. Cross-check enumerable resource and authorization-server relationships where both sides publish them.
6. Cache metadata only with an explicit freshness policy and revalidate security-relevant changes.
7. Never log bearer tokens while troubleshooting metadata or scope discovery.

## Current protocol context

The 2026-07-28 MCP release strengthened authorization around client identity and issuer validation. Protected-resource discovery remains part of the underlying OAuth resource-server model and should be implemented using the standards-track RFC rather than proprietary discovery conventions.

## Sources

- RFC Editor — RFC 9728, OAuth 2.0 Protected Resource Metadata: https://www.rfc-editor.org/rfc/rfc9728.html
- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- Model Context Protocol — authorization specification background: https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization

## Scope note

This article describes protocol-level discovery. Authorization policy, identity-provider trust, token validation, and deployment-specific scope design remain separate security decisions.
