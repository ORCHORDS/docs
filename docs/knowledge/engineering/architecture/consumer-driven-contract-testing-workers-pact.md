# Consumer-Driven Contract Testing for Cloudflare Workers (Pact)

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a graph of Cloudflare Workers communicating via service bindings or HTTP. After a
provider Worker changes its response shape, consumer Workers break in production — but all
unit tests pass because each Worker is tested in isolation with mocked dependencies.
Integration tests catch this, but they are slow, flaky, and cannot be run in CI for every
PR.

Consumer-Driven Contract (CDC) testing with Pact solves this: the consumer defines a
contract (the exact requests it sends and the response shape it expects), publishes it to a
broker, and the provider verifies it in its own CI pipeline. Breakages are caught before
either side deploys.

---

## Context

Pact is the dominant CDC testing framework. It works in two stages:

1. **Consumer test** — the consumer runs tests against a Pact mock server. Pact records the
   interactions as a JSON contract file (the "pact").
2. **Provider verification** — the provider replays the recorded requests against its actual
   implementation and checks that responses match the consumer's expectations.

Workers are TypeScript processes at their core; Pact's JS/TS SDK works in Node.js test
runners (Vitest, Jest). The trick is running Workers in a test harness that Pact can call.
`@cloudflare/vitest-pool-workers` provides that harness for Vitest.

---

## Project Structure

```
services/
  order-api/          ← provider Worker
    src/index.ts
    src/index.test.ts  (provider verification)
    wrangler.toml

  shipping-worker/    ← consumer Worker
    src/index.ts
    src/order-client.ts
    src/order-client.pact.test.ts  (consumer contract test)
    wrangler.toml
```

---

## Consumer Side

### The Client the Consumer Uses

```typescript
// services/shipping-worker/src/order-client.ts

export interface Order {
  id: string;
  status: "pending" | "confirmed" | "shipped";
  totalCents: number;
}

export async function fetchOrder(
  orderApiUrl: string,
  orderId: string,
  authToken: string
): Promise<Order> {
  const res = await fetch(`${orderApiUrl}/orders/${orderId}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!res.ok) throw new Error(`Order API error: ${res.status}`);
  return res.json<Order>();
}
```

---

### Consumer Contract Test

```typescript
// services/shipping-worker/src/order-client.pact.test.ts
import { PactV3, MatchersV3 } from "@pact-foundation/pact";
import { fetchOrder } from "./order-client";
import path from "path";

const { like, string, integer } = MatchersV3;

const provider = new PactV3({
  consumer: "ShippingWorker",
  provider: "OrderApi",
  dir: path.resolve(__dirname, "../pacts"), // where pact files are written
});

describe("OrderApi contract", () => {
  it("returns an order by id", async () => {
    await provider
      .given("order abc-123 exists")
      .uponReceiving("a GET request for order abc-123")
      .withRequest({
        method: "GET",
        path: "/orders/abc-123",
        headers: { Authorization: like("Bearer some-token") },
      })
      .willRespondWith({
        status: 200,
        headers: { "Content-Type": like("application/json") },
        body: {
          id: string("abc-123"),
          status: string("confirmed"),
          totalCents: integer(4999),
        },
      })
      .executeTest(async (mockServer) => {
        const order = await fetchOrder(mockServer.url, "abc-123", "some-token");
        expect(order.id).toBe("abc-123");
        expect(order.status).toBe("confirmed");
        expect(order.totalCents).toBe(4999);
      });
  });

  it("returns 404 when order does not exist", async () => {
    await provider
      .given("order xyz-999 does not exist")
      .uponReceiving("a GET request for a missing order")
      .withRequest({
        method: "GET",
        path: "/orders/xyz-999",
        headers: { Authorization: like("Bearer some-token") },
      })
      .willRespondWith({ status: 404 })
      .executeTest(async (mockServer) => {
        await expect(fetchOrder(mockServer.url, "xyz-999", "some-token")).rejects.toThrow(
          "Order API error: 404"
        );
      });
  });
});
```

Running this test writes `services/shipping-worker/pacts/ShippingWorker-OrderApi.json`.

---

### Publishing the Pact

```bash
# Via Pact Broker (self-hosted or PactFlow)
npx pact-broker publish \
  ./pacts \
  --broker-base-url https://your-broker.pactflow.io \
  --broker-token $PACT_BROKER_TOKEN \
  --consumer-app-version $(git rev-parse HEAD) \
  --branch $(git rev-parse --abbrev-ref HEAD)
```

In CI (GitHub Actions example):

```yaml
# .github/workflows/consumer-pact.yml
- name: Run consumer pact tests
  run: npx vitest run src/order-client.pact.test.ts
  working-directory: services/shipping-worker

- name: Publish pacts
  run: |
    npx pact-broker publish ./pacts \
      --broker-base-url ${{ secrets.PACT_BROKER_URL }} \
      --broker-token    ${{ secrets.PACT_BROKER_TOKEN }} \
      --consumer-app-version ${{ github.sha }} \
      --branch ${{ github.ref_name }}
  working-directory: services/shipping-worker
```

---

## Provider Side

### Provider State Setup (Vitest + Workers Pool)

```typescript
// services/order-api/src/index.test.ts
import { Verifier } from "@pact-foundation/pact";
import { unstable_startWorker } from "wrangler";
import path from "path";

// Start the real Worker locally; Pact will send real HTTP against it
let worker: Awaited<ReturnType<typeof unstable_startWorker>>;
let workerUrl: string;

