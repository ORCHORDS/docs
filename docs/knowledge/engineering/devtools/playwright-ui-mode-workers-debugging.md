# Playwright UI Mode for Cloudflare Workers Component Debugging

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You are writing Playwright end-to-end tests against a Cloudflare Worker (served
locally via `wrangler dev` or `wrangler pages dev`) and you want to:

- Step through individual tests visually without re-running the full suite.
- Inspect the DOM, network requests, and console output side-by-side.
- Watch and re-run tests as source files change.
- Debug flaky assertions with the time-travel trace viewer built into UI mode.

`playwright test --ui` launches a desktop-grade interactive test runner. This
article shows how to wire it against a local Worker and make the experience
fast and stable.

---

## Context

Playwright UI Mode (introduced in v1.32) combines:

- A filterable test tree on the left.
- Live browser preview on the right.
- Time-travel playback via trace snapshots.
- File-watch auto re-run.

For Workers the key challenge is **base URL management**: the Worker must be
running before Playwright starts, and the port may differ across environments.
The canonical solution is a `globalSetup` that spawns `wrangler dev` as a
child process and waits until the port is accepting connections.

---

## Prerequisites

```bash
pnpm add -D @playwright/test wrangler
# Install Chromium (required for UI mode)
pnpm exec playwright install chromium
```

---

## Playwright Config

```typescript
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

const WORKER_PORT = Number(process.env.WORKER_PORT ?? 8787);

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,

  use: {
    baseURL: `http://localhost:${WORKER_PORT}`,
    // Capture trace on first retry — critical for UI mode time-travel
    trace: "on-first-retry",
    // Capture screenshot on failure
    screenshot: "only-on-failure",
  },

  // Spawn wrangler dev before the test suite
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // Watch mode: re-run tests when src/ changes
  // (UI mode enables this automatically; this is for headless watch)
  reporter: process.env.CI ? "github" : "html",
});
```

---

## Global Setup: Spawning wrangler dev

```typescript
// e2e/global-setup.ts
import { spawn, ChildProcess } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

declare global {
  // Shared across setup and teardown via process env
  // (globalSetup/globalTeardown cannot share module-level state)
}

const PORT = Number(process.env.WORKER_PORT ?? 8787);
const MAX_WAIT_MS = 20_000;

async function waitForPort(port: number, timeoutMs: number): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`http://localhost:${port}/health`);
      if (res.ok || res.status < 500) return;
    } catch {
      // not ready yet
    }
    await sleep(250);
  }
  throw new Error(`wrangler dev did not start on port ${port} within ${timeoutMs}ms`);
}

export default async function globalSetup() {
  const wrangler = spawn(
    "pnpm",
    ["wrangler", "dev", "--local", "--port", String(PORT)],
    {
      stdio: process.env.PLAYWRIGHT_DEBUG ? "inherit" : "pipe",
      env: { ...process.env, NODE_ENV: "test" },
    }
  );

  // Store PID so teardown can kill it
  process.env.__WRANGLER_PID = String(wrangler.pid);

  // Surface stderr on crash
  if (!process.env.PLAYWRIGHT_DEBUG) {
    wrangler.stderr?.on("data", (chunk: Buffer) => {
      if (chunk.toString().includes("Error")) {
        process.stderr.write("[wrangler] " + chunk.toString());
      }
    });
  }

  await waitForPort(PORT, MAX_WAIT_MS);
  console.log(`\n[globalSetup] wrangler dev ready on :${PORT}`);
}
```

```typescript
// e2e/global-teardown.ts
export default async function globalTeardown() {
  const pid = Number(process.env.__WRANGLER_PID);
  if (pid) {
    try {
      process.kill(pid, "SIGTERM");
    } catch {
      // already gone
    }
  }
}
```

---

## Running UI Mode

```bash
# Start UI mode (opens Chromium desktop app)
pnpm exec playwright test --ui

# UI mode with a specific port for wrangler
WORKER_PORT=9000 pnpm exec playwright test --ui

# Debug a single test file in UI mode
pnpm exec playwright test --ui e2e/api.spec.ts

# Headed mode (browser visible but no UI chrome)
pnpm exec playwright test --headed

# Expose a debug port for DevTools Protocol
PWDEBUG=1 pnpm exec playwright test e2e/api.spec.ts
```

---

## Writing Tests That Benefit From UI Mode

```typescript
// e2e/api.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Worker API", () => {
  test("GET /users returns JSON array", async ({ request }) => {
    const res = await request.get("/users");
    await expect(res).toBeOK();
    const body = await res.json();
    expect(Array.isArray(body)).toBe(true);
  });

  test("POST /users creates a user", async ({ request }) => {
    const res = await request.post("/users", {
      data: { name: "Ada Lovelace", email: "ada@example.com" },
    });
    expect(res.status()).toBe(201);
    const user = await res.json();
    expect(user).toMatchObject({ name: "Ada Lovelace" });
  });
});
```

For UI-rendered Workers (e.g., Workers serving HTML via Hono):

```typescript
// e2e/ui.spec.ts
import { test, expect } from "@playwright/test";

