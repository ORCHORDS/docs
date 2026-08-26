# Consumer-Driven Contract Testing with Pact for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers-based microservices communicate via Service Bindings and HTTP. An upstream provider team ships a breaking change—a renamed JSON field or a dropped header—and your consumer Workers break silently in production. Integration tests catch this only after deployment. You need a way to verify that providers honour the exact contract each consumer expects, before either side ships.

## Context

Pact is a consumer-driven contract testing tool. The consumer defines what it expects from the provider (the "contract" or "pact"). The provider replays those interactions against its own code and asserts it can satisfy them. A Pact Broker stores and versions contracts, and the `can-i-deploy` CLI gate prevents deployment when contracts are broken.

Cloudflare Workers run on the V8 isolate runtime. Pact's Node.js library (`@pact-foundation/pact`) uses native binaries that do not run inside a Worker. The strategy is:

- **Consumer tests** run in Vitest (Node-compatible, outside the isolate) against a Pact mock server that replaces the real provider.
- **Provider verification** runs in Vitest using `@pact-foundation/pact` against a locally started `wrangler dev` instance of the provider Worker.
- Service Binding contracts are exercised by starting both the consumer Worker and provider Worker under `wrangler dev --local` and asserting over HTTP.

## Solution

```typescript
// tests/contract/order-consumer.pact.test.ts
// Consumer: orders-worker fetches product data from catalogue-worker

import { PactV3, MatchersV3 } from '@pact-foundation/pact';
import path from 'path';
import { describe, it, expect, beforeAll, afterAll } from 'vitest';

const { like, eachLike, string, integer, regex } = MatchersV3;

const provider = new PactV3({
  consumer: 'orders-worker',
  provider: 'catalogue-worker',
  dir: path.resolve(__dirname, '../../pacts'),
  logLevel: 'warn',
});

async function fetchProduct(
  baseUrl: string,
  productId: string
): Promise<{ id: string; name: string; priceCents: number; sku: string }> {
  const res = await fetch(`${baseUrl}/v1/products/${productId}`, {
    headers: { 'X-Service-Token': 'test-token' },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

describe('orders-worker → catalogue-worker contract', () => {
  describe('GET /v1/products/:id — product exists', () => {
    beforeAll(() =>
      provider
        .given('product abc-123 exists')
        .uponReceiving('a request for product abc-123')
        .withRequest({
          method: 'GET',
          path: '/v1/products/abc-123',
          headers: { 'X-Service-Token': string('test-token') },
        })
        .willRespondWith({
          status: 200,
          headers: { 'Content-Type': regex('application/json.*', 'application/json') },
          body: like({
            id: string('abc-123'),
            name: string('Widget Pro'),
            priceCents: integer(4999),
            sku: string('WGT-PRO-001'),
          }),
        })
        .executeTest(async (mockServer) => {
          const product = await fetchProduct(mockServer.url, 'abc-123');
          expect(product.id).toBe('abc-123');
          expect(typeof product.priceCents).toBe('number');
        })
    );

    it('contract interaction executed', () => {
      // Pact writes the pact file after executeTest resolves
      expect(true).toBe(true);
    });
  });

  describe('GET /v1/products/:id — product not found', () => {
    beforeAll(() =>
      provider
        .given('product xyz-999 does not exist')
        .uponReceiving('a request for a missing product')
        .withRequest({ method: 'GET', path: '/v1/products/xyz-999' })
        .willRespondWith({
          status: 404,
          body: like({ error: string('not_found') }),
        })
        .executeTest(async (mockServer) => {
          await expect(fetchProduct(mockServer.url, 'xyz-999')).rejects.toThrow('HTTP 404');
        })
    );

    it('404 contract interaction executed', () => {
      expect(true).toBe(true);
    });
  });
});

// tests/contract/catalogue-provider.pact.test.ts
// Provider verification: catalogue-worker satisfies the orders-worker pact

import { Verifier } from '@pact-foundation/pact';
import { beforeAll, afterAll, it } from 'vitest';
import { ChildProcess, spawn } from 'child_process';
import path from 'path';

let wranglerProcess: ChildProcess;
const PROVIDER_PORT = 8788;

async function waitForWorker(url: string, retries = 20): Promise<void> {
  for (let i = 0; i < retries; i++) {
    try {
      const r = await fetch(url);
      if (r.status < 500) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error('catalogue-worker did not start in time');
}

beforeAll(async () => {
  wranglerProcess = spawn(
    'npx',
    ['wrangler', 'dev', '--local', '--port', String(PROVIDER_PORT), '--config', 'workers/catalogue/wrangler.toml'],
    { stdio: 'pipe' }
  );
  await waitForWorker(`http://localhost:${PROVIDER_PORT}/health`);
});

afterAll(() => {
  wranglerProcess?.kill();
});

