# api-contract-testing-pact-workers

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

The example project mobile app and the Workers API evolve independently.
A backend engineer renames a JSON field or removes a deprecated
endpoint. The change is safe according to the Workers unit tests
but breaks the mobile app in production because no test verified
that the consumer (mobile) and the provider (Workers) agreed on
the shape of the contract. Integration tests catch some of these
regressions, but only if a matching scenario is written for every
field. A single source of truth for what the mobile app expects
does not exist in the codebase.

## Context

Pact is a consumer-driven contract testing framework. The consumer
(the example project mobile app, built with React Native) generates a
Pact file — a JSON document that records every interaction it
exercised during its test suite. The provider (the Cloudflare
Worker) then replays those recorded interactions against itself
and verifies it satisfies each one. If the Worker changes a
response shape the mobile app depends on, provider verification
fails in CI before the change is deployed.

This pattern is "consumer-driven" because the consumer dictates
what it needs; the provider does not define the contract unilaterally.

Key terms:

| Term | Definition |
|------|------------|
| Consumer | The service that calls the API — here, the mobile app |
| Provider | The service that serves the API — here, the Workers |
| Pact file | JSON document of recorded interactions |
| Pact Broker | Central registry that stores and publishes Pact files |
| Provider verification | Running the Pact interactions against the real provider |

## Project Structure

```
apps/
  mobile/
    src/
      api/
        events.ts         # API client module
      __tests__/
        pact/
          events.pact.spec.ts   # consumer Pact tests
pact/
  pacts/                  # generated Pact JSON files (gitignored in CI)
workers/
  api/
    src/
      index.ts
    __tests__/
      pact/
        provider.pact.spec.ts   # provider verification tests
pact.config.ts            # shared Pact configuration
```

## Consumer Test: Mobile App

The consumer test exercises the API client against a Pact mock
server. The mock server records each interaction and writes the
Pact file.

```ts
// apps/mobile/src/__tests__/pact/events.pact.spec.ts
import path from 'path';
import { PactV3, MatchersV3 } from '@pact-foundation/pact';
import { fetchEvents } from '../../api/events.js';

const { like, eachLike, string, integer } = MatchersV3;

const provider = new PactV3({
  consumer: 'example project-mobile-app',
  provider: 'example project-workers-api',
  dir: path.resolve(__dirname, '../../../../../pact/pacts'),
  port: 4000,
  logLevel: 'warn',
});

describe('Events API — consumer contract', () => {
  describe('GET /api/events', () => {
    it('returns a list of events with required fields', async () => {
      await provider
        .addInteraction({
          states: [{ description: 'at least one published event exists' }],
          uponReceiving: 'a request for the events list',
          withRequest: {
            method: 'GET',
            path:   '/api/events',
            headers: {
              Accept: 'application/json',
              // Mobile clients always send this header
              'x-client-platform': string('mobile'),
            },
          },
          willRespondWith: {
            status: 200,
            headers: { 'content-type': string('application/json') },
            body: {
              results: eachLike({
                id:        string('evt_01J000000000000000'),
                title:     string('Sample Event'),
                startsAt:  string('2026-09-01T18:00:00Z'),
                venue:     like({ name: string('The O2 Arena') }),
                imageUrl:  string('https://cdn.example.com/img/sample.jpg'),
              }),
              meta: like({
                total:  integer(1),
                cursor: string(''),
              }),
            },
          },
        })
        .executeTest(async (mockServer) => {
          const events = await fetchEvents(mockServer.url, {
            platform: 'mobile',
          });
          expect(events.results).toHaveLength(1);
          expect(events.results[0]).toHaveProperty('id');
          expect(events.results[0]).toHaveProperty('startsAt');
        });
    });

    it('returns 404 when no events exist', async () => {
      await provider
        .addInteraction({
          states: [{ description: 'no events exist' }],
          uponReceiving: 'a request for events when none exist',
          withRequest: {
            method:  'GET',
            path:    '/api/events',
            headers: { Accept: 'application/json' },
          },
          willRespondWith: {
            status: 200,
            body:   { results: [], meta: like({ total: integer(0) }) },
          },
        })
        .executeTest(async (mockServer) => {
          const events = await fetchEvents(mockServer.url, {});
          expect(events.results).toHaveLength(0);
        });
    });
  });
});
```

