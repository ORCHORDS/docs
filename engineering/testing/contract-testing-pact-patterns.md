# Contract Testing — Pact and Consumer-Driven Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your microservices pass all unit and integration tests independently,
but deployments break because services make incompatible assumptions
about each other's APIs. Service A expects a `user.email` field in the
response, but Service B renamed it to `user.emailAddress`. End-to-end
tests catch these issues but are slow (10-30 minutes), flaky, and
require all services running simultaneously. API changes are deployed
and break consumers in production because there is no automated way to
verify compatibility before deployment.

## Context

Contract testing verifies that two services can communicate correctly
without requiring both services to be running simultaneously. Instead
of testing the integration, each side tests against a "contract" — a
recorded agreement about the API interface. Consumer-driven contract
testing (CDC), popularized by Pact, inverts the traditional approach:
the consumer defines what it needs from the provider, and the provider
verifies it can satisfy those needs. In 2026, Pact is the most widely
adopted contract testing tool, with bi-directional contract testing
(BDCT) offering a lighter-weight alternative that works with existing
OpenAPI specifications.

## Contract testing vs. other testing types

```
Unit tests:
  → Test a single service in isolation
  → Mock external dependencies
  → Fast, but cannot verify integration

Integration tests (end-to-end):
  → Test multiple services together
  → Require all services running
  → Slow, flaky, expensive to maintain

Contract tests:
  → Test service compatibility without running both
  → Each service tests independently against the contract
  → Fast, reliable, catches API mismatches early
```

## Consumer-driven contract testing flow

```
1. Consumer writes a contract (Pact file)
   → "When I call GET /users/123, I expect { id, name, email }"

2. Consumer tests pass against a mock provider
   → Pact mock server returns the expected response
   → Consumer code is verified to handle the response correctly

3. Contract is published to the Pact Broker
   → Versioned, shared registry of all contracts

4. Provider verifies the contract
   → Provider runs against real implementation
   → Verifies it can satisfy all consumer expectations

5. can-i-deploy check gates deployment
   → Before deploying, check if this version is compatible
   → with all its consumers/providers
```

### Consumer side (JavaScript)

```javascript
import { PactV4 } from '@pact-foundation/pact';

const provider = new PactV4({
  consumer: 'OrderService',
  provider: 'UserService',
});

describe('User API contract', () => {
  it('returns user details', async () => {
    await provider
      .addInteraction()
      .given('user 123 exists')
      .uponReceiving('a request for user 123')
      .withRequest('GET', '/users/123', (builder) => {
        builder.headers({ Accept: 'application/json' });
      })
      .willRespondWith(200, (builder) => {
        builder
          .headers({ 'Content-Type': 'application/json' })
          .jsonBody({
            id: 123,
            name: 'Jane Doe',
            email: 'jane@example.com',
          });
      })
      .executeTest(async (mockServer) => {
        const response = await fetch(`${mockServer.url}/users/123`, {
          headers: { Accept: 'application/json' },
        });
        const user = await response.json();

        expect(user.id).toBe(123);
        expect(user.name).toBeDefined();
        expect(user.email).toContain('@');
      });
  });
});
```

### Provider side (verification)

```javascript
import { Verifier } from '@pact-foundation/pact';

describe('User Service contract verification', () => {
  it('satisfies all consumer contracts', async () => {
    const verifier = new Verifier({
      providerBaseUrl: 'http://localhost:3000',
      pactBrokerUrl: 'https://pact-broker.example.com',
      provider: 'UserService',
      providerVersion: process.env.GIT_SHA,
      publishVerificationResult: true,
      stateHandlers: {
        'user 123 exists': async () => {
          await db.users.create({ id: 123, name: 'Jane Doe',
            email: 'jane@example.com' });
        },
      },
    });

    await verifier.verifyProvider();
  });
});
```

## Pact Broker and can-i-deploy

```bash
# Publish consumer contract to Pact Broker
pact-broker publish ./pacts \
  --consumer-app-version=$GIT_SHA \
  --branch=$BRANCH_NAME \
  --broker-base-url=https://pact-broker.example.com

# Check if this version can be deployed safely
pact-broker can-i-deploy \
  --pacticipant=OrderService \
  --version=$GIT_SHA \
  --to-environment=production

# Output:
# COMPUTER SAYS YES \o/
# All required verification results are published and successful
```

## Bi-directional contract testing (BDCT)

```
Traditional CDC:              BDCT:
  Consumer writes pact          Consumer writes pact
  Provider verifies pact        Provider publishes OpenAPI spec
                                Pact Broker cross-references both

BDCT advantages:
  → Provider does not need to run Pact verifier
  → Works with existing OpenAPI/Swagger specs
  → Lower adoption barrier for provider teams
  → Consumer still defines expectations

BDCT limitation:
  → Cannot verify provider state handling
  → Less precise than full verification
```

## Anti-patterns

- **Testing implementation, not contract** — asserting on exact
  response bodies instead of the fields the consumer actually uses.
  Contract tests should verify the shape (required fields, types),
  not exact values. Use matchers (`like()`, `eachLike()`) instead
  of exact matches.
- **Skipping provider states** — not setting up the required state
  before provider verification. The provider must be in the state
  the consumer expects ("user 123 exists"). Without state handlers,
  tests pass or fail based on ambient data.
- **Not using can-i-deploy** — publishing contracts but not gating
  deployments on compatibility checks. The value of contract testing
  is preventing incompatible deployments, not just detecting them.
- **Contract tests replacing integration tests** — contract tests
  verify API compatibility, not business logic correctness. You
  still need integration tests for workflows that span services.

## Gotchas

- **Consumer team must own the contract** — the consumer defines
  what it needs. If the provider team writes the contract, it becomes
  provider-driven and misses the point: catching changes that break
  consumers.
- **Pact Broker is essential** — running contract tests without a
  shared broker means contracts are not versioned, verification
  results are not tracked, and `can-i-deploy` is unavailable. Use
  PactFlow (SaaS) or self-hosted Pact Broker.
- **Breaking contract changes** — when a provider needs to remove
  a field that a consumer uses, the consumer must update its contract
  first. This requires coordination between teams but is the
  correct workflow — it surfaces breaking changes before deployment.
- **Multiple consumers** — a provider may have many consumers, each
  with different contracts. The provider must satisfy all of them.
  Use the Pact Broker's network graph to visualize dependencies.

## Verification

- All inter-service APIs have consumer-driven contracts.
- Contracts are published to a Pact Broker with version tagging.
- Provider verification runs in CI on every PR.
- `can-i-deploy` gates production deployments.
- Contract tests use matchers for flexible assertions.
- Provider state handlers set up required test data.

## Related

- `documentation/categories/testing/property-based-testing.md`
- `documentation/categories/testing/visual-regression-testing-tools.md`
- `documentation/categories/patterns/api-design-patterns.md`

## Source URLs (verified 2026-08-16)

- Contract Testing for Microservices 2026 — https://totalshiftleft.ai/blog/contract-testing-for-microservices
- Consumer-Driven Contract Testing with Pact 2026 — https://www.sqaexperts.com/consumerdriven-contract-testing-with-pact-microservices-qa-guide-for-2026
- Pact Contract Testing Complete Guide 2026 — https://qaskills.sh/blog/pact-contract-testing-complete-guide-2026
- How to Configure Contract Testing with Pact — https://oneuptime.com/blog/post/2026-01-24-contract-testing-pact/view
