# Playwright D1 Database State Reset Between Tests

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

End-to-end tests against a Cloudflare Workers application backed by D1 fail intermittently because rows inserted in one test bleed into assertions of a later test. Running the full suite in isolation passes; running it in order fails. You need a reliable, fast mechanism to wipe D1 state between every Playwright test without tearing down and re-creating the database.

## Context

Playwright runs tests in separate browser contexts but the Workers process (whether via `wrangler dev` or a preview deployment) shares a single D1 database instance. Unlike in-memory stores, D1 persists across requests. The standard approach is a dedicated `/__test/reset` HTTP endpoint that your Worker exposes only in `ENVIRONMENT=test`, which Playwright calls in a `beforeEach` fixture. For local runs this hits `wrangler dev --local`, for CI it targets a dedicated test D1 binding. The reset endpoint executes `DELETE FROM` or truncation SQL wrapped in a D1 batch transaction, then re-seeds required baseline rows.

---

## 1. Worker-side Reset Endpoint

```typescript
// src/routes/test-reset.ts
import type { Env } from '../types';

export async function handleTestReset(request: Request, env: Env): Promise<Response> {
  if (env.ENVIRONMENT !== 'test') {
    return new Response('Not found', { status: 404 });
  }

  const tables = ['order_items', 'orders', 'products', 'users'];

  const stmts = tables.map((t) => env.DB.prepare(`DELETE FROM ${t}`));

  // Seed minimal baseline
  stmts.push(
    env.DB.prepare('INSERT INTO users (id, email, role) VALUES (?, ?, ?)').bind(
      'seed-user-1',
      'seed@example.com',
      'admin'
    )
  );

  await env.DB.batch(stmts);

  return new Response(JSON.stringify({ ok: true, tables }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

Mount it in the Worker router behind a guard:

```typescript
// src/index.ts
import { handleTestReset } from './routes/test-reset';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/__test/reset' && request.method === 'POST') {
      return handleTestReset(request, env);
    }
    // ... normal routing
  },
};
```

---

## 2. Playwright Global Fixture for Reset

```typescript
// tests/fixtures/db-reset.ts
import { test as base, request } from '@playwright/test';

type DbResetFixture = { resetDb: () => Promise<void> };

export const test = base.extend<DbResetFixture>({
  resetDb: async ({ baseURL }, use) => {
    const reset = async () => {
      const ctx = await request.newContext();
      const res = await ctx.post(`${baseURL}/__test/reset`);
      if (!res.ok()) {
        throw new Error(`DB reset failed: ${res.status()} ${await res.text()}`);
      }
      await ctx.dispose();
    };
    await use(reset);
  },
});

export { expect } from '@playwright/test';
```

```typescript
// tests/orders.spec.ts
import { test, expect } from './fixtures/db-reset';

test.beforeEach(async ({ resetDb }) => {
  await resetDb();
});

test('creates an order', async ({ page, baseURL }) => {
  await page.goto(`${baseURL}/orders/new`);
  await page.fill('[data-testid=product-name]', 'Widget A');
  await page.click('[data-testid=submit]');
  await expect(page.locator('[data-testid=order-id]')).toBeVisible();
});

test('lists only own orders', async ({ page, baseURL }) => {
  // No leftover rows from previous test
  await page.goto(`${baseURL}/orders`);
  await expect(page.locator('[data-testid=order-row]')).toHaveCount(0);
});
```

---

## 3. Parallel Worker Isolation via Tenant ID

When Playwright runs tests in parallel across workers, each worker needs its own data partition to avoid cross-worker conflicts:

```typescript
// tests/fixtures/tenant-db.ts
import { test as base } from '@playwright/test';
import { randomUUID } from 'crypto';

