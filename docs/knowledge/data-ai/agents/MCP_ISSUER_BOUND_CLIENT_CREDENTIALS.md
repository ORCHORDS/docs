# MCP Issuer-Bound Client Credentials

## Purpose

The MCP 2026-07-28 authorization hardening requires OAuth client credentials to remain bound to the authorization-server issuer that minted or registered them. A client credential created for one issuer must not be silently reused with another authorization server.

## Why the boundary matters

OAuth deployments may discover or interact with multiple authorization servers. Reusing a client identifier or secret across issuers can blur trust boundaries and create redirect, credential-confusion, or cross-issuer impersonation risks.

## Practical controls

1. Key stored client credentials by authorization-server issuer, not only by MCP server hostname or client application name.
2. Never send a client secret, assertion, or other issuer-specific credential to a different authorization server.
3. Re-run the appropriate client metadata or registration process when the trusted issuer changes.
4. Validate the `iss` value on authorization responses where the profile requires RFC 9207 issuer identification.
5. Keep redirect URIs and client metadata aligned with the credential set associated with that issuer.
6. In multi-issuer deployments, make credential selection deterministic and fail closed when issuer identity is ambiguous.
7. Avoid logging client secrets or credential-bearing assertions while diagnosing issuer-selection failures.

## Current MCP context

The MCP 2026-07-28 release explicitly states that client credentials are bound to the issuer that minted them and cannot be reused across authorization servers. The same release moves the protocol away from Dynamic Client Registration toward client metadata documents while retaining older behavior only for compatibility during migration.

## Sources

- Model Context Protocol — 2026-07-28 specification release, Authorization section: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- Model Context Protocol — 2026-07-28 release candidate, Authorization Hardening: https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/

## Scope note

Issuer binding does not replace normal client authentication, redirect-URI validation, PKCE, token validation, resource indicators, or least-privilege authorization.
