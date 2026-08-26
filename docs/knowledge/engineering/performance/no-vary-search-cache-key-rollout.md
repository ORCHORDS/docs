# No-Vary-Search cache-key rollout

**Issue:** Tracking query parameters fragment caches into many equivalent entries. A broad attempt to ignore query strings then serves the wrong tenant, locale, page, search result, or personalized response.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** experimental — active Internet-Draft

## Protocol boundary

The HTTP `No-Vary-Search` response header is defined by an active IETF HTTP working-group draft, not a final RFC. It allows an origin to describe which aspects of a URI's query can be disregarded when a cache matches stored responses.

Treat support as negotiated/observed and semantics as draft-versioned. Unsupported caches continue to use their normal cache key, so correctness must not depend on the optimization.

## Safe eligibility

Only declare query equivalence when the origin would produce the same representation, authorization result, validators, and relevant response metadata for every declared-equivalent request.

Good first candidates are bounded, recognized attribution parameters that are not consumed by rendering or business logic. Never ignore:

- tenant, account, authorization, or preview tokens;
- locale, currency, country, experiment, device, or personalization inputs;
- pagination, sort, filters, search terms, or resource versions;
- signed-URL fields or any parameter included in request verification;
- unknown parameters under an “ignore all except” policy unless the application has a strict allowlist contract.

The origin routing layer, CDN configuration, application cache, service worker, and observability pipeline must agree on the parameter semantics.

## Rollout

1. Inventory every query parameter by route, owner, sensitivity, response dependency, and cardinality.
2. Add server tests proving candidate parameters do not change body hash, status, content type, cache controls, ETag, language, or authorization.
3. Emit the draft header on one immutable/public route and one allowlisted parameter.
4. Keep the ordinary response cacheable and correct when the header is ignored.
5. Compare cache-key cardinality, hit ratio, origin requests, response hashes, and cross-cohort mismatch canaries.
6. Purge existing variants when changing equivalence rules. Old cache entries were stored under a different contract.
7. Expand one parameter/route at a time. Keep an immediate header-disable and purge runbook.
8. Record the draft revision and each cache/vendor implementation tested.

## Verification

Test reordered parameters, repeated keys, empty values, percent-encoding variants, key case, unknown keys, signed URLs, authenticated and anonymous requests, tenant/locale boundaries, cache revalidation, purge, downgrade to a non-supporting cache, and mixed cache layers. Use two deliberately different protected representations as a leakage canary.

A performance win is valid only when every equivalence test remains exact. Similar-looking HTML is not enough if headers, validators, or embedded user data differ.

## Gotchas

- URI normalization and query equivalence are separate operations.
- Analytics may need the original request even when cache matching ignores a parameter.
- A draft can change; re-verify after implementation or spec updates.
- Ignoring cache-key input cannot repair an otherwise uncacheable response.

## Sources

- [IETF HTTPbis draft — No-Vary-Search](https://httpwg.org/http-extensions/draft-ietf-httpbis-no-vary-search.html)
