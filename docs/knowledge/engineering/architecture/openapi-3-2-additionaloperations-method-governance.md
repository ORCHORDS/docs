# OpenAPI 3.2 additionalOperations method governance

**Issue:** OpenAPI 3.2 can describe HTTP methods beyond the Path Item Object’s fixed method fields through `additionalOperations`. Tooling that assumes only the older fixed set may silently omit validation, routing, documentation, or security for those operations.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin the document to OpenAPI 3.2 and inventory parsers, generators, gateways, documentation renderers, and policy scanners before using `additionalOperations`.
- Preserve method names exactly as required by the specification and reject a key that collides case-insensitively with a fixed Path Item operation.
- Apply operation identifiers, security requirements, parameters, request bodies, responses, callbacks, and policy linting to additional operations exactly as for fixed operations.
- Maintain an explicit allowlist of HTTP methods supported by the production proxy and origin.
- Treat `QUERY` as the OpenAPI 3.2 fixed `query` field rather than duplicating it in `additionalOperations`.
- Fail closed when a deployment tool cannot understand an operation.

## Implementation and tests

Add contract fixtures containing one supported extension method, one unsupported method, a case collision, and the fixed `query` operation. Round-trip them through every tool in the release path. Compare the resulting route, authorization, validation, SDK, and documentation inventories with the source operation inventory.

Send integration requests through the actual CDN, proxy, load balancer, framework, and origin. Assert method preservation, body handling, cache behavior, CORS policy, authentication, response validation, and rejection of disallowed methods.

## Gotchas and applicability

Describing a method does not make intermediaries support or forward it. Generated clients may have no idiomatic API for an extension method. HTTP method semantics and registration requirements still apply independently of OpenAPI.

OpenAPI 3.2 support may lag across tools; verify the exact installed versions rather than relying on a product-level compatibility claim.

## Official sources

- [OpenAPI Specification 3.2.0: Path Item Object](https://spec.openapis.org/oas/v3.2.0.html#path-item-object)
- [IANA HTTP Method Registry](https://www.iana.org/assignments/http-methods/http-methods.xhtml)
