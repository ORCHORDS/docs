# consumer-driven-contracts

**Issue:** Implementing consumer-driven contract testing to prevent integration failures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Multiple consumers rely on a shared API. A provider change breaks one consumer without the team realizing it.

## Pattern / Solution
Workflow:
1. Consumer writes pact (expected interactions)
2. Consumer CI publishes pact to broker
3. Provider CI pulls all pacts and verifies against real implementation
4. Broker tracks compatibility — blocks deployments if verification fails

```yaml
# .github/workflows/provider.yml
- name: Verify pacts
  run: npm run test:pact:provider
  env:
    PACT_BROKER_URL: ${{ secrets.PACT_BROKER_URL }}
    PACT_BROKER_TOKEN: ${{ secrets.PACT_BROKER_TOKEN }}
    PACT_PROVIDER_VERSION: ${{ github.sha }}
```

Provider verification setup:
```ts
import { Verifier } from "@pact-foundation/pact";

test("provider verifies consumer pacts", () => {
  return new Verifier({
    provider: "user-api",
    providerBaseUrl: "http://localhost:3000",
    pactBrokerUrl: process.env.PACT_BROKER_URL,
    publishVerificationResult: true,
    providerVersion: process.env.PACT_PROVIDER_VERSION,
  }).verifyProvider();
});
```

## Gotchas
- Consumer publishes with branch name — broker tracks per-branch compatibility
- `can-i-deploy` check in CI before deploy: `npx pact-broker can-i-deploy --pacticipant user-api --version $SHA --to-environment production`
- State handlers on provider must set up required data

## Related
- `contract-testing-pact.md`
- `integration-test-api.md`
