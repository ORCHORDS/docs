# Playwright D1 Data-Driven Test Parameterization

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your E2E suite needs to exercise the same UI flow (form submission, search, profile edit) against multiple realistic data scenarios stored in D1. Copy-pasting the same test with minor data differences causes maintenance drift. You want a pattern that reads scenario rows from D1 or a seed file at fixture time and fans them out into parameterized Playwright tests.

## Context

Playwright supports `test.describe.configure({ mode: "parallel" })` and `test.each` for data-driven execution. The challenge with Cloudflare Workers + D1 is that test data lives server-side; the Playwright process needs a mechanism to read that data and map it to test parameters. Two patterns exist: (1) seed a local Miniflare D1 and read fixture rows from the DB in a `test.beforeAll`; (2) drive a staging Worker's Admin API to fetch scenario rows as test parameters. This article covers both.

---

## 1. Shared Fixture: Seeded D1 Scenario Table

Define scenario rows in a JSON seed file consumed both by `wrangler d1 execute` and Playwright fixtures.

```json
// tests/fixtures/user-scenarios.json
[
  { "id": 1, "name": "Alice Admin",   "role": "admin",   "plan": "pro",   "expected_nav": "Admin Panel" },
  { "id": 2, "name": "Bob Basic",    "role": "viewer",  "plan": "free",  "expected_nav": "Upgrade" },
  { "id": 3, "name": "Carol Collab", "role": "editor",  "plan": "team",  "expected_nav": "Team Settings" },
  { "id": 4, "name": "Dave Deleted", "role": "viewer",  "plan": "none",  "expected_nav": "Reactivate" }
]
```

```sql
-- tests/fixtures/seed-scenarios.sql
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  plan TEXT NOT NULL
);
INSERT OR REPLACE INTO users VALUES (1, 'Alice Admin',   'admin',  'pro');
INSERT OR REPLACE INTO users VALUES (2, 'Bob Basic',    'viewer', 'free');
INSERT OR REPLACE INTO users VALUES (3, 'Carol Collab', 'editor', 'team');
INSERT OR REPLACE INTO users VALUES (4, 'Dave Deleted', 'viewer', 'none');
```

---

## 2. Playwright Fixture: Loading Scenarios from JSON

```typescript
// tests/fixtures/d1-scenarios.ts
import { test as base } from "@playwright/test";
import scenarios from "./user-scenarios.json";

export type Scenario = (typeof scenarios)[number];

export const test = base.extend<{ scenario: Scenario }>({
  scenario: [
    async ({}, use) => {
      // Default fixture value — overridden per-test via test.each
      await use(scenarios[0]);
    },
    { scope: "test" },
  ],
});

export { expect } from "@playwright/test";
export { scenarios };
```

---

## 3. Parameterized Tests with `test.each`

```typescript
// tests/user-dashboard.spec.ts
import { test, expect, scenarios } from "./fixtures/d1-scenarios";

// Fan out one test per scenario row
for (const scenario of scenarios) {
  test(`dashboard nav for ${scenario.role}/${scenario.plan} — "${scenario.name}"`, async ({
    page,
  }) => {
    // Authenticate as this scenario user via cookie (pre-seeded session)
    await page.context().addCookies([
      {
        name: "session",
        value: `test-session-user-${scenario.id}`,
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.goto("/dashboard");
    await expect(page.getByTestId("nav-primary")).toContainText(
      scenario.expected_nav
    );
  });
}
```

---

## 4. Fixture: Reading Scenarios from a Running Worker's Admin API

When scenarios are too complex to maintain in JSON, read them directly from a staging D1 via the Worker's test-only Admin API.

```typescript
// tests/fixtures/d1-api-scenarios.ts
import { test as base, request } from "@playwright/test";

export interface ApiScenario {
  id: number;
  name: string;
  role: string;
  plan: string;
  expected_nav: string;
}

let cachedScenarios: ApiScenario[] | null = null;

export async function fetchScenarios(baseURL: string): Promise<ApiScenario[]> {
  if (cachedScenarios) return cachedScenarios;
  const ctx = await request.newContext({ baseURL });
  const res = await ctx.get("/test-admin/user-scenarios", {
    headers: { "X-Test-Secret": process.env.TEST_ADMIN_SECRET ?? "" },
  });
  if (!res.ok()) throw new Error(`Failed to fetch scenarios: ${res.status()}`);
  cachedScenarios = await res.json();
  await ctx.dispose();
  return cachedScenarios;
}

export const test = base.extend<{ scenario: ApiScenario }, { allScenarios: ApiScenario[] }>({
  allScenarios: [
    async ({ baseURL }, use) => {
      const rows = await fetchScenarios(baseURL ?? "");
      await use(rows);
    },
    { scope: "worker" },
  ],
  scenario: async ({ allScenarios }, use) => {
    await use(allScenarios[0]);
  },
});
```

