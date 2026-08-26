# api-versioning-strategy

**Issue:** Evolving APIs over time without breaking existing consumers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Deploying a breaking API change takes down mobile apps that cannot be force-updated.

## Pattern / Solution
Three versioning strategies:

1. URI versioning: `/v1/orders`, `/v2/orders` — simple, explicit, easy to route
2. Header versioning: `Accept: application/vnd.api+json;version=2` — clean URLs, harder to test in browser
3. Query param: `?version=2` — deprecated, pollutes query string

Sunset strategy:
```
v1 → supported
v2 → current
v3 → beta

Deprecation header: Sunset: Sat, 31 Dec 2026 23:59:59 GMT
```

## Gotchas
- Running multiple versions in parallel doubles testing and maintenance burden
- Version the resource representation, not the API endpoint where possible
- Additive changes (new optional fields) are backward compatible and do not require a new version

## Related
- `backward-compatibility-design.md`
- `contract-first-api-design.md`
- `openapi-spec-driven-development.md`
