# API Versioning Strategies

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A breaking change to an API response shape causes client
failures after a deploy. Rolling back is painful; notifying
every client before the change is impractical. The team has
no formal strategy for communicating API stability or
lifecycle, leading to ad-hoc breakage.

## Context

API versioning is the contract between the server and its
clients. A versioning strategy must answer: how do clients
select a version, how long is each version supported, and
how are breaking changes communicated? On a Workers-based
platform, versioning also affects route configuration in
`wrangler.toml` and client-generated SDK contracts.

## Versioning Mechanisms Compared

| Strategy            | Example              | Notes             |
|---------------------|----------------------|-------------------|
| URL path versioning | `/v1/posts`          | Cacheable; simple |
| Header versioning   | `API-Version: date`  | Clean; less cache |
| Content negotiation | `Accept: vnd.*`      | Pure; complex     |
| Query parameter     | `?version=2`         | Easy; log noise   |

Prefer URL path versioning for public APIs and external
clients: it is trivially cacheable at the edge (Cloudflare
caches by URL), visible in logs, and copyable in browser
address bars. Use date-based header versioning
(`API-Version: YYYY-MM-DD`) for internal APIs where URL
cleanliness matters more than cacheability.

## Semantic Versioning for APIs

Apply a simplified semver scheme:

- **Major** (`v2`): Breaking change — remove a field, change
  a type, require a new mandatory parameter.
- **Minor** (`v1.1` or additive): Add optional fields,
  add new endpoints, relax constraints.
- **Patch**: Bug fixes that do not alter the contract.

Only major versions are exposed in the URL path. Minor and
patch releases are backward-compatible and do not require
clients to change.

## Breaking vs Non-Breaking Changes

| Non-breaking (safe)          | Breaking (needs new major)       |
|------------------------------|----------------------------------|
| Add optional response field  | Remove or rename a field         |
| Add new endpoint             | Change field type (str → int)    |
| Relax validation             | Make optional param required     |
| Add enum value (carefully)   | Remove enum value                |
| Return additional headers    | Change HTTP status code meaning  |

A new enum value is technically non-breaking for consumers
that handle unknown values gracefully; it is breaking for
consumers that use exhaustive switch statements.

## Deprecation Lifecycle and Sunset Header

```
HTTP/2 200
Deprecation: true
Sunset: Sat, 01 Nov 2026 00:00:00 GMT
Link: <https://api.example.com/v2/posts>; rel="successor-version"
Warning: 299 - "v1 is deprecated. Migrate to v2 by 2026-11-01"
```

Lifecycle:

1. **Announce** — publish deprecation date in changelog and
   docs; add `Deprecation` and `Sunset` headers.
2. **Warn** — emit `Warning: 299` header on every v1
   response 90 days before sunset.
3. **Sunset** — return `410 Gone` on the sunset date with a
   `Link` header pointing to the successor.
4. **Remove** — delete Worker route after 30-day grace.

## Versioning Cloudflare Workers Routes

Each major API version maps to a Workers route and,
optionally, a separate Worker script for isolation.

```toml
# wrangler.toml — dual-version routing
[[routes]]
pattern = "api.example.com/v1/*"
script_name = "api-worker-v1"

[[routes]]
pattern = "api.example.com/v2/*"
script_name = "api-worker-v2"
```

During migration, the v1 Worker can delegate internally to
the v2 Worker for non-breaking endpoints, avoiding code
duplication. Remove the v1 route binding on sunset date
after confirming zero traffic via Cloudflare Analytics.

## Client Contract Testing

Use consumer-driven contract tests (Pact or a lightweight
OpenAPI schema diff) to detect breaking changes in CI before
they reach production.

```yaml
# .github/workflows/contract.yml (excerpt)
- name: Diff OpenAPI schemas
  run: |
    npx openapi-diff \
      docs/openapi-v1.yaml \
      docs/openapi-v2.yaml \
      --fail-on-incompatible
```

Publish the OpenAPI spec at a versioned URL so clients can
pin to a known schema and receive automated diff alerts.

## Anti-patterns

- Silently changing a field's semantics without a major
  version bump — clients break without warning.
- Using query parameters for versioning on cacheable
  endpoints; Cloudflare caches by URL including query string
  by default, but Cache API rules are harder to reason about.
- Never sunsetting old versions — maintaining three active
  major versions in parallel doubles QA cost per release.
- Embedding the version in domain names (`v2.api.example.com`)
  instead of paths; TLS cert provisioning adds friction.

## Gotchas

- The `Sunset` header value must be an HTTP-date string,
  not an ISO 8601 string; clients that parse it strictly
  will fail on the wrong format.
- Adding a non-nullable field to an existing response is
  breaking for clients that use strict schema validators
  (e.g., TypeScript generated from OpenAPI with
  `additionalProperties: false`).
- Cloudflare Workers route matching is longest-prefix; a
  `/v1/` route will shadow a `/v1/admin/` route if the
  admin route is not listed first.

## Verification

- Run `openapi-diff` in CI against the previous OpenAPI
  spec; fail the build on any incompatible change detected.
- Check Cloudflare Analytics for v1 traffic volume 30 days
  before and after adding `Sunset` headers; confirm decline.
- Assert `Deprecation` and `Sunset` headers appear on every
  v1 response in integration tests.

## Related

- architecture/backward-compatibility-design.md
- architecture/contract-first-api-design.md
- architecture/openapi-spec-driven-development.md
- architecture/api-gateway-patterns-rate-limiting-routing.md

## Source URLs (verified 2026-08-17)

- https://datatracker.ietf.org/doc/html/rfc8594
- https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-\
deprecation-header
- https://developers.cloudflare.com/workers/configuration/\
routing/routes/
- https://www.openapis.org/
