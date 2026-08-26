# api-versioning-2026

**Issue:** API versioning — URL vs header vs date
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your v2 has breaking changes. The CDN serves v1
to v2 callers. Users are confused. You wish you
had a versioning strategy.

## Root cause
**Without versioning strategy, chaos wins.** Pick.

**Source:** Digital Applied + Realty API 2026.

## The "API versioning" concept

API versioning:
- **Why:** Evolve without breaking
- **When:** Breaking change
- **Where:** URL / header / query / date
- **Sunset:** 6-12 months notice

The version is per change.

## The "4 strategies" pattern

For strategies:
- **URL path:** `/v1/users`
- **Header:** `X-API-Version: 2`
- **Query:** `?api-version=v1`
- **Date:** `X-GitHub-Api-Version: 2026-03-10`

The strategy is per need.

## The "URL path versioning" pattern

For path:
- **Format:** `/v1/users`
- **Cache:** Per version (clean)
- **Visibility:** High
- **Use:** Public API default
- **Downside:** URL churn

The path is the default.

## The "header versioning" pattern

For header:
- **Format:** `X-API-Version: 2`
- **URL:** Stable
- **Cache:** Need Vary header
- **Use:** When URL stability required
- **Pitfall:** Wrong Vary = wrong version cached

The header is conditional.

## The "query parameter" pattern

For query:
- **Format:** `?api-version=v1`
- **URL:** Stable
- **Cache:** Inconsistent
- **Use:** Internal services
- **Downside:** Easy to forget

The query is fragile.

## The "date-based" pattern

For date:
- **Format:** `X-GitHub-Api-Version: 2026-03-10`
- **Used by:** GitHub, Stripe
- **Decouples:** API from SDK cadence
- **Identity:** Precise
- **Use:** Public API

The date is platform.

## The "comparison" pattern

For choice:
| Dim | URL | Header | Query | Date |
|---|---|---|---|---|
| Cache | Clean | Vary needed | Inconsistent | Vary needed |
| Visibility | High | Low | Medium | Low |
| URL stability | No | Yes | Yes | Yes |
| CDNs work | Yes | Risk | Medium | Yes |
| Debug easy | Yes | Hard | Medium | Medium |

The choice is per need.

## The "GraphQL + gRPC" pattern

For "no version":
- **GraphQL:** Schema evolution
- **gRPC:** Proto evolution
- **No URL:** Schema versioning
- **Defer:** Deprecation fields

The schema is the contract.

## The "GitHub date" pattern

For GitHub:
- **Header:** `X-GitHub-Api-Version: 2026-03-10`
- **Current:** 2026-03-10 (June 2026)
- **Legacy:** 2022-11-28 (until March 2028)
- **Use:** Public API

The GitHub is the example.

## The "Stripe date" pattern

For Stripe:
- **Header:** `Stripe-Version: 2024-06-20`
- **Pinned:** Per account
- **Default:** Account setting
- **Rollback:** Easy (just change header)

The Stripe is the example.

## The "no version" anti-pattern

For "no version":
- **Issue:** "Don't break things"
- **Result:** Hard to evolve
- **Fix:** Version from day 1

The version is required.

## The "Vary missing" anti-pattern

For header:
- **Issue:** CDN caches wrong
- **Fix:** `Vary: X-API-Version`

The Vary is required.

## The "version in body" anti-pattern

For body:
- **Issue:** Hard to route
- **Fix:** URL or header

The version is in URL/header.

## The "no sunset" anti-pattern

For no sunset:
- **Issue:** Old version forever
- **Fix:** 6-12 month deprecation

The sunset is documented.

## The "single version" anti-pattern

For single:
- **Issue:** Can't break
- **Fix:** Run v1 + v2 in parallel

The dual is required.

## The "sunset 410" pattern

For sunset:
- **Header:** `Sunset: Sat, 01 Jan 2028 00:00:00 GMT`
- **Final:** `410 Gone`
- **Before:** 200 + warning

