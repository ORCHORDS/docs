# API Versioning Strategy — Lessons Learned

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A consumer team upgrades a shared internal API client library. Two services break silently
because a previously optional field is now required and the response shape changed for one
endpoint. Neither the producer team nor the consumer teams noticed until a downstream
payment flow failed in production at midnight. The incident lasts four hours.

The root cause is not a bad deploy. The root cause is the absence of an enforced versioning
contract and a breaking-change detection process.

## Context

API versioning is not primarily a URL design decision (`/v1/` vs `Accept: application/vnd.api+json;version=2`).
It is a lifecycle-management discipline: how do you evolve a service contract without
destroying consumers? The strategy must answer four questions before any code ships:

1. What constitutes a **breaking change**?
2. How do consumers **discover** that a new version exists and that an old one will retire?
3. How long is the **sunset window**?
4. What **tooling** enforces the contract automatically?

Without answers baked into process, teams default to "just bump the major version" while
simultaneously not deprecating the old one, leaving both alive indefinitely.

## Defining Breaking vs Non-Breaking Changes

The single most productive investment is publishing a written, team-ratified list of what
counts as breaking. A useful starting taxonomy:

**Always breaking:**
- Removing a field from a response that was documented as present
- Renaming a field
- Changing a field's data type (string → integer, object → array)
- Changing HTTP status codes on success paths (200 → 204)
- Narrowing the accepted range of an input field (string max-length 1000 → 100)
- Removing an endpoint
- Changing authentication scheme on an existing endpoint

**Never breaking:**
- Adding a new optional field to a response (consumers must tolerate unknown fields)
- Adding a new endpoint
- Adding a new enum value consumers are expected to ignore if unknown
- Widening the accepted range of an input field

**Conditionally breaking (document and agree per change):**
- Adding a required field to a request (breaking for existing producers, not consumers)
- Changing timeout behavior
- Changing idempotency semantics

Put this list in the API governance document. Link it from every PR template for services
that expose shared APIs. Without a written definition, "breaking" stays subjective and the
decision is re-litigated on every change.

## Versioning Schemes and Their Trade-offs

### URL-path versioning (`/v1/`, `/v2/`)
Pros: obvious in logs, easy to route at the gateway layer, no header negotiation.
Cons: encourages copy-paste API surfaces, makes it easy to maintain two diverging
implementations instead of a shared core, violates REST resource identity purity.

Best suited for: public APIs with a diverse consumer population and long sunset windows.

### Header versioning (`Accept-Version: 2` or `Api-Version: 2024-01-01`)
Pros: URL is stable, same resource is versioned without duplication.
Cons: invisible in browser address bar, requires client discipline, harder to route in CDN
rules.

Best suited for: internal service meshes where teams control both sides of the call.

### Date-based versioning (Stripe model: `Stripe-Version: 2024-06-20`)
Pros: every deployment is pinned to the API contract that existed on a given date,
regression-proofed by default, consumers explicitly opt in to new behavior.
Cons: significant implementation complexity (version routing middleware), hard to sunset.

Best suited for: SaaS products with paying customers and regulatory change-control
requirements.

### Evolutionary / field-level versioning (GraphQL, gRPC field deprecation)
Pros: consumers retrieve exactly what they need, no full-version ceremony for small changes.
Cons: schema sprawl, deprecation discipline is harder to enforce.

Choose one scheme and stick to it. Mixing URL-path for major changes and headers for minor
changes creates cognitive overhead that outlives any individual engineer.

## Sunset Window Policy

Define a sunset policy before you publish your first breaking change, not after. A workable
default for internal APIs:

- Minor breaking changes (new required field, narrowed validation): **8 weeks** notice
- Endpoint removal or major response shape change: **6 months** notice
- Full version retirement: **12 months** notice after the successor version GA date

Publish the sunset date in:
1. The API documentation (machine-readable `sunset` HTTP response header per RFC 8594)
2. The changelog / release notes
3. Direct Slack notification to all known consumers at announcement, T-30 days, and T-7 days

Use the `Sunset` header on every response from the deprecated version so that consumers
with alerting on HTTP headers get automatic warnings.

## Consumer Discovery and Deprecation Signaling

Passive documentation does not work. Consumers only read docs when something breaks.
Active deprecation signaling requires:

