# IETF RFC 9728 Protected Resource Metadata Platform Governance

## Purpose

Govern the application of RFC 9728 (OAuth 2.0 Protected Resource Metadata) so that protected resources publish their authorization requirements — resource name, supported scopes and authorization servers, signing algorithms, and bearer token requirements — at a well-known URL, letting clients discover how to call an API without out-of-band configuration.

## Scope

Applies to every OAuth 2.0-protected API the studio operates and every client that consumes such APIs. Covers metadata publication, field accuracy, authorization server binding, and change management. Does not cover authorization server metadata (RFC 8414) or client registration.

## Workflow

1. Publish protected resource metadata per resource at the well-known location defined by RFC 9728, derived from the resource's URL.
2. Populate required metadata accurately: `resource` (the resource identifier), `resource_documentation`, and the authorization servers whose access tokens the resource accepts (`authorization_servers`).
3. Declare supported scopes in metadata where the resource enforces scope-based authorization; the published scope set must match the resource's actual enforcement, not its aspirations.
4. Bind resource to authorization server deliberately: adding an authorization server to `authorization_servers` extends token acceptance; the change requires the same review as an authentication trust change.
5. Clients consume metadata to configure token acquisition: authorization server selection, scopes, and audience; hard-coded authorization server URLs in clients are configuration drift and are flagged.
6. Treat metadata as versioned interface: adding fields or authorization servers is compatible; removing scopes or dropping an authorization server is breaking and requires a deprecation window and client notification.
7. Monitor the well-known endpoint and metadata content drift (published vs enforced) as production alerting conditions.

## Controls and evidence

- Metadata publication record per protected resource: well-known URL, resource identifier, publication date.
- Metadata accuracy check results: published scopes and authorization servers vs enforced configuration.
- Authorization server binding change records with review evidence.
- Drift and availability alerting configuration for the well-known endpoint.

## Validation

- Fetch well-known metadata for each protected resource and confirm `resource` matches the API's actual identifier.
- Compare published scopes against the resource's enforced scope checks; confirm zero drift.
- Attempt access with a token from an unauthorized server in a test and confirm rejection.

## Failure correction

- **Metadata drift (published ≠ enforced)** → republish from enforced configuration and fix the pipeline or manual edit that caused the drift.
- **Unauthorized authorization server accepted** → treat as an authentication vulnerability: remove the binding, audit token acceptance logs, and review how the binding was added.
- **Breaking metadata change without deprecation** → revert if possible; otherwise notify clients immediately and record the process failure.

## Limitations

- Metadata describes intended authorization behavior; enforcement bugs remain possible and need testing.
- The specification is recent (April 2025); client library support varies, and older clients may need configuration guidance.
- Multi-tenant resources with per-tenant authorization servers need a metadata strategy (per-tenant publication or a tenant-scoped identifier).

## Scope note

This article is part of the platforms leaf. Cross-reference: `IETF_RFC_8414_AUTHORIZATION_SERVER_METADATA_GOVERNANCE.md` if present, `IETF_RFC_7592_OAUTH_CLIENT_DYNAMIC_REGISTRATION_TEMPLATE_GOVERNANCE.md` (templates leaf), and `OPENAPI_3_1_SPECIFICATION_TEMPLATE_GOVERNANCE.md` (templates leaf).

## Canonical sources

- IETF RFC 9728 — OAuth 2.0 Protected Resource Metadata: https://datatracker.ietf.org/doc/html/rfc9728
- IETF RFC 8414 — OAuth 2.0 Authorization Server Metadata: https://datatracker.ietf.org/doc/html/rfc8414
- IETF RFC 6749 — The OAuth 2.0 Authorization Framework: https://datatracker.ietf.org/doc/html/rfc6749
- IETF RFC 6750 — OAuth 2.0 Authorization Framework: Bearer Token Usage: https://datatracker.ietf.org/doc/html/rfc6750
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
