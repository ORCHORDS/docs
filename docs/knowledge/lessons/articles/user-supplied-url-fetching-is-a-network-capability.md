# User-Supplied URL Fetching Is a Network Capability

**Issue:** A feature accepts a URL for image import, webhooks, previews, SSO metadata, or another remote fetch without treating that input as control over where the server can connect.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API7:2023 describes SSRF as the server fetching a remote resource from a user-supplied URL without sufficient validation. The dangerous capability is not merely URL parsing; it is allowing client input to steer a server-side network request into locations the client could not reach directly.

## Engineering rule

- Isolate remote-resource fetching from sensitive internal networks where architecture allows it.
- Allowlist expected origins, schemes, ports, or media types whenever the business function has a bounded destination set.
- Use a maintained URL parser and validate client-supplied URL input before connection.
- Apply network-layer outbound restrictions as defense in depth.
- Treat webhook test requests and URL-preview features as SSRF-capable surfaces.

## Verification

- Attempt requests to loopback, internal-address, metadata-service, and otherwise disallowed destinations using safe test fixtures.
- Test alternate URL forms and parsing edge cases supported by the client stack.
- Confirm rejected targets never result in an outbound connection.

## Official sources

- OWASP API7:2023 Server Side Request Forgery: https://owasp.org/API-Security/editions/2023/en/0xa7-server-side-request-forgery/
- OWASP Server-Side Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
