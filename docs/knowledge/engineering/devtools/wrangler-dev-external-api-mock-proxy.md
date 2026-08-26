# Mocking External API Calls in `wrangler dev` Local Development

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker calls an external payment gateway, shipping API, or third-party SaaS. During local development with `wrangler dev`, you do not want to hit live endpoints — both to avoid side-effects and to work offline. You need a way to point the Worker at a local mock server without changing source code.

## Context

`wrangler dev` runs the Worker in a local Miniflare-backed process. Its `--var KEY:VALUE` flag overrides any `[vars]` entry in `wrangler.toml` for that dev session only, without touching the file. The trick is to store the external API base URL in a `var` (e.g., `PAYMENT_API_URL`) and override it at the command line to point at a local mock server.

This pattern composes well: the same mock fixtures can be shared between `wrangler dev` and Vitest unit tests, giving you a single fixture source of truth.

## Local Mock Server Setup

```typescript
// mocks/payment-server.ts — a plain Node.js HTTP server used as the mock
import * as http from 'node:http';
import * as fs from 'node:fs';
import * as path from 'node:path';

// Load fixtures from JSON files — shared with Vitest tests
const fixtures: Record<string, unknown> = {
  '/v1/charges': JSON.parse(
    fs.readFileSync(path.join(__dirname, 'fixtures/charge-success.json'), 'utf8')
  ),
  '/v1/charges/fail': JSON.parse(
    fs.readFileSync(path.join(__dirname, 'fixtures/charge-failure.json'), 'utf8')
  ),
  '/v1/payment_intents': JSON.parse(
    fs.readFileSync(path.join(__dirname, 'fixtures/payment-intent.json'), 'utf8')
  ),
};

const server = http.createServer((req, res) => {
  const url = new URL(req.url ?? '/', `http://localhost`);
  const fixture = fixtures[url.pathname];

  if (!fixture) {
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: `No mock for ${url.pathname}` }));
    return;
  }

  console.log(`[mock] ${req.method} ${url.pathname}`);
  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(fixture));
});

const PORT = parseInt(process.env.MOCK_PORT ?? '9090', 10);
server.listen(PORT, () => {
  console.log(`Mock payment API listening on http://localhost:${PORT}`);
});

// mocks/fixtures/charge-success.json
// {
//   "id": "ch_mock_001",
//   "status": "succeeded",
//   "amount": 2000,
//   "currency": "usd"
// }
```

```bash
# Start the mock server in one terminal
node --loader ts-node/esm mocks/payment-server.ts
# Mock payment API listening on http://localhost:9090

# Start wrangler dev in another terminal, overriding the URL var
npx wrangler dev \
  --var PAYMENT_API_URL:http://localhost:9090 \
  --var PAYMENT_API_KEY:mock-key-local

# All fetch() calls in the Worker to PAYMENT_API_URL now hit the local mock
```

## Worker Code That Reads the URL from Env

```typescript
// src/index.ts
export interface Env {
  PAYMENT_API_URL: string; // https://api.stripe.com in production
  PAYMENT_API_KEY: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== 'POST' || new URL(request.url).pathname !== '/charge') {
      return new Response('Not found', { status: 404 });
    }

    const body = await request.json<{ amount: number; currency: string }>();

    // Uses env.PAYMENT_API_URL — overridable via --var in wrangler dev
    const response = await fetch(`${env.PAYMENT_API_URL}/v1/charges`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.PAYMENT_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    const charge = await response.json();
    return Response.json(charge, { status: response.status });
  },
};
```

## Sharing Fixtures with Vitest Unit Tests

```typescript
// src/__tests__/charge.test.ts
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { env } from 'cloudflare:test';
import * as http from 'node:http';
import * as fs from 'node:fs';
import worker from '../index';

let mockServer: http.Server;
let mockPort: number;

beforeAll(async () => {
  // Spin up the same mock server used in wrangler dev
  const fixture = JSON.parse(
    fs.readFileSync('mocks/fixtures/charge-success.json', 'utf8')
  );
  mockServer = http.createServer((_req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(fixture));
  });
  await new Promise<void>(resolve => mockServer.listen(0, resolve));
  mockPort = (mockServer.address() as { port: number }).port;
});

afterAll(async () => {
  await new Promise<void>((resolve, reject) =>
    mockServer.close(err => err ? reject(err) : resolve())
  );
});

