# Playwright Workers API Contract E2E Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Integration-level Pact tests verify that a consumer and provider agree on a contract, but they
still mock the network layer. End-to-end contract verification — spinning up the real Cloudflare
Worker via `wrangler dev`, driving a browser client with Playwright, and asserting that every
response body conforms to the published JSON Schema — catches drift that unit and Pact tests
miss: middleware stripping headers, Hono serialisation differences, D1 column renames. This
article shows how to build a Playwright fixture that runs `wrangler dev` in-process, drives API
calls from the browser context, and validates each response against a versioned schema registry.

## Context

The example project platform exposes REST APIs from several Workers (`apps/api-worker`,
`apps/search-worker`, `apps/auth-worker`). Schemas live in `packages/api-schema` as Zod
definitions that are compiled to JSON Schema for distribution. The Playwright test suite
(`e2e/`) targets these Workers via `wrangler dev --local` and validates both the happy path and
known error shapes. The Pact consumer-driven contract suite (see
`playwright-api-testing.md`) operates at the unit level; this article covers the E2E layer.

---

## wrangler-dev Playwright Fixture

```typescript
// e2e/fixtures/wrangler-worker.ts
import { test as base, type APIRequestContext } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";

interface WorkerFixtures {
  workerUrl: string;
  apiRequest: APIRequestContext;
}

// Wait for wrangler dev to print its ready URL
async function waitForReady(proc: ChildProcess): Promise<string> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("wrangler dev timeout")), 30_000);
    proc.stdout?.on("data", (chunk: Buffer) => {
      const line = chunk.toString();
      const match = line.match(/Ready on (http:\/\/[^\s]+)/);
      if (match) { clearTimeout(timeout); resolve(match[1]); }
    });
    proc.on("error", reject);
    proc.on("exit", (code) => {
      if (code !== 0) reject(new Error(`wrangler dev exited with ${code}`));
    });
  });
}

export const test = base.extend<WorkerFixtures>({
  workerUrl: async ({}, use) => {
    const proc = spawn(
      "npx",
      ["wrangler", "dev", "--local", "--port", "0", "--config", "apps/api-worker/wrangler.toml"],
      { stdio: ["ignore", "pipe", "pipe"] }
    );
    const url = await waitForReady(proc);
    await use(url);
    proc.kill("SIGTERM");
    await once(proc, "exit").catch(() => {});
  },

  apiRequest: async ({ playwright, workerUrl }, use) => {
    const ctx = await playwright.request.newContext({ baseURL: workerUrl });
    await use(ctx);
    await ctx.dispose();
  },
});

export { expect } from "@playwright/test";
```

---

## JSON Schema Validation Fixture

```typescript
// e2e/fixtures/schema-validator.ts
import { test as workerTest, expect } from "./wrangler-worker";
import Ajv from "ajv";
import addFormats from "ajv-formats";
import { readFileSync } from "node:fs";
import path from "node:path";

const ajv = new Ajv({ strict: true, allErrors: true });
addFormats(ajv);

// Load compiled schemas from the package
const SCHEMA_DIR = path.resolve("packages/api-schema/dist");

function loadSchema(name: string) {
  const raw = readFileSync(path.join(SCHEMA_DIR, `${name}.json`), "utf8");
  return JSON.parse(raw);
}

export const test = workerTest.extend<{
  validateSchema: (name: string, data: unknown) => void;
}>({
  validateSchema: async ({}, use) => {
    const cache = new Map<string, ReturnType<typeof ajv.compile>>();

    const validator = (name: string, data: unknown) => {
      if (!cache.has(name)) cache.set(name, ajv.compile(loadSchema(name)));
      const validate = cache.get(name)!;
      const valid = validate(data);
      if (!valid) {
        throw new Error(
          `Schema "${name}" validation failed:\n${ajv.errorsText(validate.errors)}`
        );
      }
    };

    await use(validator);
  },
});

export { expect };
```

---

## Writing Contract E2E Tests

```typescript
// e2e/api-contract.spec.ts
import { test, expect } from "./fixtures/schema-validator";

test.describe("GET /v1/articles – response contract", () => {
  test("200 list shape matches ArticleList schema", async ({ apiRequest, validateSchema }) => {
    const res = await apiRequest.get("/v1/articles?limit=5");
    expect(res.status()).toBe(200);
    const body = await res.json();
    validateSchema("ArticleList", body);
    expect(body.items).toHaveLength(5);
    expect(body.nextCursor).toEqual(expect.any(String));
  });

  test("400 invalid limit returns ErrorEnvelope schema", async ({ apiRequest, validateSchema }) => {
    const res = await apiRequest.get("/v1/articles?limit=abc");
    expect(res.status()).toBe(400);
    const body = await res.json();
    validateSchema("ErrorEnvelope", body);
    expect(body.error.code).toBe("VALIDATION_ERROR");
  });

  test("Content-Type header is application/json", async ({ apiRequest }) => {
    const res = await apiRequest.get("/v1/articles");
    expect(res.headers()["content-type"]).toMatch(/application\/json/);
  });
});

test.describe("POST /v1/articles – mutation contract", () => {
  test("201 created article matches Article schema", async ({ apiRequest, validateSchema }) => {
    const res = await apiRequest.post("/v1/articles", {
      data: { title: "Contract Test Article", body: "Hello" },
    });
    expect(res.status()).toBe(201);
    validateSchema("Article", await res.json());
  });

  test("409 duplicate slug returns ErrorEnvelope", async ({ apiRequest, validateSchema }) => {
    const payload = { title: "Dup", slug: "dup-slug", body: "x" };
    await apiRequest.post("/v1/articles", { data: payload });
    const res = await apiRequest.post("/v1/articles", { data: payload });
    expect(res.status()).toBe(409);
    validateSchema("ErrorEnvelope", await res.json());
  });
});
```

