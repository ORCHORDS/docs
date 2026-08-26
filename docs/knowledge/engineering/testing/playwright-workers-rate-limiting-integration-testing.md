# Playwright Workers Rate Limiting Integration Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker enforces per-IP or per-user rate limits via Durable Objects or Workers KV
counters. You need end-to-end tests that exercise the 429 response path, assert that retry-after
headers are correct, and confirm that the UI gracefully shows an error state—all without hitting
live rate limit quotas in CI. Playwright's network interception and parallel page support make it
the right tool once the UI layer is in scope; k6 covers raw throughput, but Playwright covers the
user-visible behaviour when the limit trips.

---

## Context

Rate limiting in Workers typically uses one of two approaches:

1. **Durable Object counter** — a DO stores a request count with a TTL reset; returns 429 when
   the count exceeds a threshold.
2. **Workers KV + atomic CAS** — a KV entry holds a rolling count; 429 is returned if the
   read-modify-write sequence observes the limit.

For Playwright integration tests the Worker is run locally via `wrangler dev --local`; Playwright
controls a real Chromium/Firefox/WebKit browser and intercepts or modifies network responses as
needed to trigger the 429 path without needing to exhaust the actual counter.

---

## Project Layout

```
├── src/
│   └── worker.ts          # The Worker under test
├── tests/
│   ├── fixtures.ts        # Playwright fixtures
│   └── rate-limit.spec.ts # Rate limit tests
├── playwright.config.ts
└── wrangler.toml
```

---

## Playwright Config with Local Worker

```ts
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  use: {
    baseURL: "http://localhost:8787",
  },
  webServer: {
    command: "wrangler dev --local --port 8787",
    url: "http://localhost:8787/health",
    reuseExistingServer: !process.env.CI,
    timeout: 15_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
```

---

## Fixture: Network Interception for 429 Injection

When the real DO counter would require many requests to trip, inject 429 responses at the network
layer to test UI handling without draining the real counter:

```ts
// tests/fixtures.ts
import { test as base, type Page } from "@playwright/test";

type RateLimitFixtures = {
  rateLimitedPage: Page;
};

export const test = base.extend<RateLimitFixtures>({
  rateLimitedPage: async ({ page }, use) => {
    // Intercept the first matching API request and respond with 429
    await page.route("**/api/submit", (route) => {
      route.fulfill({
        status: 429,
        headers: {
          "Content-Type": "application/json",
          "Retry-After": "60",
          "X-RateLimit-Limit": "10",
          "X-RateLimit-Remaining": "0",
          "X-RateLimit-Reset": String(Math.floor(Date.now() / 1000) + 60),
        },
        body: JSON.stringify({ error: "rate_limit_exceeded", retryAfter: 60 }),
      });
    });
    await use(page);
  },
});

export { expect } from "@playwright/test";
```

---

## Testing the 429 UI Response

```ts
// tests/rate-limit.spec.ts
import { test, expect } from "./fixtures";

test.describe("rate limit UI behaviour", () => {
  test("shows rate-limit error banner when 429 is returned", async ({
    rateLimitedPage: page,
  }) => {
    await page.goto("/submit-form");

    await page.fill('[name="email"]', "user@example.com");
    await page.click('[type="submit"]');

    // The UI should show a rate-limit error, not a generic error
    await expect(page.locator('[data-testid="rate-limit-banner"]')).toBeVisible();
    await expect(page.locator('[data-testid="rate-limit-banner"]')).toContainText(
      /too many requests/i
    );
  });

  test("displays retry countdown from Retry-After header", async ({
    rateLimitedPage: page,
  }) => {
    await page.goto("/submit-form");
    await page.fill('[name="email"]', "user@example.com");
    await page.click('[type="submit"]');

    // Countdown element should reference the 60-second window
    const countdown = page.locator('[data-testid="retry-countdown"]');
    await expect(countdown).toBeVisible();
    const text = await countdown.textContent();
    expect(text).toMatch(/60|1 minute/i);
  });

  test("submit button is disabled during rate limit window", async ({
    rateLimitedPage: page,
  }) => {
    await page.goto("/submit-form");
    await page.fill('[name="email"]', "user@example.com");
    await page.click('[type="submit"]');

    await expect(page.locator('[type="submit"]')).toBeDisabled();
  });
});
```

---

## Testing Real Counter Trip via wrangler dev

For tests where the real DO counter must actually be exhausted, use a test-only Worker route that
resets the counter and another that fires bursts:

