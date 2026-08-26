# Workers Service Bindings Integration Testing with Worktrees

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your monorepo has two Workers: `api` (public-facing) and `auth` (internal). `api` calls
`auth` via a service binding. Unit tests mock the binding, so integration bugs at the
boundary are only caught in production. You want a local integration test harness that
starts both Workers in separate processes, wires the real service binding, and runs
end-to-end assertions — without deploying to Cloudflare. You also want to run the same
suite in parallel across feature branches using git worktrees.

## Context

Wrangler's `--local` mode supports service bindings between locally-running Workers
since `wrangler` 3.x. Each Worker exposes itself on a local port; the binding is
declared in `wrangler.jsonc` pointing to the other Worker's local URL. `miniflare` v3
exposes a programmatic API for the same topology, enabling full in-process integration
testing. Combining worktrees with the miniflare API lets CI run integration tests for
multiple branches simultaneously without port contention.

---

## 1. Wrangler Local Service Binding Topology

```jsonc
// packages/api/wrangler.jsonc
{
  "name": "api",
  "compatibility_date": "2025-11-01",
  "main": "src/index.ts",
  "services": [
    {
      "binding": "AUTH",
      "service": "auth",
      "environment": "local"      // resolved to locally-running auth Worker
    }
  ]
}
```

```jsonc
// packages/auth/wrangler.jsonc
{
  "name": "auth",
  "compatibility_date": "2025-11-01",
  "main": "src/index.ts"
}
```

```bash
# Start auth Worker first
cd packages/auth && pnpm wrangler dev --port 8789 --local &

# Start api Worker, referencing auth via service binding
cd packages/api && pnpm wrangler dev --port 8788 --local \
  --var AUTH_SERVICE_URL:http://localhost:8789 &
```

Wrangler resolves service bindings to locally-running Workers by matching the `name`
field in `wrangler.jsonc`. No explicit URL is required when both processes are started
via `wrangler dev --local` in the same session.

## 2. In-Process Miniflare Harness

```typescript
// packages/api/tests/integration/harness.ts
import { Miniflare, Response as MiniflareResponse } from "miniflare";
import path from "node:path";

export async function createTestHarness() {
  // Auth Worker (inner)
  const authWorker = new Miniflare({
    name: "auth",
    scriptPath: path.resolve(__dirname, "../../auth/dist/index.js"),
    compatibilityDate: "2025-11-01",
    modules: true,
  });

  // API Worker (outer) with service binding to auth
  const apiWorker = new Miniflare({
    name: "api",
    scriptPath: path.resolve(__dirname, "../dist/index.js"),
    compatibilityDate: "2025-11-01",
    modules: true,
    serviceBindings: {
      AUTH: async (request: Request): Promise<MiniflareResponse> => {
        // Proxy to the auth miniflare instance
        return authWorker.dispatchFetch(request.url, {
          method: request.method,
          headers: Object.fromEntries(request.headers),
          body: request.body,
        });
      },
    },
  });

  return {
    api: apiWorker,
    auth: authWorker,
    async [Symbol.asyncDispose]() {
      await apiWorker.dispose();
      await authWorker.dispose();
    },
  };
}
```

## 3. Integration Test Suite

```typescript
// packages/api/tests/integration/auth-binding.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { createTestHarness } from "./harness";

describe("api <-> auth service binding integration", () => {
  let harness: Awaited<ReturnType<typeof createTestHarness>>;

  beforeAll(async () => {
    harness = await createTestHarness();
  });

  afterAll(async () => {
    await harness[Symbol.asyncDispose]();
  });

  it("returns 401 when Authorization header is missing", async () => {
    const res = await harness.api.dispatchFetch("http://localhost/protected");
    expect(res.status).toBe(401);
  });

  it("returns 200 with valid JWT forwarded to auth", async () => {
    const res = await harness.api.dispatchFetch("http://localhost/protected", {
      headers: { Authorization: "Bearer valid-test-token" },
    });
    expect(res.status).toBe(200);
    const body = await res.json<{ userId: string }>();
    expect(body.userId).toBeTruthy();
  });

  it("propagates auth errors as structured JSON", async () => {
    const res = await harness.api.dispatchFetch("http://localhost/protected", {
      headers: { Authorization: "Bearer expired-token" },
    });
    expect(res.status).toBe(401);
    const body = await res.json<{ error: string }>();
    expect(body.error).toMatch(/expired/i);
  });
});
```

## 4. Worktree-Aware Port Assignment

