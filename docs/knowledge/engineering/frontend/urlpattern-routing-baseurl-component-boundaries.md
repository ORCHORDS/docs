# URLPattern routing: base URL and component boundaries

**Issue:** Route matching is implemented with substring checks or one regular expression over a serialized URL. Host, port, path, query, and hash boundaries blur together, relative patterns resolve unexpectedly, and a route match is mistaken for authorization.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published — feature-detect

## Matching model

The WHATWG URL Pattern Standard matches URL components separately: protocol, username, password, hostname, port, pathname, search, and hash. `test()` returns a boolean; `exec()` returns per-component inputs and named groups.

Constructor forms are materially different:

- A string pattern without a protocol needs an explicit base URL or construction throws.
- A relative string with a base URL resolves similarly to a relative URL.
- An object initializer can specify individual components. Missing components default according to the initializer processing rules, so make security-relevant components explicit.
- Matching is case-sensitive by default; `ignoreCase` is an explicit option.

## Routing pattern

```js
if (!globalThis.URLPattern) useFallbackRouter();

const productRoute = new URLPattern({
  protocol: "https",
  hostname: "shop.example",
  port: "",
  pathname: "/products/:id([0-9]+)",
  search: "*",
  hash: "*",
});

const match = productRoute.exec(request.url);
if (!match) return notFound();

const id = match.pathname.groups.id;
return loadAuthorizedProduct(id, currentPrincipal);
```

Parse input as a URL and keep routing distinct from authorization. A successful match only extracts a candidate resource identifier; the authenticated principal and tenant must still be checked at the data boundary.

## Controls

1. Compile a fixed, reviewed route table at startup. Do not accept arbitrary pattern syntax from an untrusted request.
2. Supply a fixed base URL whenever relative pattern strings are used. Do not use the incoming Host header as an implicit base without validation.
3. Specify protocol, hostname, and port for routes that must be origin-bound. A pathname-only wildcard must not become an open redirect or SSRF allowlist.
4. Read captures from the correct component, such as `result.pathname.groups`. Reject missing or unexpected groups.
5. Canonicalize only through platform URL processing. Test encoded delimiters, percent encoding, Unicode hostnames, IPv6, default ports, credentials, empty query/hash, and trailing slashes.
6. Keep an equivalent, conformance-tested fallback where target runtimes lack `URLPattern`.
7. Version route contracts. Changing a pattern can invalidate saved links and service-worker routes.

## Verification

Build positive and negative tables for every component. Include wrong scheme, subdomain lookalikes, explicit non-default ports, relative URLs under different bases, path traversal-looking strings, encoded slashes, query/hash differences, and patterns with regular-expression groups. Run applicable Web Platform Tests or mirror their edge cases in each supported runtime.

## Gotchas

- A wildcard in an omitted component can widen a match beyond the visible pathname.
- `ignoreCase` affects matching and should not be enabled as a blanket compatibility fix.
- Pattern capture is not input validation for downstream SQL, filesystem, redirect, or fetch use.
- URL state serialization and URL route matching are separate concerns.

## Sources

- [WHATWG URL Pattern Living Standard](https://urlpattern.spec.whatwg.org/)