The 410 is final.

## The "Deprecation header" pattern

For deprecate:
- **Header:** `Deprecation: true`
- **Link:** To migration
- **Sunset:** When
- **Warning:** 299

The Deprecation is per RFC 8594.

## The "OpenAPI deprecated" pattern

For spec:
```yaml
paths:
  /v1/users:
    get:
      deprecated: true
      description: |
        Deprecated. Use /v2/users.
        Sunset: 2028-01-01
```

The spec marks deprecated.

## The "versioning policy" pattern

For policy:
- **Deprecation:** What counts as breaking
- **Dual support:** Min 2 versions
- **Telemetry:** Per client
- **Sunset:** Hard date in gateway

The policy is documented.

## The "deprecation window" pattern

For window:
- **Public API:** 6-12 months
- **Internal:** 4-6 weeks
- **Notice:** Multi-channel
- **High-volume clients:** Direct support

The window is per audience.

## The "telemetry" pattern

For telemetry:
- **Track:** Per client
- **Aggregate:** Per version
- **Dashboard:** Real-time
- **Alert:** If v1 still high

The telemetry is per client.

## The "migration guide" pattern

For guide:
- **Differences:** v1 vs v2
- **Code samples:** Both
- **Timeline:** Sunset date
- **Support:** Contact

The guide is required.

## The "sunset checklist" pattern

For checklist:
- [ ] Deprecation header
- [ ] Sunset header
- [ ] OpenAPI deprecated: true
- [ ] Migration guide
- [ ] Multi-channel notice
- [ ] Telemetry by client
- [ ] Hard date in gateway
- [ ] Top clients migrated
- [ ] Final 410 Gone

The checklist is 9.

## The "no Vary" anti-pattern

For no Vary:
- **Issue:** Cache poison
- **Fix:** Vary: X-API-Version

The Vary is set.

## The "version in body" anti-pattern

For body:
- **Issue:** Hard to route
- **Fix:** URL or header

The version is outside body.

## The "GraphQL deprecated field" pattern

For GraphQL:
```graphql
type User {
  id: ID!
  name: String! @deprecated(reason: "Use fullName")
  fullName: String!
}
```

The deprecate is in schema.

## The "gRPC proto evolution" pattern

For gRPC:
- **Field tag:** Never reuse
- **Reserved:** `reserved 5;`
- **Add:** New field
- **Never:** Change existing

The proto is additive.

## The "versioning decision" pattern

For choice:
- **Public + diverse consumers:** URL
- **CDN-heavy:** URL
- **URL stability required:** Header
- **Internal:** Query or no version
- **Public API + cadence:** Date (GitHub)

The decision is per need.

## The "versioning checklist" pattern

For checklist:
- [ ] Strategy chosen
- [ ] v1 + v2 in parallel
- [ ] Cache correct
- [ ] Deprecation policy
- [ ] Sunset dates
- [ ] Telemetry
- [ ] Migration guide
- [ ] OpenAPI marked
- [ ] Headers set

The checklist is 9.

## Verification
- **Test:** Cache per version
- **Test:** v1 + v2 both work
- **Test:** Deprecation header
- **Test:** Sunset enforced
- **Audit:** Quarterly

## Gotchas
- **The "no version" anti-pattern.** Required.
- **The "Vary missing" anti-pattern.** Set.
- **The "no sunset" anti-pattern.** Required.

## Related
- `patterns/api-versioning.md`
- `patterns/api-design-best-practices.md`
- `patterns/api-design-anti-patterns.md`
- `patterns/api-gateway-comparison-2026.md`
- `deploy/semver-best-practices.md`
- Digital Applied: https://www.digitalapplied.com/blog/api-versioning-strategies-2026-engineering-decision-matrix
- Realty API: https://www.realtyapi.io/blog/api-versioning-strategy
- Fern: https://buildwithfern.com/post/api-design-best-practices-guide