---

## Response Header Contract Assertions

```typescript
// e2e/api-headers.spec.ts
import { test, expect } from "./fixtures/wrangler-worker";

const SECURITY_HEADERS = [
  ["x-content-type-options", "nosniff"],
  ["x-frame-options", "DENY"],
  ["strict-transport-security", /max-age=\d+/],
];

test("security headers present on all 2xx responses", async ({ apiRequest }) => {
  const res = await apiRequest.get("/v1/articles");
  for (const [header, expected] of SECURITY_HEADERS) {
    const value = res.headers()[header];
    expect(value, `missing ${header}`).toBeDefined();
    if (expected instanceof RegExp) expect(value).toMatch(expected);
    else expect(value).toBe(expected);
  }
});

test("Cache-Control absent on authenticated endpoints", async ({ apiRequest }) => {
  const res = await apiRequest.get("/v1/me", {
    headers: { Authorization: "Bearer test-token-123" },
  });
  expect(res.headers()["cache-control"]).toBeUndefined();
});
```

---

## Schema Drift Detection in CI

```typescript
// e2e/schema-drift.spec.ts
import { test, expect } from "./fixtures/schema-validator";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";

// Snapshot hashes of published schemas to detect silent breaking changes
const SCHEMA_HASHES: Record<string, string> = {
  "ArticleList": "sha256-abc123...",   // generated by: node scripts/hash-schemas.mjs
  "Article":     "sha256-def456...",
  "ErrorEnvelope": "sha256-789ghi...",
};

test("compiled schemas match published hashes", () => {
  for (const [name, expected] of Object.entries(SCHEMA_HASHES)) {
    const file = path.resolve(`packages/api-schema/dist/${name}.json`);
    const actual = "sha256-" + createHash("sha256")
      .update(readFileSync(file))
      .digest("hex")
      .slice(0, 6) + "...";
    expect(actual, `schema "${name}" has drifted`).toBe(expected);
  }
});
```

---

## playwright.config.ts Integration

```typescript
// playwright.config.ts (relevant section)
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,       // wrangler dev startup adds latency
  retries: process.env.CI ? 1 : 0,
  use: {
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "api-contracts",
      testMatch: /api-contract\.spec\.ts|api-headers\.spec\.ts/,
      // No browser needed – pure APIRequestContext
      use: { browserName: "chromium", headless: true },
    },
  ],
  // Run wrangler dev once for the entire suite via globalSetup if preferred
  // globalSetup: "./e2e/global-setup.ts",
});
```

---

## Anti-patterns

- **Asserting only status codes** – Status codes alone do not catch schema drift. A renamed
  field `items` → `data` still returns 200; only schema validation catches it.
- **One Playwright project sharing a single `wrangler dev` process** – Worker state leaks
  between test files. Use the fixture's per-test `workerUrl` or a `globalSetup` with careful
  state reset between suites.
- **Hardcoding `localhost:8787`** – Port collisions in parallel CI runs. Pass `--port 0` and
  capture the dynamic URL from stdout.
- **Skipping error-shape contracts** – Most contract drift happens in error responses, not
  happy paths. Always have a test for each `4xx` code the Worker emits.
- **Compiling schemas on the fly in tests** – Compile at build time in `packages/api-schema`;
  tests load the pre-built JSON. On-the-fly Zod→JSONSchema in tests is slow and masks
  version mismatches.

---

## Gotchas

- `wrangler dev --local` with `--port 0` returns an ephemeral port; parse the port from the
  "Ready on" line, not from environment variables.
- Ajv v8 is ESM-first; use `import` syntax and ensure `"type": "module"` in the e2e package
  or configure `@playwright/test`'s `tsconfig` accordingly.
- Workers behind auth middleware will return 401 for all unauthenticated E2E calls; add a
  dedicated test auth token in the Worker's local binding (wrangler.toml `[vars]`) and pass it
  in the fixture.
- JSON Schema `additionalProperties: false` is strict but catches field addition bugs from the
  Worker side. Generate schemas with `additionalProperties: false` only for versioned stable
  endpoints.
- `wrangler dev` in CI can be slow on the first run (downloading the local runtime). Cache
  `~/.wrangler/local-protocol-server` across CI runs to reduce cold-start time.

---

## Verification

```bash
# Run API contract tests locally
pnpm playwright test --project=api-contracts

# Generate schema hashes for hash-pinning file
node scripts/hash-schemas.mjs > e2e/schema-hashes.json

# Run with trace on failure
pnpm playwright test --project=api-contracts --trace=on

# CI one-liner
pnpm playwright test --project=api-contracts --reporter=github
```

---

## Related

- `api-contract-testing-pact-workers.md`
- `playwright-workers-auth-flow-session-persistence-e2e.md`
- `playwright-webserver-readiness-and-ci-isolation.md`
- `hono-workers-api-snapshot-testing.md`
- `contract-testing-workers-openapi-schema-drift.md`

---

## Sources

- Playwright APIRequestContext: https://playwright.dev/docs/api/class-apirequestcontext
- Wrangler dev CLI: https://developers.cloudflare.com/workers/wrangler/commands/#dev
- Ajv JSON Schema validator: https://ajv.js.org/
- Zod-to-JSON-Schema: https://github.com/StefanTerdell/zod-to-json-schema
- Cloudflare Workers local development: https://developers.cloudflare.com/workers/local-development/