test("dashboard renders user list", async ({ page }) => {
  await page.goto("/dashboard");

  // UI mode pauses here automatically when --ui is active
  // and you click the step button
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount({ min: 1 });
});

test("error boundary shows fallback UI on 500", async ({ page }) => {
  // Intercept the Worker's internal fetch to force a failure
  await page.route("**/api/data", (route) => route.abort("failed"));
  await page.goto("/dashboard");
  await expect(page.getByText("Something went wrong")).toBeVisible();
});
```

---

## Inspecting Worker Network Calls in UI Mode

Workers often call external services via `fetch()`. Use `page.route()` to
intercept and stub in tests while seeing the stubs highlighted in UI mode's
network panel:

```typescript
test("shows cached badge when CDN hit", async ({ page }) => {
  // Stub the upstream API
  await page.route("https://api.upstream.com/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ source: "cache", data: [] }),
    });
  });

  await page.goto("/feed");
  await expect(page.getByTestId("cache-badge")).toBeVisible();
});
```

In UI mode the route intercept appears in the **Network** tab with a teal
"Mocked" badge, making it easy to verify that stubs are firing.

---

## Trace Viewer: Time-Travel Debugging

After a test run, open the HTML report to access traces:

```bash
pnpm exec playwright show-report
```

For a specific trace file:

```bash
pnpm exec playwright show-trace test-results/api-spec-ts-/trace.zip
```

In UI mode, clicking a failed test automatically opens its trace inline. Each
`await` step becomes a time-travel snapshot — hover over any action to see the
DOM state, console logs, and network calls at that moment.

---

## Watch Mode Without UI

For headless CI-like watching during development:

```bash
# Re-run on file change (Playwright ≥ 1.43)
pnpm exec playwright test --watch

# With only the files you care about
pnpm exec playwright test --watch e2e/api.spec.ts
```

---

## Anti-patterns

- **Not adding a health-check endpoint to the Worker.** `waitForPort` using a
  random endpoint may return non-500 status for wrong reasons (e.g., a 404 on
  `/health` if that route does not exist still returns "ready"). Add a
  `GET /health` that returns 200.
- **Running UI mode in CI.** UI mode requires a display server. In CI use
  `--reporter=github` and `--reporter=html` instead.
- **Hardcoding `localhost:8787` in tests.** Use `baseURL` from the config so
  that port overrides propagate automatically.
- **Not setting `trace: "on-first-retry"`.** Without traces, UI mode's
  time-travel panel is empty and flaky tests are very hard to debug.

---

## Gotchas

- `globalSetup` runs in a **separate Node process** from the test workers. You
  cannot share module-level state; use `process.env` for coordination.
- `wrangler dev --local` boots with a random SQLite D1 database. If your tests
  depend on seeded data, add a seed script to `globalSetup` after the port is
  ready.
- UI mode's file-watch does **not** restart `wrangler dev`. Worker source
  changes require a separate terminal with `wrangler dev` already running, or
  you rely on wrangler's own HMR.
- On Apple Silicon, `playwright install chromium` downloads the x86 binary by
  default. Add `--with-deps` to also install system deps:
  `playwright install --with-deps chromium`.

---

## Verification

```bash
# 1. Confirm Playwright version supports UI mode (≥ 1.32)
pnpm exec playwright --version

# 2. Run one test in headed mode to validate wrangler dev starts
pnpm exec playwright test --headed e2e/api.spec.ts

# 3. Open UI mode and step through the test
pnpm exec playwright test --ui

# 4. In CI: assert exit code is 0 on passing suite
pnpm exec playwright test --reporter=github
echo "Exit: $?"
```

---

## Related

- `playwright-e2e-workers-wrangler-dev.md`
- `wrangler-dev-local-d1-r2-kv.md`
- `wrangler-unstable-dev-programmatic-api-testing.md`
- `vitest-workers-miniflare-testing-setup.md`
- `workers-hmr-live-reload.md`

---

## Sources

- https://playwright.dev/docs/test-ui-mode
- https://playwright.dev/docs/trace-viewer-intro
- https://playwright.dev/docs/api/class-testconfig#test-config-global-setup
- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://playwright.dev/docs/network#modify-requests
