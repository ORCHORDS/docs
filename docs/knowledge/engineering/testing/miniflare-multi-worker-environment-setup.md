# Miniflare Multi-Worker Test Environment Setup

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Applications that span multiple Cloudflare Workers connected via Service Bindings cannot be tested in isolation — each Worker must be able to call its downstream sibling. This article shows how to configure Miniflare 3 to run several Workers in a single Vitest suite and wire Service Bindings between them.

## Context
Cloudflare Service Bindings let one Worker call another over an in-process channel with no HTTP round-trip. In production, the runtime resolves the binding by name; in tests, Miniflare's `workers` array in `vitest-pool-workers` configuration replaces the production resolution. Each entry declares its own script, bindings, and compatibility settings, and references other workers by the binding names defined in `wrangler.toml`. This enables end-to-end tests that cover the full call graph without deploying.

## Repository Structure

```
apps/
  api/          # public-facing Worker
  auth/         # internal auth service (Service Binding)
  data/         # data access Worker (Service Binding)
vitest.config.ts
```

## Vitest Configuration for Multiple Workers

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        // The worker under test — its bindings resolve to the siblings below
        wrangler: { configPath: "./apps/api/wrangler.toml" },
        miniflare: {
          workers: [
            {
              // auth service sibling
              name: "auth-worker",
              scriptPath: "./apps/auth/dist/index.js",
              compatibilityDate: "2024-09-23",
              compatibilityFlags: ["nodejs_compat"],
              bindings: {},
            },
            {
              // data service sibling
              name: "data-worker",
              scriptPath: "./apps/data/dist/index.js",
              compatibilityDate: "2024-09-23",
              d1Databases: { DB: "local-d1" },
            },
          ],
        },
      },
    },
  },
});
```

The `api` Worker's `wrangler.toml` declares the service bindings by name:

```toml
# apps/api/wrangler.toml
name = "api-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[services]]
binding = "AUTH"
service = "auth-worker"

[[services]]
binding = "DATA"
service = "data-worker"
```

## Writing Cross-Worker Integration Tests

```typescript
// tests/api-auth-flow.test.ts
import { describe, it, expect } from "vitest";
import { env, SELF } from "cloudflare:test";

describe("API → Auth service binding", () => {
  it("rejects requests without a bearer token", async () => {
    const res = await SELF.fetch("https://api.example.com/protected");
    expect(res.status).toBe(401);
  });

  it("forwards valid token to auth service and returns 200", async () => {
    const res = await SELF.fetch("https://api.example.com/protected", {
      headers: { Authorization: "Bearer valid-test-token" },
    });
    expect(res.status).toBe(200);
  });
});
```

## Testing Service Binding Call Propagation

Verify the API Worker correctly delegates to the data sibling and surfaces the response:

```typescript
// tests/api-data-flow.test.ts
import { it, expect, beforeAll } from "vitest";
import { SELF, env } from "cloudflare:test";

beforeAll(async () => {
  // Seed the local D1 attached to the data-worker sibling
  await env.DATA.fetch(new Request("https://data.internal/seed", { method: "POST" }));
});

it("returns items from the data service", async () => {
  const res = await SELF.fetch("https://api.example.com/items");
  expect(res.status).toBe(200);
  const body = await res.json<{ items: unknown[] }>();
  expect(body.items.length).toBeGreaterThan(0);
});

it("propagates 404 from data service to the API response", async () => {
  const res = await SELF.fetch("https://api.example.com/items/does-not-exist");
  expect(res.status).toBe(404);
});
```

## Isolating Sibling Workers Per Test Suite

To prevent state bleeding between test files when siblings share in-memory state, use unique binding names or reset endpoints:

```typescript
// tests/helpers/reset.ts
import { env } from "cloudflare:test";

export async function resetDataWorker(): Promise<void> {
  const res = await env.DATA.fetch(new Request("https://data.internal/reset", { method: "DELETE" }));
  if (!res.ok) throw new Error(`Reset failed: ${res.status}`);
}
```

```typescript
// tests/isolated-suite.test.ts
import { beforeEach, it, expect } from "vitest";
import { SELF } from "cloudflare:test";
import { resetDataWorker } from "./helpers/reset";

beforeEach(resetDataWorker);

it("starts each test with an empty item list", async () => {
  const res = await SELF.fetch("https://api.example.com/items");
  const body = await res.json<{ items: unknown[] }>();
  expect(body.items).toHaveLength(0);
});
```

## Testing Error Propagation Across Bindings

When a sibling throws, verify the API Worker handles it gracefully:

```typescript
// tests/service-binding-error.test.ts
import { it, expect, vi } from "vitest";
import { SELF, env } from "cloudflare:test";

it("returns 503 when data service is unavailable", async () => {
  // Override the DATA binding for this test with a fetch that always fails
  vi.spyOn(env.DATA, "fetch").mockResolvedValueOnce(
    new Response("service unavailable", { status: 503 })
  );

  const res = await SELF.fetch("https://api.example.com/items");
  expect(res.status).toBe(503);
});
```

## Anti-patterns
- Do not build sibling Worker scripts on-the-fly in `vitest.config.ts`; pre-build them with `wrangler build --no-bundle` or esbuild in a `globalSetup` file to keep config clean.
- Avoid pointing all workers at the same `wrangler.toml`; each sibling needs its own config or inline options so that bindings resolve correctly.
- Do not share mutable module-level state across workers — Miniflare runs each Worker script in an isolated V8 context, so cross-worker state must go through bindings.

## Gotchas
- Service Binding calls in Miniflare are synchronous in-process invocations; they do not add HTTP latency, but they do add JavaScript microtask queue depth — deep call chains may exhaust the stack in test environments.
- `SELF` refers to the primary Worker under test (the one in `wrangler.configPath`); calls to siblings must go through `env.BINDING_NAME.fetch(...)`.
- If a sibling Worker's build is stale, tests silently run against the old code — add a pre-test build step in `package.json` scripts.
- Miniflare does not replicate Cloudflare's inter-Worker network isolation or subrequest limits; tests that exploit this will pass locally but fail in production.

## Verification
`npx vitest run tests/api-auth-flow.test.ts tests/api-data-flow.test.ts` — all assertions should pass without external network calls. Check the Miniflare debug log (`DEBUG=miniflare:*`) to confirm each Worker script is loaded correctly.

## Related
- [workers-service-bindings-vitest-testing.md](workers-service-bindings-vitest-testing.md)
- [vitest-cloudflare-pool-workers.md](vitest-cloudflare-pool-workers.md)
- [vitest-projects-isolation-and-configuration-boundaries.md](vitest-projects-isolation-and-configuration-boundaries.md)
- [test-isolation-principles.md](test-isolation-principles.md)

## Sources
- https://developers.cloudflare.com/workers/testing/vitest-integration/configuration/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://github.com/cloudflare/workers-sdk/blob/main/packages/vitest-pool-workers/README.md
