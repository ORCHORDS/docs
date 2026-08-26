# Fetch cross-origin redirect Authorization stripping

**Issue:** The Fetch Standard removes the `Authorization` header when an HTTP redirect crosses to a different origin. A client that expects its bearer token to follow the redirect sees an unexplained 401 at the destination; a workaround that blindly re-adds the token can instead leak credentials to an attacker-controlled origin.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Send authenticated requests directly to the canonical API origin rather than relying on cross-origin redirects.
- Keep redirects same-origin when the same authorization credential is intended to remain valid.
- Treat scheme, host, and port as origin components; approve and test every canonicalization and regional-routing hop.
- Never copy `Authorization` to a redirect target merely because the source supplied a `Location` header.
- If the destination requires authentication, issue a destination-scoped credential through an explicit, authenticated exchange.
- Bound redirect count, reject downgrade to insecure transport, and log the origin transition without logging tokens.
- Verify behavior in every supported browser and server-side Fetch implementation against the current Fetch Standard.

## Implementation and tests

Stand up controlled endpoints for same-origin redirect, different host, different subdomain, different port, HTTP-to-HTTPS, HTTPS-to-HTTP, and a multi-hop chain that becomes cross-origin and later returns. Assert that the destination receives `Authorization` only on the approved same-origin path and that a cross-origin hop removes it for the remainder of the Fetch algorithm.

Test expired and destination-scoped tokens, relative and absolute `Location`, redirect loops, CORS success and failure, and a hostile redirect target. Ensure retry logic does not turn the destination 401 into an infinite authenticated loop.

## Gotchas

The Fetch specification removes `Authorization` when the current URL’s origin differs from the redirect location. This is separate from cookie credential mode, CORS response visibility, and HTTP authentication caches. A subdomain is a different origin even when both names belong to the same organization.

Some non-browser HTTP libraries have different redirect policies. Do not project their behavior onto standards-based `fetch()`; test the actual runtime.

## Official sources

- [WHATWG Fetch Standard: HTTP-redirect fetch](https://fetch.spec.whatwg.org/#http-redirect-fetch)
- [WHATWG URL Standard: Origin](https://url.spec.whatwg.org/#origin)
