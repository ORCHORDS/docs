# HTTP QUERY Method Safe-Body Contract

**Issue:** Complex read operations placed in POST bodies lose safe-method semantics, while oversized GET targets encounter URL and cache limitations. QUERY defines a safe, idempotent request with body content.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Use QUERY only where clients, servers, gateways, and caches explicitly support it.
- Define request content type, canonicalization, validation, and response cache policy.
- Keep QUERY side-effect free and apply authorization exactly as for equivalent reads.
- Provide a compatibility path for intermediaries that do not recognize the method.

## Verification

- Pass QUERY through every proxy, WAF, CDN, framework, and observability layer.
- Verify retries and cache revalidation do not mutate state.
- Test content negotiation, body limits, malformed queries, and fallback behavior.

## Gotchas

- A method being safe does not make the query inexpensive or non-sensitive.
- Unknown-method handling can differ across intermediaries.

## Official sources

- https://www.rfc-editor.org/rfc/rfc10008.html