```typescript
// tests/worker-api-scenarios.spec.ts
import { test, expect, fetchScenarios } from "./fixtures/d1-api-scenarios";

test.beforeAll(async ({ baseURL }) => {
  const rows = await fetchScenarios(baseURL ?? "http://localhost:8787");
  // Dynamically register tests (workaround for async test.each)
  // In practice, prefer the static JSON approach for parallel test runners
  console.log(`Loaded ${rows.length} scenarios from D1`);
});

// Static parameterization requires the scenario list to be resolved before collection.
// Use the JSON fixture for standard CI — reserve API fixture for smoke tests against staging.
test("admin role sees Admin Panel nav item", async ({ page }) => {
  await page.context().addCookies([
    { name: "session", value: "test-session-user-1", domain: "localhost", path: "/" },
  ]);
  await page.goto("/dashboard");
  await expect(page.getByTestId("nav-primary")).toContainText("Admin Panel");
});
```

---

## 5. Global Setup: Seeding D1 Before the Suite

```typescript
// tests/global-setup.ts
import { execSync } from "node:child_process";
import path from "node:path";

export default async function globalSetup() {
  // Seed scenarios into local Miniflare D1
  const seedFile = path.resolve(__dirname, "fixtures/seed-scenarios.sql");
  execSync(
    `npx wrangler d1 execute DB --local --file ${seedFile}`,
    { stdio: "inherit", env: { ...process.env } }
  );
  console.log("D1 scenarios seeded for Playwright suite");
}
```

```typescript
// playwright.config.ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  globalSetup: "./tests/global-setup.ts",
  use: {
    baseURL: "http://localhost:8787",
  },
  webServer: {
    command: "npx wrangler dev --local",
    url: "http://localhost:8787",
    reuseExistingServer: !process.env.CI,
  },
});
```

---

## 6. Parallel Scenario Execution

```typescript
// tests/user-dashboard.spec.ts (parallel variant)
import { test, expect, scenarios } from "./fixtures/d1-scenarios";

test.describe.configure({ mode: "parallel" });

for (const s of scenarios) {
  test(`${s.role} plan=${s.plan} sees expected nav`, async ({ page }) => {
    await page.context().addCookies([
      { name: "session", value: `test-session-user-${s.id}`, domain: "localhost", path: "/" },
    ]);
    await page.goto("/dashboard");
    await expect(page.getByTestId("nav-primary")).toContainText(s.expected_nav);
  });
}
```

Run with Playwright's built-in sharding to split across CI workers:

```bash
npx playwright test --shard=1/4
npx playwright test --shard=2/4
```

---

## Anti-patterns

- **Fetching D1 rows inside `test()` bodies** — async DB fetches during test execution introduce variable latency; load all scenario data in `globalSetup` or worker-scoped fixtures.
- **Using `OFFSET` pagination to read scenarios** — for seeded test data, `SELECT * FROM scenarios` returning all rows at once is safer; pagination is unnecessary and adds fragility.
- **Mutable scenario state between tests** — if one test writes back to D1, it can corrupt subsequent parameterized runs; reset state with `ROLLBACK` or truncate in `afterEach`.
- **Deriving `expected_*` values inside the test** — the expected outcome should live in the scenario row, not be computed by the test; computing expectations in tests couples test logic to application logic.
- **Hardcoded user IDs in session cookies** — use the `scenario.id` field; coupling cookie values to magic numbers breaks when new scenarios are inserted.

## Gotchas

- Playwright's `test.each` requires the dataset to be statically available at collection time (before any async operations). Prefer JSON seed files for parameterization; use fixtures for runtime data access.
- `test.describe.configure({ mode: "parallel" })` applies to the entire file; if some tests in the file are order-dependent, move them to a separate spec file.
- Wrangler's `--local` D1 mode uses a SQLite file in `.wrangler/state/`; deleting this directory between CI runs prevents stale scenario data from leaking.
- The `worker`-scoped fixture pattern in Playwright runs once per worker process, not once globally; `fetchScenarios` caches the result to avoid duplicate API calls across the worker's tests.

## Verification

```bash
# Seed and run all parameterized scenario tests
npx wrangler d1 execute DB --local --file tests/fixtures/seed-scenarios.sql
npx playwright test tests/user-dashboard.spec.ts --reporter=list

# Confirm parallel execution reduces wall-clock time
time npx playwright test --workers=4 tests/user-dashboard.spec.ts
```

## Related

- `playwright-d1-state-reset-between-tests.md`
- `d1-test-fixtures-wrangler-seed.md`
- `test-data-management-d1-factories.md`
- `playwright-fixtures.md`
- `playwright-parallel-execution.md`

## Sources

- https://playwright.dev/docs/test-parameterize
- https://playwright.dev/docs/test-fixtures
- https://developers.cloudflare.com/d1/platform/local-development/
- https://playwright.dev/docs/test-parallel
