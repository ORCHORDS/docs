# Contract Testing Between Cloudflare Workers and React Native Clients

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Your React Native (Expo) app communicates with a set of Cloudflare Workers APIs. A Worker
maintainer renames a JSON field from `itemId` to `id`; the mobile client breaks silently in
production because the API has no typed contract and the React Native team only discovers the
regression after App Store review. You need a consumer-driven contract test that:

1. The React Native team authors — describing exactly what response shapes their code depends on.
2. The Workers team can verify locally and in CI before merging any change.
3. Does not require both teams to coordinate deployment timing.

## Context

Consumer-Driven Contract Testing (CDCT) uses Pact. The **consumer** (React Native app) generates
a JSON **pact file** describing the interactions it expects. The **provider** (Cloudflare Worker)
verifies the pact file against its actual implementation — no live coordination needed.

Special considerations for this stack:

- React Native tests run in a Jest/jsdom environment (or a native test runner). The Pact
  consumer library `@pact-foundation/pact` works in Jest.
- Cloudflare Workers cannot be verified by the standard Node-based Pact provider verifier
  directly because Workers run in the V8 isolate, not Node. The workaround is to run the
  Worker locally with `wrangler dev --local` and point the Pact verifier at
  `http://localhost:8787`.
- Pact files are shared via a **PactFlow** broker (hosted) or a self-hosted
  `pact-broker` instance in Docker.

Stack: React Native (Expo SDK 52), Pact JS v13, Cloudflare Workers (Wrangler 4),
PactFlow / pact-broker, GitHub Actions.

---

## Consumer Side: React Native Pact Tests

Install dependencies in the React Native workspace:

```bash
pnpm add -D @pact-foundation/pact
```

### Consumer contract test

```ts
// apps/mobile/__tests__/pact/search.pact.test.ts
import { Pact, Matchers } from '@pact-foundation/pact';
import path from 'node:path';

const { like, eachLike, string, integer } = Matchers;

// Pact mock server runs on a local port during tests.
const provider = new Pact({
  consumer: 'OrchordsApp',
  provider: 'OrchordsSearchWorker',
  // Pact files are written here; committed or published to broker.
  dir: path.resolve(__dirname, '../../pacts'),
  port: 4000,
  log: path.resolve(__dirname, '../../logs/pact.log'),
  logLevel: 'warn',
});

describe('OrchordsApp → OrchordsSearchWorker contract', () => {
  beforeAll(() => provider.setup());
  afterAll(() => provider.finalize());
  afterEach(() => provider.verify());

  describe('GET /v1/search', () => {
    beforeEach(() =>
      provider.addInteraction({
        state: 'there are matching items for "guitar"',
        uponReceiving: 'a search request with query "guitar"',
        withRequest: {
          method: 'GET',
          path: '/v1/search',
          query: { q: 'guitar', limit: '10' },
          headers: {
            Accept: 'application/json',
            Authorization: string('Bearer some-token'),
          },
        },
        willRespondWith: {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
          body: {
            // The app only reads these three fields from each item.
            // Pact records exactly what the consumer uses, nothing more.
            items: eachLike({
              id:        string('item-123'),
              name:      string('Fender Stratocaster'),
              priceUsd:  integer(1299),
            }),
            total: integer(42),
            cursor: like('eyJwYWdlIjoxfQ=='),
          },
        },
      }),
    );

    it('maps search response to SearchResult[]', async () => {
      // Import the actual client code used in production.
      const { searchItems } = await import('../../src/api/searchClient');

      // Point the client at the Pact mock server.
      const client = searchItems({ baseUrl: 'http://localhost:4000' });

      const results = await client.search({ q: 'guitar', limit: 10 });

      expect(results.items).toHaveLength(1);
      expect(results.items[0]).toMatchObject({
        id: expect.any(String),
        name: expect.any(String),
        priceUsd: expect.any(Number),
      });
      expect(results.total).toBeGreaterThan(0);
    });
  });

  describe('GET /v1/items/:id', () => {
    beforeEach(() =>
      provider.addInteraction({
        state: 'item item-123 exists',
        uponReceiving: 'a request for item detail item-123',
        withRequest: {
          method: 'GET',
          path: '/v1/items/item-123',
          headers: { Authorization: string('Bearer some-token') },
        },
        willRespondWith: {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
          body: like({
            id:          'item-123',
            name:        'Fender Stratocaster',
            description: 'Electric guitar',
            priceUsd:    1299,
            stock:       5,
            images:      eachLike({ url: string('https://cdn.example.com/img.jpg') }),
          }),
        },
      }),
    );

    it('maps item detail to ItemDetail type', async () => {
      const { getItem } = await import('../../src/api/itemClient');
      const client = getItem({ baseUrl: 'http://localhost:4000' });

      const item = await client.fetchItem('item-123');

      expect(item.id).toBe('item-123');
      expect(item.images.length).toBeGreaterThan(0);
      expect(item.images[0].url).toMatch(/^https:/);
    });
  });
});
```

