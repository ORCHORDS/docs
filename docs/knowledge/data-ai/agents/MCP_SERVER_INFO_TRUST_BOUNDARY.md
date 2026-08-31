# MCP Server Information Trust Boundary

## Purpose

MCP 2026-07-28 allows server metadata to be surfaced to clients, but self-reported identity and version information is not an authentication mechanism.

## Trust boundary

Current MCP SDK guidance treats `serverInfo` and `clientInfo` as self-reported metadata intended for display, logging, and debugging. Applications should not use these values as the basis for authorization, routing trust, credential release, policy bypasses, or other security decisions.

Malformed self-reported metadata can be treated as absent. A client should therefore remain functional when optional informational metadata is missing or invalid.

## Implementation guidance

1. Authenticate the remote endpoint using the transport and authorization mechanisms appropriate to the deployment; do not equate a claimed server name with authenticated identity.
2. Treat server name, title, and version strings as untrusted display data.
3. Escape or otherwise safely render metadata before placing it in HTML, logs, terminals, or dashboards.
4. Do not release credentials or privileged tools because a peer claims a familiar product name or version.
5. Base compatibility behavior on negotiated protocol capabilities and versions rather than branding strings.
6. Keep security policy keyed to verified endpoints, issuers, credentials, or configured trust anchors.
7. Make missing metadata non-fatal unless an application-specific contract explicitly requires it.

## 2026-07-28 compatibility note

The TypeScript SDK migration guidance notes that `DiscoverResult` no longer exposes `serverInfo` as a normal member; applications needing the value use the SDK's server-version/metadata access path. This reinforces that informational metadata is separate from protocol capability and authorization decisions.

## Sources

- MCP TypeScript SDK — supporting protocol revision 2026-07-28: https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28
- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/

## Scope note

This guidance is about self-reported MCP metadata. It does not replace TLS validation, OAuth/OIDC validation, protected-resource metadata, issuer checks, or application-specific authorization.