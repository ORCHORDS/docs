# contract-testing-pact

**Issue:** Preventing API consumer/provider mismatches with contract testing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Backend changes break frontend without either team knowing until integration. Contract tests catch this at the service boundary.

## Pattern / Solution
Consumer side (frontend):
```ts
import { PactV3, MatchersV3 } from "@pact-foundation/pact";

const provider = new PactV3({
  consumer: "frontend",
  provider: "user-api",
  dir: "./pacts",
});

test("get user by id", async () => {
  await provider.addInteraction({
    states: [{ description: "user 1 exists" }],
    uponReceiving: "a request for user 1",
    withRequest: { method: "GET", path: "/users/1" },
    willRespondWith: {
      status: 200,
      body: {
        id: MatchersV3.integer(1),
        name: MatchersV3.string("Alice"),
      },
    },
  });

  await provider.executeTest(async (mockServer) => {
    const client = new UserClient(mockServer.url);
    const user = await client.getUser(1);
    expect(user.name).toBe("Alice");
  });
});
```

Provider side verifies pacts from broker:
```bash
npx pact-provider-verifier --provider-base-url http://localhost:3000 --pact-broker-url https://broker.example.com
```

## Gotchas
- Pacts are contracts, not integration tests — keep interactions minimal
- Publish pacts to a broker (PactFlow) for CI automation
- Consumer drives the contract, not provider

## Related
- `consumer-driven-contracts.md`
- `integration-test-api.md`