### jest configuration for Pact tests

```js
// apps/mobile/jest.pact.config.js
/** @type {import('jest').Config} */
module.exports = {
  displayName: 'pact',
  testEnvironment: 'node',       // Pact runs a local HTTP server; needs Node env.
  testMatch: ['**/__tests__/pact/**/*.test.ts'],
  transform: {
    '^.+\\.tsx?$': ['ts-jest', { tsconfig: 'tsconfig.json' }],
  },
  // Run serially — Pact mock server is bound to a fixed port.
  maxWorkers: 1,
  testTimeout: 30_000,
};
```

---

## Publishing the Pact to the Broker

```bash
# apps/mobile/package.json scripts
"pact:publish": "pact-broker publish ./pacts \
  --broker-base-url $PACT_BROKER_URL \
  --broker-token $PACT_BROKER_TOKEN \
  --consumer-app-version $(git rev-parse --short HEAD) \
  --tag $(git rev-parse --abbrev-ref HEAD)"
```

In CI (consumer side):

```yaml
# .github/workflows/mobile-ci.yml (excerpt)
- name: Run Pact consumer tests
  run: pnpm --filter @example-org/example-repo test:pact
  env:
    PACT_BROKER_URL: ${{ vars.PACT_BROKER_URL }}

- name: Publish pacts to broker
  run: pnpm --filter @example-org/example-repo pact:publish
  env:
    PACT_BROKER_URL: ${{ vars.PACT_BROKER_URL }}
    PACT_BROKER_TOKEN: ${{ secrets.PACT_BROKER_TOKEN }}
```

---

## Provider Side: Verifying the Worker

The Workers provider verification:
1. Starts `wrangler dev --local` on port 8787.
2. Runs `@pact-foundation/pact`'s provider verifier pointed at `http://localhost:8787`.
3. Sets up provider states (seeding D1 or KV fixtures) before each interaction.

### Provider state handler (separate Node process)

Because the state handler needs to call D1 directly (which only exists in the Wrangler local
environment), it is injected via Wrangler's `--state-handler` support or a lightweight Express
state-handler proxy that the verifier contacts.

```ts
// workers/search/test/pact/provider-state-handler.ts
import express from 'express';
import { execSync } from 'node:child_process';

const app = express();
app.use(express.json());

/**
 * Pact verifier calls POST /_pact/provider-states with the state name
 * before replaying each interaction against the real Worker.
 */
app.post('/_pact/provider-states', async (req, res) => {
  const { state, params } = req.body as { state: string; params?: Record<string, unknown> };

  try {
    switch (state) {
      case 'there are matching items for "guitar"':
        // Seed wrangler's local D1 with test data.
        execSync(
          `wrangler d1 execute DB --local --command \
            "INSERT OR REPLACE INTO items (id,name,price_usd) VALUES ('item-123','Fender Stratocaster',1299)"`,
          { cwd: process.cwd(), stdio: 'ignore' },
        );
        break;

      case 'item item-123 exists':
        execSync(
          `wrangler d1 execute DB --local --command \
            "INSERT OR REPLACE INTO items (id,name,description,price_usd,stock) \
             VALUES ('item-123','Fender Stratocaster','Electric guitar',1299,5)"`,
          { cwd: process.cwd(), stdio: 'ignore' },
        );
        break;

      default:
        console.warn(`Unknown provider state: "${state}"`);
    }
    res.json({ result: 'success' });
  } catch (err) {
    console.error(err);
    res.status(500).json({ result: 'error', error: String(err) });
  }
});

app.listen(9999, () => console.log('State handler on :9999'));
```

### Provider verification test

```ts
// workers/search/test/pact/verify.test.ts
import { Verifier } from '@pact-foundation/pact';
import path from 'node:path';

/**
 * Prerequisite: wrangler dev --local is running on :8787
 * and the state handler is running on :9999.
 * Both are started by the CI job before this test runs.
 */
describe('OrchordsSearchWorker pact verification', () => {
  it('satisfies all consumer contracts', async () => {
    const output = await new Verifier({
      providerBaseUrl: 'http://localhost:8787',
      // Fetch pacts from broker, or use local files during development.
      pactBrokerUrl: process.env.PACT_BROKER_URL,
      pactBrokerToken: process.env.PACT_BROKER_TOKEN,
      provider: 'OrchordsSearchWorker',
      providerVersion: process.env.GITHUB_SHA ?? 'local',
      // State setup endpoint — a separate Express server started before tests.
      providerStatesSetupUrl: 'http://localhost:9999/_pact/provider-states',
      publishVerificationResult: !!process.env.CI,
      enablePending: true,   // New unverified pacts don't fail the build yet.
      includeWipPactsSince: '2026-01-01',
    }).verifyProvider();

    console.log(output);
  }, 120_000);
});
```