## Provider Verification: Workers API

Provider verification runs against a locally started version of
the Worker (via Miniflare or a staging deployment). It replays
every interaction from the Pact file and asserts the Worker
responds as contracted.

```ts
// workers/api/__tests__/pact/provider.pact.spec.ts
import path from 'path';
import { Verifier } from '@pact-foundation/pact';
import { unstable_dev } from 'wrangler';
import type { UnstableDevWorker } from 'wrangler';

let worker: UnstableDevWorker;

beforeAll(async () => {
  worker = await unstable_dev('src/index.ts', {
    experimental: { disableExperimentalWarning: true },
    vars: {
      ENVIRONMENT: 'test',
    },
  });
});

afterAll(async () => {
  await worker?.stop();
});

describe('Provider verification — example project-workers-api', () => {
  it('satisfies all consumer contracts', async () => {
    const opts = {
      provider:            'example project-workers-api',
      providerBaseUrl:     `http://127.0.0.1:${worker.port}`,

      // Load Pact files from local directory (CI: from Pact Broker)
      pactUrls: [
        path.resolve(
          __dirname,
          '../../../../pact/pacts/example project-mobile-app-example project-workers-api.json'
        ),
      ],

      // Provider states: seed the D1 test database for each state
      stateHandlers: {
        'at least one published event exists': async () => {
          // Insert a seed row via the Worker's internal test endpoint
          // (only available when ENVIRONMENT=test)
          const res = await fetch(
            `http://127.0.0.1:${worker.port}/__test/seed/events`,
            { method: 'POST' }
          );
          if (!res.ok) throw new Error('Seed failed: ' + res.status);
        },
        'no events exist': async () => {
          const res = await fetch(
            `http://127.0.0.1:${worker.port}/__test/seed/clear`,
            { method: 'POST' }
          );
          if (!res.ok) throw new Error('Clear failed: ' + res.status);
        },
      },

      publishVerificationResult: process.env.CI === 'true',
      providerVersion:           process.env.GITHUB_SHA ?? 'local',
      logLevel:                  'warn',
    };

    return new Verifier(opts).verifyProvider();
  }, 60_000);
});
```

## Pact Broker Integration

Use PactFlow (hosted Pact Broker) or a self-hosted Broker to
share Pact files between the mobile CI pipeline and the Workers
CI pipeline without committing them to the repository.

```ts
// pact.config.ts — shared broker config
export const BROKER_CONFIG = {
  pactBrokerUrl:      process.env.PACT_BROKER_BASE_URL!,
  pactBrokerToken:    process.env.PACT_BROKER_TOKEN!,
  consumerVersion:    process.env.GITHUB_SHA ?? 'local',
  publishVerificationResult: process.env.CI === 'true',
};
```

Consumer publish step (runs in mobile CI after tests pass):

```bash
npx pact-broker publish pact/pacts/ \
  --broker-base-url  "$PACT_BROKER_BASE_URL" \
  --broker-token     "$PACT_BROKER_TOKEN" \
  --consumer-app-version "$GITHUB_SHA" \
  --tag "$(git rev-parse --abbrev-ref HEAD)"
```

## CI Integration

```yaml
# .github/workflows/pact.yml
name: Contract tests
on:
  push:
    branches: ['**']

