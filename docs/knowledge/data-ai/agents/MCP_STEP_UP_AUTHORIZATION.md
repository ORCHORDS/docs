# MCP Step-Up Authorization

## Purpose

The Model Context Protocol authorization specification dated 2025-11-25 defines a runtime step-up authorization pattern for operations that require permissions beyond those in the client's current access token.

## Runtime insufficient-scope challenge

When an MCP client presents a valid token that lacks the permissions needed for an operation, the server should use an HTTP `403 Forbidden` response and a `WWW-Authenticate` challenge with `error="insufficient_scope"` and the scope information needed for the current request.

The challenge can also include the protected-resource metadata URI and a human-readable error description. Clients must not assume that the challenged scope set has a particular subset or superset relationship with the scopes advertised in protected-resource metadata.

## Client workflow

A reusable MCP client should:

1. Parse the `WWW-Authenticate` challenge rather than treating every 403 as an unrecoverable transport error.
2. Determine the scopes needed for the failed operation from the authoritative challenge.
3. Initiate re-authorization for an appropriately increased scope set when acting on behalf of a user.
4. Preserve already-needed permissions when constructing the new request where the authorization model requires them.
5. Obtain a new token for the same canonical MCP resource.
6. Retry the original operation only a limited number of times.
7. Treat repeated insufficient-scope failures for the same resource and operation as a permanent authorization failure rather than creating an authorization loop.

Clients using their own credentials may attempt step-up authorization or abort instead, depending on the deployment.

## Server controls

Servers should return enough scope information to satisfy the current operation without forcing clients through a series of one-scope-at-a-time failures. Scope challenges should be consistent and should not be used to trick a client into requesting unrelated privileges.

The server must continue to validate token audience, expiry, and authorization for the MCP server after step-up. A larger scope set does not waive normal access-token validation.

## Consent and least privilege

Step-up authorization supports incremental consent: clients can begin with the permissions needed for basic functionality and ask for additional authorization only when a protected operation requires it. User-facing clients should make the reason for the permission increase understandable before starting the new authorization flow.

## Source

- Model Context Protocol Specification 2025-11-25 — Authorization, Scope Challenge Handling and Step-Up Authorization Flow: https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization

## Scope note

This article tracks the published MCP protocol revision dated 2025-11-25. OAuth provider configuration, scope semantics, consent UI, and authorization policy remain deployment-specific.