### Provider CI job

```yaml
# .github/workflows/workers-ci.yml (excerpt)
- name: Start wrangler dev
  run: |
    npx wrangler dev --local --port 8787 &
    # Wait for Worker to be ready.
    timeout 30 bash -c 'until curl -sf http://localhost:8787/health; do sleep 1; done'
  working-directory: workers/search

- name: Start provider state handler
  run: npx ts-node test/pact/provider-state-handler.ts &
  working-directory: workers/search

- name: Verify pacts
  run: pnpm --filter @example-org/example-repo test:pact:verify
  env:
    PACT_BROKER_URL: ${{ vars.PACT_BROKER_URL }}
    PACT_BROKER_TOKEN: ${{ secrets.PACT_BROKER_TOKEN }}
    GITHUB_SHA: ${{ github.sha }}
```

---

## Can-I-Deploy Gate

Before deploying either side, check the broker's compatibility matrix:

```yaml
- name: Can I deploy Worker?
  run: |
    npx pact-broker can-i-deploy \
      --broker-base-url "$PACT_BROKER_URL" \
      --broker-token "$PACT_BROKER_TOKEN" \
      --pacticipant OrchordsSearchWorker \
      --version "$GITHUB_SHA" \
      --to-environment production
  env:
    PACT_BROKER_URL: ${{ vars.PACT_BROKER_URL }}
    PACT_BROKER_TOKEN: ${{ secrets.PACT_BROKER_TOKEN }}
```

---

## Anti-patterns

**Writing the pact on the provider side.**
The value of CDCT is that the consumer defines what it needs. A provider-authored pact silently
over-specifies the contract; changes that don't affect the consumer still fail the test.

**Using `string()` matcher for numeric fields.**
The React Native client may parse `priceUsd` as a string if the Pact interaction uses
`string()`. Use `integer()` or `decimal()` so type mismatches are caught at contract level,
not at runtime on a user's device.

**Skipping `enablePending: true` in early adoption.**
Without pending pacts, a consumer can publish a new interaction before the provider has a chance
to implement it, breaking the provider CI. Enable pending pacts and `includeWipPactsSince` to
allow consumers to publish optimistically.

**Running the provider state handler in the same process as the Worker.**
The Worker runs in a Wrangler V8 isolate; the state handler needs Node APIs (`child_process`,
file system) to seed D1. Keep them as separate processes.

---

## Gotchas

- **Wrangler local D1 is not shared between processes** — the state handler must use
  `wrangler d1 execute --local` (which Wrangler persists to `.wrangler/state/`) rather than a
  direct SQLite connection, or the Worker will not see the seeded data.

- **Auth headers in Pact interactions** — Pact records the `Authorization` header. In tests,
  use `string()` matcher so any valid token matches, not a literal value that expires.

- **React Native uses a bundler (Metro/Hermes)** — the Pact consumer tests must run in a
  Node Jest environment, not in the Hermes runtime. Keep pact tests separate from component
  tests that run via Expo's Jest preset.

- **Multiple Workers, one consumer** — use separate `provider` names per Worker
  (`OrchordsSearchWorker`, `OrchordsCartWorker`) and a separate pact file per provider.
  The broker tracks them independently.

---

## Verification

```bash
# Consumer: generate pact files.
pnpm --filter @example-org/example-repo test:pact
ls apps/mobile/pacts/
# Should see: OrchordsApp-OrchordsSearchWorker.json

# Inspect the pact file structure.
cat apps/mobile/pacts/OrchordsApp-OrchordsSearchWorker.json | jq '.interactions[].description'

# Provider: start wrangler and state handler, then verify.
cd workers/search
npx wrangler dev --local --port 8787 &
npx ts-node test/pact/provider-state-handler.ts &
sleep 5
pnpm test:pact:verify

# Broker: check can-i-deploy.
npx pact-broker can-i-deploy \
  --pacticipant OrchordsSearchWorker \
  --version local \
  --to-environment staging
```

---

## Related

- `contract-testing-pact-workers-api.md`
- `api-contract-testing-pact-workers.md`
- `consumer-driven-contracts.md`
- `detox-react-native-e2e.md`
- `test-doubles-cloudflare-workers.md`

## Sources

- Pact JS documentation: https://docs.pact.io/implementation_guides/javascript
- PactFlow can-i-deploy: https://docs.pact.io/pact_broker/can_i_deploy
- Wrangler local development: https://developers.cloudflare.com/workers/wrangler/commands/#dev
- Pact pending pacts: https://docs.pact.io/pact_broker/advanced_topics/pending_pacts