jobs:
  consumer:
    name: Consumer — mobile Pact generation
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22' }
      - run: npm ci
      - name: Generate Pact files
        run: npx vitest run apps/mobile/src/__tests__/pact
      - name: Publish to Pact Broker
        env:
          PACT_BROKER_BASE_URL: ${{ vars.PACT_BROKER_BASE_URL }}
          PACT_BROKER_TOKEN:    ${{ secrets.PACT_BROKER_TOKEN }}
        run: |
          npx pact-broker publish pact/pacts/ \
            --broker-base-url  "$PACT_BROKER_BASE_URL" \
            --broker-token     "$PACT_BROKER_TOKEN" \
            --consumer-app-version "$GITHUB_SHA" \
            --tag "${{ github.ref_name }}"

  provider:
    name: Provider — Workers verification
    runs-on: ubuntu-latest
    needs: consumer
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22' }
      - run: npm ci
      - name: Verify provider against Pact Broker
        env:
          PACT_BROKER_BASE_URL: ${{ vars.PACT_BROKER_BASE_URL }}
          PACT_BROKER_TOKEN:    ${{ secrets.PACT_BROKER_TOKEN }}
          GITHUB_SHA:           ${{ github.sha }}
          CI: 'true'
        run: npx vitest run workers/api/__tests__/pact
```

## Mobile vs Desktop Contract Differences

The mobile app and a hypothetical desktop web app may need
different response shapes. Pact handles this via separate
consumer names and separate Pact files:

| Consumer | Pact file | Unique fields |
|----------|-----------|---------------|
| `example project-mobile-app` | `example project-mobile-app-example project-workers-api.json` | `imageUrl`, `x-client-platform` |
| `example project-web-app` | `example project-web-app-example project-workers-api.json` | `embedHtml`, full `venue` object |

The provider verification job downloads and verifies all
consumer Pacts, ensuring a single Worker change cannot
break either consumer silently.

## Anti-patterns

- Writing provider tests that re-implement the consumer tests —
  the consumer writes the contract; the provider only verifies it.
  If the provider team writes Pact interactions themselves, the
  contract is no longer consumer-driven.
- Using Pact to test business logic — Pact tests structure and
  existence of fields, not business rules. Use unit tests for
  logic; use Pact for API shape stability.
- Committing generated Pact JSON files to the repository without
  a Broker — they will drift out of sync and developers will
  forget to regenerate them.
- Skipping provider state handlers — returning an empty database
  state for an interaction that expects data causes false
  verification passes when the Worker happens to return an empty
  list rather than the expected response.
- Verifying against a mocked Worker — the `stateHandlers` must
  run against a real Wrangler dev instance; a Jest mock of the
  Worker cannot reveal actual D1 schema regressions.

## Gotchas

- `unstable_dev` from Wrangler binds to a random port by default.
  Read `worker.port` after `await unstable_dev(...)` rather than
  hard-coding a port in the Verifier URL.
- Pact `eachLike` asserts that the array contains at least one
  item matching the template; it does not assert the exact count.
  Use `atLeastLike(n, template)` when a minimum count matters.
- Provider state handlers run before each interaction in the Pact
  file. If state handlers share database rows, later interactions
  may see data inserted by earlier state handlers. Use `clear`
  at the start of each handler.
- `publishVerificationResult: true` should only be set in CI —
  publishing from a local machine with a dirty working tree
  associates a verification result with the wrong commit SHA.

## Verification

```bash
# Generate Pact file locally
npx vitest run apps/mobile/src/__tests__/pact
ls pact/pacts/

# Verify provider locally (reads local Pact file)
npx vitest run workers/api/__tests__/pact

# Check Pact Broker for the latest verification status
npx pact-broker can-i-deploy \
  --pacticipant example project-mobile-app \
  --version "$GITHUB_SHA" \
  --to-environment staging \
  --broker-base-url "$PACT_BROKER_BASE_URL" \
  --broker-token "$PACT_BROKER_TOKEN"
```

## Related

- `testing/consumer-driven-contracts.md`
- `testing/contract-testing-pact.md`
- `testing/contract-testing-pact-patterns.md`
- `testing/api-contract-testing-schema-validation.md`
- `testing/miniflare-d1-integration-testing.md`

## Source URLs (verified 2026-08-22)

- https://docs.pact.io/implementation_guides/javascript/docs/provider
- https://docs.pact.io/implementation_guides/javascript/docs/consumer
- https://docs.pact.io/pact_broker/can_i_deploy
- https://developers.cloudflare.com/workers/wrangler/api/#unstable_dev
