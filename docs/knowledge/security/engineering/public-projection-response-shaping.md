# public-projection-response-shaping

**Issue:** Every leak incident on the example project public API traced to the same shape: a handler ran a broad query (`SELECT *` or an ORM entity fetch), then serialized the whole row/object with `JSON.stringify` straight into the response — carrying internal DB fields (user emails, moderation flags like `autoFlaggedScore`/`moderationState`, internal sequential IDs, soft-delete tombstones) out to anonymous clients. The structural problem is that the database schema is a *superset* of the public API contract, and nothing between the two enforces the difference. The fix is an explicit allowlist projection layer at the API boundary: a per-endpoint, typed mapping from internal rows to public DTOs, where a field appears in a response only because someone deliberately added it to the projection — never because it exists in the table.

**Date:** 2026-08-15
**Repo:** example-org/example-repo (fork example-org/example-repo)
**Author:** ORCHORDS
**Status:** published

## Why leaks happen without one

1. **The schema grows; the response grows with it.** Adding a column for a new moderation or compliance feature silently widens every `SELECT *`-backed response — there is no code change at the endpoint to review, so the leak ships invisibly. This is the exact mechanism behind OWASP API3:2023 (Broken Object Property Level Authorization), the renamed Excessive Data Exposure.
2. **`JSON.stringify` serializes everything it is handed.** ORMs decorate entities with internal state (join caches, flags, timestamps, FK IDs); passing the entity to the serializer publishes all of it. Cobalt's write-ups on excessive data exposure document this as the single most common API leak vector.
3. **Blocklists fail by construction.** Stripping `passwordHash` and `email` from responses enumerates what you *know* is sensitive today; the next sensitive field is by definition not on the list yet. An allowlist inverts the default: unknown fields are excluded until deliberately added.
4. **"The client ignores extra fields" is not a property.** Attackers read raw responses; buried fields are discoverable by anyone with a proxy, and are the reconnaissance step for targeted enumeration and social engineering.

## The projection layer pattern

1. **One projection function per public resource.** `toPublicVideo(row)`, `toPublicUser(row)` — each returns a fresh object built field-by-field from an explicit allowlist. Every public handler passes rows through the projection before serialization; the raw row never crosses the response boundary.
2. **Types enforce the boundary.** The projection's return type (`PublicVideoDTO`) is the only type the response layer accepts; an attempt to return the DB row type is a compile error, not a code-review hope. Where queries back projections directly, select the columns the DTO needs — the projection and the query allowlist should agree.
3. **Projections are per-audience, not one-per-resource.** The owner of a video sees more than an anonymous viewer (`draftReason` for the owner, nothing for others); model this as separate projections or a projection parameterized by viewer role — field-level authorization, evaluated server-side.
4. **Transform, don't just filter.** Projections are also the place to reshape for the public contract: expose the public slug/UUID instead of the internal sequential ID, convert timestamps to ISO-8601, and derive display values instead of exposing stored ones.

## Defense in depth around the projection

1. **Query-level allowlists still matter.** The projection stops leaks at the boundary, but selecting only needed columns at the query layer reduces the blast radius of a missed projection and keeps PII out of Worker memory in the first place — see `security/select-star-data-leak.md` for the SQL-side pattern.
2. **Input side is a different hole with the same shape.** Mass-assignment (clients writing fields you never meant to accept) is the write-direction sibling; allowlist binding on input and allowlist projection on output are deployed as a pair.
3. **Gateway-level filtering as a backstop.** API gateways (e.g., APISIX response filtering) can strip configured field names from responses platform-wide — useful as a safety net for legacy endpoints not yet behind projections, never as the primary control because it is still a blocklist.
4. **Log the same projection, not the same object.** Response logging that serializes the pre-projection object re-introduces the leak into logs; log the projected DTO (and see `security/security-logging-what-to-log.md`).

## GraphQL field sensitivity

1. **GraphQL inherits the problem at field granularity.** A type whose resolvers expose the internal model means any client can query `email`, `moderationState`, or internal IDs directly — the projection equivalent is a deliberately designed public schema where sensitive fields simply do not exist on public types.
2. **Field-level authorization belongs in resolvers, not client restraint.** Directives/middleware (GraphQL Shield-style `@auth` rules) must gate sensitive fields per viewer role; "the UI never asks for that field" is not a control.
3. **Disable introspection and field suggestions in production.** Schema reconnaissance plus "Did you mean `emailHash`?" suggestions turn a fat schema into an enumeration tool — see `security/graphql-introspection-disable.md`; treat both as hardening around the schema-projection principle, not substitutes for it.
4. **Prefer separate schemas per trust level.** One public schema and one internal/admin schema beat a single mega-schema with hidden fields — the boundary is structural instead of per-field.

## Testing for leaks

1. **Assert the absence of internal fields.** Contract tests deserialize every public endpoint response and assert that a canonical denylist of internal field names (`email`, `moderation*`, `internal*`, `*Id` for sequential IDs) never appears; the test fails when a new sensitive column leaks before any user sees it.
2. **Schema-drift test.** A test that diffs the DB table's column set against each endpoint's projection fails whenever a new column is added without a projection decision — this converts the invisible `SELECT *` widening into a visible CI failure.
3. **Fuzz the serializer.** Serialize responses for entities with hostile field values (unicode, control chars, huge strings) to catch serialization crashes that would tempt someone to bypass the projection in a hotfix.
4. **Test both audiences.** For role-parameterized projections, assert the anonymous projection omits owner-only fields and the owner projection includes them — off-by-audience is the most common regression.

## Gotchas

1. **Nested objects bypass shallow projections.** A projection that copies sub-objects (`row.author` passed through verbatim) drags the author's internal fields along; projections must recurse or apply composed sub-projections (`toPublicUser(row.author)`).
2. **Spread operators silently widen projections.** `{ ...row, extra }` in a "small fix" re-publishes every column including future ones — lint for object spread of raw rows inside response paths.
3. **Error paths leak too.** Validation and error handlers that echo the stored object (or ORM error messages containing row data) bypass the projection entirely; error responses get their own shaped payload.
4. **Caching amplifies leaks.** A response cached at the edge with internal fields present serves the leak to every subsequent viewer until TTL expiry — projections must run before any caching layer, and a discovered leak means purging caches, not just fixing code.

## Related

- `security/select-star-data-leak.md` — the SQL-side column allowlist pattern
- `security/mass-assignment-prevention.md` — the input-direction sibling
- `security/owasp-api-top-10-2023.md` (API3: Broken Object Property Level Authorization)
- `security/graphql-introspection-disable.md`
- `security/security-logging-what-to-log.md`
- Cobalt — Excessive Data Exposure: https://www.cobalt.io/blog/excessive-data-exposure-how-apis-leak-sensitive-data
- APIsec — Excessive Data Exposure / API3: https://www.apisec.ai/blog/excessive-data-exposure
- Ammune — API response data leakage: https://ammune.ai/blog/api-response-data-leakage
- APISIX — preventing sensitive data leaks at the gateway: https://api7.ai/blog/apisix-prevents-sensitive-data-leaking