beforeAll(async () => {
  worker = await unstable_startWorker({
    config: path.resolve(__dirname, "../wrangler.toml"),
  });
  workerUrl = `http://localhost:${worker.port}`;
});

afterAll(async () => {
  await worker.stop();
});

describe("OrderApi provider verification", () => {
  it("satisfies ShippingWorker pact", async () => {
    const verifier = new Verifier({
      provider: "OrderApi",
      providerBaseUrl: workerUrl,
      pactBrokerUrl: process.env.PACT_BROKER_URL!,
      pactBrokerToken: process.env.PACT_BROKER_TOKEN!,
      publishVerificationResult: true,
      providerVersion: process.env.GITHUB_SHA ?? "local",
      providerVersionBranch: process.env.GITHUB_REF_NAME ?? "local",

      // Provider states: seed data so requests match expectations
      stateHandlers: {
        "order abc-123 exists": async () => {
          // Insert into D1 test database or return from in-memory stub
          console.log("Setting up: order abc-123 exists");
        },
        "order xyz-999 does not exist": async () => {
          console.log("Setting up: order xyz-999 does not exist");
        },
      },
    });

    await verifier.verifyProvider();
  });
});
```

---

### Provider State Endpoint (Alternative Approach)

If the provider verification framework needs to call state setup over HTTP:

```typescript
// services/order-api/src/index.ts  (add a /_pact/provider-states endpoint)

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Only expose in non-production environments
    if (url.pathname === "/_pact/provider-states" && env.ENVIRONMENT !== "production") {
      const { state } = await request.json<{ state: string }>();
      await applyProviderState(state, env);
      return new Response("OK");
    }

    return routeRequest(request, env, ctx);
  },
};

async function applyProviderState(state: string, env: Env): Promise<void> {
  switch (state) {
    case "order abc-123 exists":
      await env.DB.prepare(
        "INSERT OR REPLACE INTO orders (id, status, total_cents) VALUES (?, ?, ?)"
      ).bind("abc-123", "confirmed", 4999).run();
      break;
    case "order xyz-999 does not exist":
      await env.DB.prepare("DELETE FROM orders WHERE id = ?").bind("xyz-999").run();
      break;
  }
}
```

---

## Can-I-Deploy Gate

Before deploying either service, check the broker:

```bash
# Check: is ShippingWorker@<sha> compatible with the deployed OrderApi?
npx pact-broker can-i-deploy \
  --pacticipant ShippingWorker \
  --version $(git rev-parse HEAD) \
  --to-environment production \
  --broker-base-url $PACT_BROKER_URL \
  --broker-token $PACT_BROKER_TOKEN
```

Exit code 0 = safe to deploy; non-zero = contract broken, deploy blocked.

---

## Anti-patterns

**Provider-driven contracts.** If the provider writes the pact (what it promises to return)
rather than the consumer (what it actually needs), the contract no longer reflects real
usage. The consumer must own the pact file.

**Over-specifying responses.** Matching the entire response body exactly causes brittle
contracts. Use Pact matchers (`like`, `eachLike`, `string`) to match structure and type, not
exact values. Exact matching breaks on timestamps, generated IDs, and minor provider
additions.

**Skipping `can-i-deploy`.** Publishing the pact but not gating deployment means contracts
are checked but never enforced. Add the `can-i-deploy` step as a required CI check on both
the consumer and provider pipelines.

**Testing via shared integration environments.** The point of CDC testing is to eliminate
shared environment dependencies. Provider verification must run the real Worker locally (via
`wrangler dev` or `unstable_startWorker`), not against a staging deployment.

---

## Gotchas

- `unstable_startWorker` is Wrangler's programmatic dev API and is subject to breaking
  changes between Wrangler versions. Pin your Wrangler version and check the changelog on
  upgrades.
- Provider state handlers run in the test process (Node.js), not inside the Worker. If
  state setup requires DB writes, use `wrangler d1 execute` or an HTTP endpoint inside the
  Worker (the `/_pact/provider-states` pattern).
- Pact does not support WebSocket or streaming responses. For Workers that use SSE or
  WebSockets, fall back to integration tests for those interaction types.
- The Pact mock server binds to a random port. Ensure no firewall rule blocks localhost
  loopback traffic in the CI runner.

---

## Verification

```bash
# Consumer: run pact tests and confirm pact file is generated
cd services/shipping-worker
npx vitest run src/order-client.pact.test.ts
ls pacts/   # ShippingWorker-OrderApi.json should appear

# Provider: run verification against broker
cd services/order-api
PACT_BROKER_URL=... PACT_BROKER_TOKEN=... npx vitest run src/index.test.ts

# Gate: check deployability
npx pact-broker can-i-deploy \
  --pacticipant ShippingWorker --version HEAD \
  --to-environment production \
  --broker-base-url $PACT_BROKER_URL --broker-token $PACT_BROKER_TOKEN
```

---

## Related

- `contract-first-api-design.md` — design-time API contracts using OpenAPI
- `worker-to-worker-rpc-service-bindings.md` — how Workers call each other
- `api-versioning-strategies.md` — managing breaking changes once contracts are in place
- `backward-compatibility-design.md` — ensuring provider changes remain backward-compatible

---

## Sources

- Pact documentation — docs.pact.io
- Pact JS/TS SDK — github.com/pact-foundation/pact-js
- Wrangler `unstable_startWorker` — developers.cloudflare.com/workers/wrangler/api
- Martin Fowler, "ContractTest", martinfowler.com/bliki/ContractTest.html
- Ian Robinson, "Consumer-Driven Contracts", martinfowler.com/articles/consumerDrivenContracts.html