- **`Deprecation` response header**: RFC 9110 conformant, date of deprecation announcement
- **`Sunset` response header**: RFC 8594 conformant, exact UTC datetime of removal
- **`Link` header**: pointing to the migration guide (`rel="deprecation"`)
- **Changelog automation**: auto-generate changelogs from OpenAPI diff on every merge to main

Running `oasdiff` or `openapi-diff` in CI on every PR gives a machine-generated breaking
change report before code is merged. Block merges that introduce undocumented breaking
changes.

## Contract Testing

Consumer-driven contract testing (Pact, or schema snapshot assertions in Vitest) is the
highest-leverage tool for catching version drift. The pattern:

1. Consumer writes a test that declares what it expects the API to return
2. Provider CI runs the consumer's contract as part of its own test suite
3. If the provider change would break the consumer's expectation, CI fails

This flips the detection window from "consumer deploys and breaks" to "provider PR fails
before merge." At Cloudflare Workers scale, where deploy latency is measured in seconds,
catching the issue pre-merge is the only reliable strategy.

## Anti-patterns

**"We'll add a breaking change and just tell everyone."** Verbal or Slack notification has
no enforcement. Without code-level deprecation headers and contract tests, consumers drift.

**Maintaining three or more live versions simultaneously.** Each live version is operational
debt. If you are running v1, v2, and v3, v1 and v2 have no effective sunset date. Cap
simultaneous live versions at two and enforce the cap in the gateway routing configuration.

**Treating internal APIs as exempt from versioning discipline.** Internal API consumers
break just as hard as external ones. The difference is that you usually can't bill them for
the migration cost.

**Version in the payload instead of the transport layer.** Some teams embed `"version": 2`
in the JSON body. This requires every consumer to inspect the payload before routing.
Version in the transport (URL, header) so infrastructure can route or reject before
business logic runs.

**Bumping to v2 on the first non-trivial change.** If v1 has been live for three weeks and
you "break" it for a new required field, the correct response is to fix the consumers
(there are few), not introduce v2. Save version bumps for genuinely large surface changes.

## Gotchas

- **Enum exhaustion**: Consumers often write switch statements with `default: throw`. Adding
  a new enum value is non-breaking in theory but breaks those consumers in practice. Document
  the "unknown enum values MUST be ignored" policy and lint for exhaustive switch patterns.

- **Null vs absent**: `"field": null` and `{}` (absent field) are semantically different in
  JSON. Changing from null to absent or vice versa is a breaking change that JSON schema
  validation will not catch unless you explicitly test both representations.

- **Pagination cursor encoding**: Changing the opaque cursor format is a breaking change
  if consumers store cursors (e.g., in a jobs queue). Cursors that look like base64 or
  UUIDs invite consumers to depend on the internal structure.

- **Cloudflare Workers deployed globally**: A phased rollout of a v2 API behind a Workers
  route means v1 and v2 may be simultaneously reachable at different PoPs during a deploy
  window. Use Durable Objects or a central version store to guarantee atomic cutover.

- **The `Accept` header is not forwarded by all proxies.** Header-versioned APIs behind
  Cloudflare caching rules may cache based on URL alone, serving v1 responses to v2
  requests. Always add `Vary: Accept-Version` (or your version header name) to prevent this.

## Verification

Before shipping any breaking change:

- [ ] Breaking change is listed in the API changelog with migration guidance
- [ ] `Deprecation` and `Sunset` headers are present on all old-version responses
- [ ] Consumer-driven contract tests pass on both old and new version
- [ ] `oasdiff` / `openapi-diff` output reviewed and acknowledged in the PR
- [ ] All known consumers notified through the agreed deprecation channel
- [ ] Sunset date is no sooner than the policy window
- [ ] Old version traffic is monitored and drops to zero before retirement

## Related

- `unknown-field-policy-is-a-versioning-decision.md`
- `third-party-api-changes-break-silent-integrations.md`
- `documentation-decays-without-ownership.md`
- `migrations-must-be-backward-compatible.md`
- `upstream-deprecation-signal-to-migration-deadline.md`

## Sources

- RFC 8594 — The Sunset HTTP Header Field
- RFC 9110 — HTTP Semantics (Deprecation header)
- Stripe API versioning model documentation
- `oasdiff` open-source OpenAPI diff tool
- Pact consumer-driven contract testing documentation
- Cloudflare Workers routing documentation