describe('POST /charge', () => {
  it('returns succeeded charge from mock', async () => {
    const testEnv = {
      ...env,
      PAYMENT_API_URL: `http://localhost:${mockPort}`,
      PAYMENT_API_KEY: 'mock-key',
    };

    const request = new Request('https://example.com/charge', {
      method: 'POST',
      body: JSON.stringify({ amount: 2000, currency: 'usd' }),
      headers: { 'Content-Type': 'application/json' },
    });

    const ctx = { waitUntil: () => {}, passThroughOnException: () => {} } as unknown as ExecutionContext;
    const response = await worker.fetch(request, testEnv as any, ctx);

    expect(response.status).toBe(200);
    const body = await response.json<{ status: string }>();
    expect(body.status).toBe('succeeded');
  });
});
```

## Using MSW (Mock Service Worker) as an Alternative

```typescript
// vitest.setup.ts — MSW intercepts fetch() calls inside the test process
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import chargeSuccess from './mocks/fixtures/charge-success.json';

export const mockServer = setupServer(
  http.post('https://api.stripe.com/v1/charges', () =>
    HttpResponse.json(chargeSuccess)
  ),
  http.post('http://localhost:9090/v1/charges', () =>
    HttpResponse.json(chargeSuccess)
  ),
);

beforeAll(() => mockServer.listen({ onUnhandledRequest: 'error' }));
afterEach(() => mockServer.resetHandlers());
afterAll(() => mockServer.close());
```

## The `--remote` Flag

```bash
# Test against live Cloudflare infrastructure (not local Miniflare)
# Useful for verifying behavior that Miniflare does not accurately emulate
# (e.g., Durable Object consistency, KV global replication)
npx wrangler dev --remote

# CAUTION: --remote with --var still overrides vars, but requests go to
# Cloudflare edge — you may incur real costs and hit production dependencies
# if not careful. Only use with a dedicated development Worker name.
npx wrangler dev --remote \
  --name api-worker-dev \
  --var PAYMENT_API_URL:https://sandbox.payment-provider.com
```

## Anti-patterns

- **Hardcoding `http://localhost:9090` in source code.** The URL must come from `env.PAYMENT_API_URL` so production uses the real endpoint without code changes.
- **Running `wrangler dev` with `--remote` against a production-named Worker.** Remote dev mode deploys a temporary version to Cloudflare. Using the production Worker name risks serving the dev version to real traffic during the session.
- **Mocking `fetch` globally in Vitest with `vi.mock`.** This bypasses the Workers runtime semantics. Prefer a real HTTP server or MSW node adapter so the Worker's actual `fetch()` call goes through the full request/response cycle.
- **Different fixture files for dev and tests.** Fixture drift causes tests to pass while the dev mock diverges from reality. Keep one canonical `mocks/fixtures/` directory.

## Gotchas

- `--var KEY:VALUE` values are **strings**. Boolean and numeric `vars` in `wrangler.toml` are also strings at runtime, so `env.RETRY_COUNT` is `"3"`, not `3`. Parse explicitly: `parseInt(env.RETRY_COUNT, 10)`.
- Miniflare (local mode) blocks outbound `fetch()` to non-localhost hosts by default in some versions. If the Worker calls a host that is not the mock, you will get a network error. Use `--local-protocol https` and configure trusted hosts if needed.
- The mock server runs in Node.js but the Worker runs in V8 isolate — they cannot share in-process memory. Use the HTTP protocol or a shared SQLite file (via Miniflare's `d1Persist`) to exchange state between them.
- When the Worker uses `PAYMENT_API_URL` as a base for multiple endpoints, ensure the mock handles all paths the Worker may call during a dev session, or it will 404 unexpectedly.

## Verification

```bash
# With both the mock server and wrangler dev running:
curl -X POST http://localhost:8787/charge \
  -H 'Content-Type: application/json' \
  -d '{"amount": 2000, "currency": "usd"}'
# Expected: {"id":"ch_mock_001","status":"succeeded",...}

# Check mock server log shows the intercepted call
# [mock] POST /v1/charges
```

## Related

- `vitest-workers-env-type-generation.md` — typed `Env` for the Worker under test
- `wrangler-secret-bulk-import-workers.md` — setting production API keys as secrets
- `workers-opentelemetry-otlp-export.md` — tracing real vs. mock API calls

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://developers.cloudflare.com/workers/testing/local-development/
- https://mswjs.io/docs/integrations/node
- https://miniflare.dev/
