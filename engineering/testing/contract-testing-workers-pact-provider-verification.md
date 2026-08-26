# Pact Contract Testing for Cloudflare Workers as a Provider

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Multiple consumer teams depend on a Cloudflare Workers API. You need contract tests that verify the Workers provider honours each consumer's expectations, fail the deployment pipeline when a contract is broken, and give consumer teams a self-service workflow for publishing new contracts.

## Context

Pact is a consumer-driven contract testing framework. The consumer writes a Pact file (JSON) describing the HTTP interactions it expects, publishes it to a Pact Broker, and the provider runs verification against its own running server. For Cloudflare Workers, the provider server is `wrangler dev --local`, and provider states are seeded into D1 before each interaction.

This article covers: provider verification setup, D1 provider-state seeding, Pact Broker CI integration, and pipeline gating.

## Provider Verification Setup

```typescript
// pact/provider.test.ts
import { Verifier, VerifierOptions } from "@pact-foundation/pact";
import { execSync, spawn, ChildProcess } from "node:child_process";
import path from "node:path";
import { afterAll, beforeAll, describe, it } from "vitest";

const PROVIDER_PORT = 9000;
const PROVIDER_BASE_URL = `http://localhost:${PROVIDER_PORT}`;
const PACT_BROKER_URL =
  process.env.PACT_BROKER_URL ?? "https://broker.pact.example.com";
const PACT_BROKER_TOKEN = process.env.PACT_BROKER_TOKEN ?? "";

let wranglerProcess: ChildProcess;

// ---------------------------------------------------------------------------
// Provider state handler — seeds D1 before each Pact interaction
// ---------------------------------------------------------------------------

const providerStatesHandler = async (
  req: Request
): Promise<Response> => {
  const body = await req.json<{ state: string; params?: Record<string, unknown> }>();

  switch (body.state) {
    case "a product with ID prod-001 exists": {
      execSync(
        `npx wrangler d1 execute products-db --local --command \
        "INSERT OR REPLACE INTO products (id, name, price) \
         VALUES ('prod-001', 'Widget', 9.99);"`
      );
      break;
    }
    case "no products exist": {
      execSync(
        `npx wrangler d1 execute products-db --local --command \
        "DELETE FROM products;"`
      );
      break;
    }
    case "user alice has an active session": {
      const expiresAt = new Date(Date.now() + 3600_000).toISOString();
      execSync(
        `npx wrangler d1 execute products-db --local --command \
        "INSERT OR REPLACE INTO sessions (token, user_id, expires_at) \
         VALUES ('tok-alice', 'user-alice', '${expiresAt}');"`
      );
      break;
    }
    default:
      return new Response(
        JSON.stringify({ error: `Unknown state: ${body.state}` }),
        { status: 400 }
      );
  }

  return new Response(JSON.stringify({ success: true }), { status: 200 });
};

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

beforeAll(async () => {
  // Start wrangler dev in local mode
  wranglerProcess = spawn(
    "npx",
    ["wrangler", "dev", "--local", "--port", String(PROVIDER_PORT)],
    { stdio: "pipe", detached: false }
  );

  // Wait for wrangler to be ready
  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(
      () => reject(new Error("wrangler dev timed out")),
      30_000
    );
    wranglerProcess.stdout?.on("data", (chunk: Buffer) => {
      if (chunk.toString().includes("Ready on")) {
        clearTimeout(timeout);
        resolve();
      }
    });
  });
}, 40_000);

afterAll(async () => {
  wranglerProcess.kill("SIGTERM");
});

// ---------------------------------------------------------------------------
// Pact provider verification
// ---------------------------------------------------------------------------