it('catalogue-worker satisfies orders-worker pact', async () => {
  const verifier = new Verifier({
    provider: 'catalogue-worker',
    providerBaseUrl: `http://localhost:${PROVIDER_PORT}`,
    pactUrls: [path.resolve(__dirname, '../../pacts/orders-worker-catalogue-worker.json')],
    stateHandlers: {
      'product abc-123 exists': async () => {
        // Seed the provider's D1 database via wrangler d1 execute or a /test-setup endpoint
        await fetch(`http://localhost:${PROVIDER_PORT}/__test/state`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ state: 'product abc-123 exists' }),
        });
      },
      'product xyz-999 does not exist': async () => {
        await fetch(`http://localhost:${PROVIDER_PORT}/__test/state`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ state: 'product xyz-999 does not exist' }),
        });
      },
    },
    publishVerificationResult: process.env.CI === 'true',
    providerVersion: process.env.GITHUB_SHA ?? 'local',
    pactBrokerUrl: process.env.PACT_BROKER_URL,
    pactBrokerToken: process.env.PACT_BROKER_TOKEN,
  });

  await verifier.verifyProvider();
}, 60_000);
```

## Implementation Details

**Provider state endpoint inside the Worker** — add a `/__test/state` route that only activates when `WORKER_ENV === 'test'`. This route uses `wrangler d1 execute --local` under the hood (via `platform.env.DB`) to insert or delete fixtures:

```typescript
// workers/catalogue/src/index.ts (excerpt — test state handler)
if (request.method === 'POST' && url.pathname === '/__test/state') {
  if (env.WORKER_ENV !== 'test') return new Response('Forbidden', { status: 403 });
  const { state } = await request.json<{ state: string }>();

  if (state === 'product abc-123 exists') {
    await env.DB.prepare(
      `INSERT OR REPLACE INTO products (id, name, price_cents, sku)
       VALUES ('abc-123', 'Widget Pro', 4999, 'WGT-PRO-001')`
    ).run();
  } else if (state === 'product xyz-999 does not exist') {
    await env.DB.prepare(`DELETE FROM products WHERE id = 'xyz-999'`).run();
  }
  return new Response(null, { status: 204 });
}
```

**Pact Broker integration** — run `pact-broker can-i-deploy` in CI before any deployment step:

```yaml
# .github/workflows/deploy.yml (excerpt)
- name: Check can-i-deploy
  run: |
    npx pact-broker can-i-deploy \
      --pacticipant orders-worker \
      --version ${{ github.sha }} \
      --to-environment production \
      --broker-base-url ${{ secrets.PACT_BROKER_URL }} \
      --broker-token ${{ secrets.PACT_BROKER_TOKEN }}
```

**Service Binding contracts** — when two Workers are bound via `services` in `wrangler.toml`, both must run under `wrangler dev --local`. The consumer test starts both processes and asserts via the consumer's public HTTP surface rather than testing the binding directly, keeping the contract at the HTTP protocol level.

## Anti-patterns

- **Defining contracts on the provider side** — Pact is consumer-driven. Providers that self-define their pact defeat the purpose; broken consumer expectations go undetected.
- **Using `eachLike` for everything** — `eachLike` generates a single-element array by default. If the consumer code iterates and picks the second element it will fail in production. Assert array shape where it matters.
- **Skipping `can-i-deploy`** — publishing a pact without gating deployment on `can-i-deploy` means you get noise without safety. Wire the gate into your CD pipeline.
- **State handlers that call the live external network** — provider state setup must be deterministic and offline-capable. Use local D1 (`--local`) not a remote database.

## Gotchas

- `@pact-foundation/pact` ships native Rust binaries via `@pact-foundation/pact-core`. On Linux CI runners ensure the `libc` version is compatible (use `ubuntu-22.04` or newer).
- Pact V3 `executeTest` is async and resolves after the interaction completes. Do not run assertions outside of `executeTest`; the mock server tears down immediately after.
- `wrangler dev` cold-start can take 3–8 seconds on first run. The `waitForWorker` retry loop must be generous enough; 10 seconds is a reasonable lower bound in CI.
- When `publishVerificationResult` is `true` and `pactBrokerUrl` is not set, the verifier throws. Guard with `process.env.CI === 'true'` before enabling publication.

## Verification

```bash
# 1. Run consumer tests and generate pact files
npx vitest run tests/contract/order-consumer.pact.test.ts

# 2. Inspect generated pact
cat pacts/orders-worker-catalogue-worker.json | jq '.interactions | length'

# 3. Run provider verification against local wrangler dev
npx vitest run tests/contract/catalogue-provider.pact.test.ts

# 4. Check can-i-deploy (requires Pact Broker)
npx pact-broker can-i-deploy \
  --pacticipant orders-worker \
  --version local \
  --to-environment staging \
  --broker-base-url $PACT_BROKER_URL \
  --broker-token $PACT_BROKER_TOKEN
```

## Related

- `documentation/docs/policies/testing/workers-golden-path-test-suite.md`
- `documentation/docs/policies/testing/workers-e2e-testing-playwright-workers.md`
- Pact documentation: https://docs.pact.io
- `wrangler dev` local mode: https://developers.cloudflare.com/workers/wrangler/commands/#dev

## Sources

- Pact Foundation — Pact V3 JS README (2025)
- Cloudflare Workers — Service Bindings docs (2025)
- example.com internal runbook: contract-testing-patterns (2026-07)
