# API Contract Testing — Consumer-Driven Contracts, Schema-First Testing, and Bi-Directional Verification

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your microservices team deploys a backend change that renames a JSON
field from `userName` to `user_name`. The provider's own tests pass
because they test the new schema. The frontend team discovers the
breakage in production because their consumer expectations were never
verified against the provider. Meanwhile, your public API has unknown
external consumers, so consumer-driven contract testing cannot cover
them — you need schema-first validation but are only running Pact.

## Context

API contract testing verifies that providers and consumers agree on
request/response shapes without requiring end-to-end integration
tests. Three complementary approaches exist in 2026: consumer-driven
contract testing (Pact) where consumers define expectations verified
against the provider, schema-first testing (Schemathesis, Dredd)
where tools generate tests from OpenAPI/GraphQL schemas, and
bi-directional contract testing (PactFlow) where both sides
independently publish contracts that are statically compared. Mature
teams run both — Pact for known high-value consumer relationships
and schema-first fuzzing for public APIs with unknown consumers.

## Consumer-driven contract testing (Pact)

```javascript
// Consumer test — generates a pact file
const provider = new Pact({
  consumer: 'WebApp',
  provider: 'OrdersAPI',
});

it('gets order by id', () => {
  provider.addInteraction({
    state: 'order 123 exists',
    uponReceiving: 'a request for order 123',
    withRequest: { method: 'GET', path: '/orders/123' },
    willRespondWith: {
      status: 200,
      body: { id: 123, status: 'shipped' },
    },
  });
  return orderClient.getOrder(123)
    .then(order => expect(order.status).toBe('shipped'));
});
```

```
Consumer-driven flow:

  1. Consumer writes tests against a mock provider
  2. Tests generate a "pact" (JSON contract file)
  3. Pact published to a broker (Pact Broker / PactFlow)
  4. Provider replays consumer interactions against real implementation
  5. Provider cannot break fields any consumer relies on

  Best for: known consumers you control
  Limitation: only protects interactions consumers recorded
```

## Schema-first testing (Schemathesis)

```bash
# CLI — property-based fuzzing from OpenAPI schema
st run openapi.yaml --url https://api.example.com

# Test only documented examples
st run --phases=examples https://api.example.com/openapi.json
```

```python
# pytest integration — generates random/edge-case inputs
import schemathesis

schema = schemathesis.from_uri("https://api.example.com/openapi.json")

@schema.parametrize()
def test_api(case):
    case.call_and_validate()
```

```yaml
# GitHub Actions integration
- uses: schemathesis/action@v3
  with:
    schema: "https://api.example.com/openapi.json"
```

```
Schema-first tools:

  Tool           Approach                    Best for
  ──────────────────────────────────────────────────────────
  Schemathesis   Property-based fuzzing      Finding edge cases,
                 from OpenAPI/GraphQL        unknown consumers

  Dredd          Replays documented          Validating API matches
                 examples from spec          its documentation

  Best for: public APIs with unknown consumers
  Generates: randomized inputs constrained by schema
```

## Bi-directional contract testing (PactFlow)

```
How it works:

  1. Consumer publishes a Pact-style contract (from mocked tests)
  2. Provider publishes an OpenAPI spec (from their own tests)
  3. PactFlow broker statically compares the two for compatibility
  4. No code changes required on the provider side

  Trades rigor (static check, not full replay) for lower
  provider-side effort. Decouples consumer/provider release
  cadence more than classic consumer-driven testing.
```

## Dredd configuration

```yaml
# dredd.yml
dry-run: null
hookfiles: ./hooks.js
server: npm start
server-wait: 3
color: true
level: info
blueprint: ./openapi.yaml
endpoint: 'http://127.0.0.1:3000'
```

```
Dredd validates that a running API matches its OpenAPI/API Blueprint
description by replaying each documented example as a request and
diffing the response. Supports setup/teardown hooks per operation.
Run each operation in isolation to avoid shared-state flakiness.
```

## Anti-patterns

- **Treating Pact as sufficient for public APIs** — consumer-driven
  contracts only protect interactions consumers actually recorded.
  Unknown consumers and undocumented usage patterns remain unverified.
  Use schema-first fuzzing for the unknown-consumer surface.
- **Skipping provider verification** — the value of contract testing
  collapses if provider verification is not run in the provider's CI
  on every change. Contract drift goes undetected until runtime.
- **Confusing schema validation with contract testing** — validating
  that responses conform to an OpenAPI schema does not guarantee a
  consumer's actual usage still works. A field can stay schema-valid
  but change meaning or format.
- **Provider hand-writing verification for every consumer** — this
  friction pushed teams toward bi-directional contract testing, which
  trades some rigor for lower provider-side effort.

## Gotchas

- **Running operations non-isolated** — shared state between test
  cases causes flaky, order-dependent failures in both Dredd and
  Schemathesis. Use explicit setup/teardown per operation.
- **No drift detection on staging** — contract tests that only run
  at PR time miss backward-incompatible changes introduced by
  config or data changes after merge. Run continuous verification
  against staging environments.
- **Schemathesis stateful testing** — supports OpenAPI Links for
  multi-step stateful test sequences (create → read → update →
  delete) but requires Links to be defined in the spec.
- **Pact broker version selectors** — the "can I deploy" check
  requires correct version tagging. Misconfigured selectors can
  give false confidence that a deployment is safe.

## Verification

- Consumer-driven contracts generated and published to broker on every PR.
- Provider verification runs in provider CI against all published contracts.
- Schema-first fuzzing (Schemathesis) runs against public API endpoints.
- Bi-directional compatibility check passes before deployment.
- Contract tests run against staging for continuous drift detection.
- Hard-decline vs soft-decline response codes documented in contracts.

## Related

- `documentation/categories/testing/contract-testing-pact-provider-verification.md`
- `documentation/categories/architecture/api-gateway-patterns-rate-limiting-routing.md`
- `documentation/categories/deploy/feature-flag-lifecycle-management.md`

## Source URLs (verified 2026-08-16)

- 12 Best Contract Testing Tools in 2026 — https://keploy.io/blog/community/contract-testing-tools
- Contract Testing Plan: From OpenAPI to CI — https://spec-coding.dev/blog/contract-testing-plan-from-openapi-to-ci
- Bi-Directional Contract Testing (PactFlow) — https://pactflow.io/bi-directional-contract-testing/
- Schemathesis: Property-Based API Testing — https://schemathesis.io/