export const test = base.extend<{ tenantId: string }>({
  tenantId: async ({}, use) => {
    await use(`tenant-${randomUUID()}`);
  },
});
```

```typescript
// Worker endpoint uses tenantId header to scope DELETEs
export async function handleTestReset(request: Request, env: Env): Promise<Response> {
  if (env.ENVIRONMENT !== 'test') return new Response('Not found', { status: 404 });

  const tenantId = request.headers.get('X-Test-Tenant') ?? '';
  if (!tenantId) return new Response('Missing tenant', { status: 400 });

  await env.DB.batch([
    env.DB.prepare('DELETE FROM orders WHERE tenant_id = ?').bind(tenantId),
    env.DB.prepare('DELETE FROM users WHERE tenant_id = ?').bind(tenantId),
  ]);

  return new Response(JSON.stringify({ ok: true }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

---

## 4. Playwright Config: Local vs CI D1

```typescript
// playwright.config.ts
import { defineConfig } from '@playwright/test';

const isCI = !!process.env.CI;

export default defineConfig({
  use: {
    baseURL: isCI
      ? `https://my-app-test.workers.dev`
      : 'http://localhost:8788',
  },
  webServer: isCI
    ? undefined
    : {
        command: 'wrangler dev --local --env test',
        port: 8788,
        reuseExistingServer: !process.env.CI,
        timeout: 30_000,
      },
  workers: isCI ? 2 : 1, // limit parallelism against shared CI D1
});
```

---

## 5. Snapshot Assertion After Seeded State

```typescript
// tests/product-list.spec.ts
import { test, expect } from './fixtures/db-reset';

test.beforeEach(async ({ resetDb, request, baseURL }) => {
  await resetDb();
  // Insert specific seed rows for this test
  await request.post(`${baseURL}/__test/seed`, {
    data: {
      products: [
        { id: 'p1', name: 'Widget A', price: 999 },
        { id: 'p2', name: 'Widget B', price: 1499 },
      ],
    },
  });
});

test('product list matches snapshot', async ({ page, baseURL }) => {
  await page.goto(`${baseURL}/products`);
  await expect(page.locator('[data-testid=product-list]')).toMatchAriaSnapshot(`
    - list:
      - listitem: Widget A $9.99
      - listitem: Widget B $14.99
  `);
});
```

---

## Anti-patterns

- **Calling reset in `afterEach`**: A test failure aborts the hook and state leaks into the next test. Always reset in `beforeEach`.
- **Truncating via schema drop/recreate**: Running `DROP TABLE` and migrations in each reset is 10-100x slower than `DELETE FROM`.
- **Sharing a D1 database between dev and test environments**: Always use separate `wrangler.test.toml` bindings or `--env test`.
- **Resetting from the browser context**: Use the Playwright `request` API (server-side) not `page.evaluate(fetch(...))` to avoid CORS issues.
- **Hardcoding the reset URL without the guard**: Exposing `/__test/reset` in production deletes live data.

---

## Gotchas

- D1 `batch()` is not atomic by default in the HTTP API; use `BEGIN`/`COMMIT` statements or the Workers binding batch for true atomicity.
- `wrangler dev --local` uses a SQLite file under `.wrangler/state/`. If the file is corrupted, delete it and restart.
- Playwright's `request` fixture shares the browser's base URL but is not affected by `storageState`. Authentication headers must be added manually to reset requests.
- Foreign key constraints in D1 require deleting child tables before parent tables; order your `DELETE` statements accordingly.
- In `--remote` mode, each reset incurs network latency. Budget 200-500 ms per reset and set `test.setTimeout` accordingly.

---

## Verification

```bash
# Run tests twice in sequence; second run should not see first run's data
npx playwright test tests/orders.spec.ts --repeat-each=3

# Confirm reset endpoint is absent in production build
curl -X POST https://my-app.workers.dev/__test/reset
# Expected: 404 Not found

# Confirm reset endpoint works locally
curl -X POST http://localhost:8788/__test/reset
# Expected: {"ok":true,"tables":["order_items","orders","products","users"]}
```

---

## Related

- `d1-test-fixtures-wrangler-seed.md`
- `miniflare-d1-integration-testing.md`
- `playwright-fixtures.md`
- `playwright-cloudflare-pages-e2e.md`
- `test-database-isolation.md`

---

## Sources

- Cloudflare D1 Workers binding docs: https://developers.cloudflare.com/d1/worker-api/
- Playwright `request` fixture: https://playwright.dev/docs/api/class-apirequestcontext
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Playwright `beforeEach` hook ordering: https://playwright.dev/docs/api/class-test#test-before-each
