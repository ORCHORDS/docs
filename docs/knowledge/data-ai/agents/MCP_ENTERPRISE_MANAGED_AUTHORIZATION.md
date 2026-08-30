# MCP Enterprise-Managed Authorization

## Purpose

Enterprise-Managed Authorization (EMA) is a stable MCP extension for centrally managed access to MCP servers through an organization's identity provider. It reduces repeated per-application authorization while keeping access policy under enterprise administration.

## Core model

EMA uses the extension identifier `io.modelcontextprotocol/enterprise-managed-authorization`. An organization can centrally provision which MCP resources a workforce identity may access, while MCP authorization servers validate enterprise-issued identity assertions and map their claims to local permissions.

## Practical controls

1. Treat EMA as an opt-in extension, not a default capability assumed for every client or server.
2. Validate enterprise identity assertions cryptographically, including issuer, audience, expiration, and signature.
3. Map enterprise claims to least-privilege MCP permissions rather than granting broad access from organization membership alone.
4. Keep account-linking rules explicit when enterprise identity must be associated with an application account.
5. Separate enterprise policy administration from MCP resource-server token validation.
6. Record authorization decisions without logging bearer tokens, identity assertions, or sensitive claim values unnecessarily.
7. Test revocation and policy-change propagation so centrally removed access does not persist silently.

## Interoperability note

Support varies by MCP client and deployment. EMA is an extension and must be negotiated or otherwise supported by the participating components before it can be relied on.

## Sources

- Model Context Protocol — Enterprise-Managed Authorization: https://modelcontextprotocol.io/extensions/auth/enterprise-managed-authorization
- Model Context Protocol Blog — Enterprise-Managed Authorization: Zero-touch OAuth for MCP: https://blog.modelcontextprotocol.io/posts/enterprise-managed-auth/
- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/

## Scope note

EMA does not eliminate the need for resource-server authorization, token validation, tenant isolation, or application-specific access policy.