```ts
// tests/rate-limit.spec.ts (continued)
test.describe("real rate limit counter", () => {
  test.beforeEach(async ({ request }) => {
    // Test-only reset endpoint — guarded by a secret header in the Worker
    await request.post("http://localhost:8787/__test/reset-rate-limit", {
      headers: { "X-Test-Secret": process.env.TEST_SECRET ?? "local-dev-secret" },
      data: { ip: "127.0.0.1" },
    });
  });

  test("returns 429 after threshold is reached", async ({ request }) => {
    const LIMIT = 5; // must match wrangler.toml var RATE_LIMIT_MAX

    // Fire requests up to the limit — all should succeed
    for (let i = 0; i < LIMIT; i++) {
      const res = await request.post("http://localhost:8787/api/submit", {
        data: { value: i },
      });
      expect(res.status()).toBe(200);
    }

    // The next one should be rate limited
    const limited = await request.post("http://localhost:8787/api/submit", {
      data: { value: "over-limit" },
    });
    expect(limited.status()).toBe(429);

    const body = await limited.json();
    expect(body).toMatchObject({ error: "rate_limit_exceeded" });
    expect(limited.headers()["retry-after"]).toBeTruthy();
  });
});
```

---

## Asserting Correct Retry-After Header Values

```ts
test("Retry-After header is a positive integer seconds value", async ({
  request,
}) => {
  // Exhaust counter via helper (same beforeEach reset as above)
  const LIMIT = 5;
  for (let i = 0; i < LIMIT; i++) {
    await request.post("http://localhost:8787/api/submit", { data: {} });
  }

  const res = await request.post("http://localhost:8787/api/submit", { data: {} });
  expect(res.status()).toBe(429);

  const retryAfter = res.headers()["retry-after"];
  expect(retryAfter).toBeDefined();

  const seconds = parseInt(retryAfter, 10);
  expect(Number.isInteger(seconds)).toBe(true);
  expect(seconds).toBeGreaterThan(0);
  expect(seconds).toBeLessThanOrEqual(3600); // sanity upper bound
});
```

---

## Testing Allowlist Bypass

Workers often allowlist internal IPs or service accounts. Test that the allowlist bypasses the
counter:

```ts
test("allowlisted X-Forwarded-For IP bypasses rate limit", async ({
  request,
}) => {
  const LIMIT = 5;
  // Exhaust the counter for the default IP
  for (let i = 0; i <= LIMIT; i++) {
    await request.post("http://localhost:8787/api/submit", { data: {} });
  }

  // Allowlisted IP should still succeed
  const res = await request.post("http://localhost:8787/api/submit", {
    headers: { "X-Forwarded-For": "10.0.0.1" }, // allowlisted in wrangler.toml vars
    data: {},
  });
  expect(res.status()).toBe(200);
});
```

---

## Anti-patterns

- **Using `page.waitForTimeout` to simulate "waiting out" the rate limit window** — fake timers
  do not work across the Playwright–Worker boundary. Instead mock the clock in the Worker's DO
  alarm or use the `__test/reset-rate-limit` endpoint.
- **Hard-coding the threshold in tests without reading `RATE_LIMIT_MAX` from env** — the
  threshold value lives in `wrangler.toml`; read it from `process.env` in `playwright.config.ts`
  so changing the limit doesn't silently break tests.
- **Intercepting all requests** — `page.route("**")` blocks health-check and static asset fetches,
  stalling `webServer.url` readiness polling.
- **Forgetting to reset the DO counter in `beforeEach`** — rate limit state persists across tests
  in `wrangler dev --local` when the DO storage file is not deleted.

---

## Gotchas

- `wrangler dev --local` binds the DO state to a `.wrangler/state` directory. Delete it between
  CI runs or add `--persist-to /dev/null` equivalent; there is no built-in ephemeral flag but
  you can set `WRANGLER_MINIFLARE_DURABLE_OBJECTS_PERSIST=false` in the env.
- When the Worker reads `cf.ip` for rate limiting, Playwright's local requests present `127.0.0.1`
  or `::1`. Ensure the Worker falls back to `X-Forwarded-For` or a default key in local mode.
- `page.route` intercepts only requests made from the browser context, not from `request` (the
  APIRequestContext). Use separate interception strategies for each.
- Playwright test isolation requires each test's browser context to be fresh; use `test.use({
  storageState: undefined })` if a previous test stored session cookies that contain rate-limit
  tokens.

---

## Verification

```bash
# Run only rate limit tests
npx playwright test tests/rate-limit.spec.ts

# Run with trace on failure for debugging the UI state
npx playwright test tests/rate-limit.spec.ts --trace on

# Run headed to watch the banner appear
npx playwright test tests/rate-limit.spec.ts --headed --timeout 60000
```

---

## Related

- `k6-workers-rate-limiter-load-test.md`
- `rate-limit-testing-strategies.md`
- `durable-objects-alarm-testing-miniflare.md`
- `playwright-workers-api-contract-e2e-testing.md`

---

## Sources

- Playwright network interception docs — https://playwright.dev/docs/network
- Cloudflare Rate Limiting with Durable Objects — https://developers.cloudflare.com/durable-objects/examples/rate-limiter/
- Wrangler dev local mode — https://developers.cloudflare.com/workers/wrangler/commands/#dev
- Playwright APIRequestContext — https://playwright.dev/docs/api/class-apirequestcontext