```typescript
// scripts/resolve-test-ports.ts
import { createHash } from "node:crypto";
import { execSync } from "node:child_process";

function branchToPort(baseName: string, base: number, range: number): number {
  const branch = execSync("git branch --show-current", { encoding: "utf8" }).trim();
  const hash = createHash("sha256").update(`${baseName}:${branch}`).digest("hex");
  return base + (parseInt(hash.slice(0, 4), 16) % range);
}

export const AUTH_PORT = branchToPort("auth", 9000, 500);   // 9000–9499
export const API_PORT  = branchToPort("api",  9500, 500);   // 9500–9999

console.log(`AUTH_PORT=${AUTH_PORT} API_PORT=${API_PORT}`);
```

This deterministically assigns ports based on branch name, so two worktrees for
different branches never collide while the same branch always gets the same ports
(enabling `wait-on` checks without a lookup step).

## 5. Vitest Config for Integration Tests

```typescript
// packages/api/vitest.config.integration.ts
import { defineConfig } from "vitest/config";
import { AUTH_PORT, API_PORT } from "../../scripts/resolve-test-ports";

export default defineConfig({
  test: {
    include: ["tests/integration/**/*.test.ts"],
    globals: true,
    testTimeout: 30_000,
    env: {
      AUTH_PORT: String(AUTH_PORT),
      API_PORT: String(API_PORT),
      // Miniflare uses these to route inter-service requests
    },
    pool: "forks",          // isolate each test file in a subprocess
    poolOptions: {
      forks: { singleFork: true },   // keep miniflare instance alive across tests
    },
  },
});
```

```bash
# Run integration tests in the current worktree
pnpm vitest run --config vitest.config.integration.ts
```

## 6. CI Matrix Across Worktrees

```yaml
# .github/workflows/integration.yml
name: Service Binding Integration Tests
on: [pull_request]

jobs:
  integration:
    strategy:
      matrix:
        package: [api, analytics]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile

      - name: Build all Workers
        run: pnpm turbo build --filter=${{ matrix.package }}...

      - name: Run integration tests
        run: |
          pnpm --filter @repo/${{ matrix.package }} \
            vitest run --config vitest.config.integration.ts
```

---

## Anti-patterns

- **Mocking service bindings in integration tests** — the entire point of integration
  testing is exercising the real binding contract. Mocks belong in unit tests only.
- **Starting wrangler dev processes sequentially without readiness checks** — the api
  Worker starts before auth is ready, the binding call fails with ECONNREFUSED, and
  the test suite reports a false negative.
- **Using the same miniflare instance for both Workers** — a single Miniflare cannot
  simulate service binding latency, separate Worker memory, or isolated Durable Object
  namespaces. Use two instances connected via the `serviceBindings` callback.
- **Hardcoding ports in test code** — causes collision when multiple worktrees run the
  `wrangler dev`-based harness in CI on the same runner.

## Gotchas

- Miniflare v3's `serviceBindings` callback receives a `Request` object, not a URL
  string. If the bound Worker uses `request.url` to route internally, ensure the URL
  passed to `dispatchFetch` inside the callback matches the inner Worker's route patterns.
- `wrangler dev --local` service binding resolution requires both Workers to declare the
  same `name` in `wrangler.jsonc`. A name mismatch produces a `binding not found` error
  at runtime, not at startup.
- In CI, `pnpm turbo build` must produce `dist/index.js` before Miniflare's
  `scriptPath` is used. Running tests before build produces a misleading "file not found"
  error rather than a build failure.
- Miniflare v3 does not support the `wrangler dev --remote` binding protocol. Integration
  tests must stay `--local` / in-process.

## Verification

```bash
# Build first
pnpm turbo build --filter=api... --filter=auth...

# Run integration suite
pnpm --filter @repo/api vitest run --config vitest.config.integration.ts --reporter=verbose

# Expected output:
# ✓ api <-> auth service binding integration > returns 401 when Authorization header is missing
# ✓ api <-> auth service binding integration > returns 200 with valid JWT forwarded to auth
# ✓ api <-> auth service binding integration > propagates auth errors as structured JSON
# Test Files  1 passed
```

## Related

- `git-worktree-parallel-feature-branch-testing-workers.md`
- `cloudflare-workers-vitest-miniflare-testing.md`
- `monorepo-deploy-order-workers-service-bindings.md`
- `monorepo-wrangler-service-bindings-topology.md`
- `git-worktree-parallel-ci-patterns.md`

## Sources

- Miniflare v3 `serviceBindings` API — miniflare.dev/docs/core/service-bindings
- Wrangler local service binding docs — developers.cloudflare.com/workers/wrangler/service-bindings
- Vitest pool options — vitest.dev/config/#pool
