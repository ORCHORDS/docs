# MCP OAuth Resource Indicators

## Purpose

OAuth access tokens should be issued for the resource the client actually intends to call. Resource Indicators for OAuth 2.0, standardized in RFC 8707, let clients identify that target resource explicitly during authorization and token requests.

## Why this matters for agents

Agent systems frequently connect to multiple MCP servers, gateways, or delegated resources. A token minted without a clear audience boundary can be more easily confused, replayed, or presented to the wrong service. Explicit resource indicators narrow that ambiguity.

## Practical controls

1. Include the canonical MCP resource URI in the OAuth `resource` parameter when the authorization profile requires it.
2. Keep the same resource identity consistent across authorization, token issuance, protected-resource metadata, and token validation.
3. Do not reuse a token for a different MCP server merely because the same authorization server issued it.
4. Validate the token audience or equivalent resource binding at the receiving resource server.
5. Reject unexpected resource identifiers instead of silently broadening authorization.
6. When multiple resources are involved, request only the resources actually needed for the operation.
7. Record resource-selection failures without storing access tokens or authorization codes.

## MCP context

MCP authorization guidance has used OAuth resource indicators to bind tokens to the intended MCP server. The 2026-07-28 release further hardened authorization and moved more request identity into explicit protocol metadata; that makes precise resource identity even more important at gateways and resource servers.

## Sources

- RFC Editor — RFC 8707, Resource Indicators for OAuth 2.0: https://www.rfc-editor.org/rfc/rfc8707.html
- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- Model Context Protocol — authorization specification background: https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization

## Scope note

Resource indicators do not replace normal token validation, issuer validation, least-privilege scope design, or application authorization.