describe("Pact provider verification", () => {
  it("verifies all consumer contracts from the Pact Broker", async () => {
    const opts: VerifierOptions = {
      provider: "workers-products-api",
      providerBaseUrl: PROVIDER_BASE_URL,

      // Pull contracts from the Pact Broker
      pactBrokerUrl: PACT_BROKER_URL,
      pactBrokerToken: PACT_BROKER_TOKEN,

      // Only verify contracts for consumers that interact with this provider
      consumerVersionSelectors: [
        { mainBranch: true },
        { deployedOrReleased: true },
      ],

      // Provider state setup endpoint (handled by a separate HTTP server below)
      stateHandlers: {
        "a product with ID prod-001 exists": async () => {
          await providerStatesHandler(
            new Request("http://localhost/", {
              method: "POST",
              body: JSON.stringify({ state: "a product with ID prod-001 exists" }),
            })
          );
        },
        "no products exist": async () => {
          await providerStatesHandler(
            new Request("http://localhost/", {
              method: "POST",
              body: JSON.stringify({ state: "no products exist" }),
            })
          );
        },
        "user alice has an active session": async () => {
          await providerStatesHandler(
            new Request("http://localhost/", {
              method: "POST",
              body: JSON.stringify({ state: "user alice has an active session" }),
            })
          );
        },
      },

      // Publish verification results back to the Pact Broker
      publishVerificationResult: !!process.env.CI,
      providerVersion: process.env.GIT_SHA ?? "local",
      providerVersionBranch: process.env.GIT_BRANCH ?? "local",
    };

    await new Verifier(opts).verifyProvider();
  }, 120_000);
});
```

## CI Pipeline Configuration (GitHub Actions)

```yaml
# .github/workflows/pact-verify.yml
name: Pact Provider Verification

on:
  push:
    branches: [main]
  pull_request:

jobs:
  pact-verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - run: npm ci

      - name: Run provider verification
        env:
          PACT_BROKER_URL: ${{ secrets.PACT_BROKER_URL }}
          PACT_BROKER_TOKEN: ${{ secrets.PACT_BROKER_TOKEN }}
          GIT_SHA: ${{ github.sha }}
          GIT_BRANCH: ${{ github.ref_name }}
          CI: "true"
        run: npx vitest run pact/provider.test.ts

      - name: Gate deploy on contract verification
        if: failure()
        run: |
          echo "::error::Pact provider verification failed. Deploy blocked."
          exit 1
```

## Consumer Workflow for Publishing Contracts

```typescript
// consumer-team/pact/publish.ts  — run by the consumer CI
import { Publisher } from "@pact-foundation/pact";

const publisher = new Publisher({
  pactBroker: process.env.PACT_BROKER_URL!,
  pactBrokerToken: process.env.PACT_BROKER_TOKEN!,
  pactFilesOrDirs: [path.resolve(__dirname, "../pacts")],
  consumerVersion: process.env.GIT_SHA!,
  branch: process.env.GIT_BRANCH!,
  tags: [process.env.GIT_BRANCH!],
});

await publisher.publishPacts();
console.log("Pact contracts published to broker.");
```

## Anti-patterns

- **Running provider verification against the production Workers URL** — provider states mutate D1; never run state-seeding SQL against production.
- **Publishing verification results from a PR branch without a `providerVersionBranch`** — the Pact Broker cannot determine which contracts are safe to deploy without branch metadata.
- **Hardcoding consumer names** in `consumerVersionSelectors` — use `mainBranch: true` + `deployedOrReleased: true` to automatically pick up all relevant consumers.
- **Skipping the pipeline gate step** — verification results published but not checked mean broken contracts go undetected until a consumer breaks in production.

## Gotchas

- `wrangler dev --local` starts asynchronously; wait for the "Ready on" stdout message before running verification — a race condition here causes all interactions to fail with `ECONNREFUSED`.
- Pact's `stateHandlers` run in the Node.js test process, not inside the Worker. D1 state changes must be applied via `wrangler d1 execute --local` (or a dedicated state-setup HTTP endpoint on the Worker itself gated by an env flag).
- `publishVerificationResult: true` should only be set in CI (`process.env.CI`). Local runs that publish results with `local` as the version pollute the Pact Broker's can-I-deploy matrix.
- Provider state handler errors must return a non-2xx status code; otherwise Pact marks the state as successfully set up even when D1 seeding failed.

## Verification

```bash
# Run verification locally (no broker publish)
npx vitest run pact/provider.test.ts

# Check can-I-deploy status for this provider version
npx pact-broker can-i-deploy \
  --broker-base-url=$PACT_BROKER_URL \
  --broker-token=$PACT_BROKER_TOKEN \
  --pacticipant=workers-products-api \
  --version=$(git rev-parse HEAD)
```

## Related

- `workers-integration-test-service-bindings-miniflare.md`
- `load-testing-workers-k6-realistic-traffic-profiles.md`
- Pact Foundation documentation — `https://docs.pact.io`

## Sources

- `@pact-foundation/pact` Node.js library documentation
- Pact Broker can-i-deploy workflow
- Cloudflare Workers `wrangler dev --local` reference
