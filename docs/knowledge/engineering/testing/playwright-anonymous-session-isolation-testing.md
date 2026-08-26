# Playwright Anonymous Session Isolation Testing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your example project application on example.com has pages accessible to unauthenticated users. During E2E
test runs, cookies or `localStorage` leaking between test cases cause anonymous sessions to
accidentally inherit state from a previous authenticated user, producing false positives (features
appear available when they should be gated) or false negatives (pages redirect to login when they
should render publicly). You need each anonymous-user test to start with a completely clean browser
context, independent of any auth fixtures.

## Context

Playwright's default `page` fixture reuses a browser context within a worker process. When
`storageState` auth fixtures are loaded for some tests and not others, the context isolation depends
on test ordering. On Cloudflare Pages + Workers, anonymous requests carry no session cookie; the
Worker reads `request.headers.get('Cookie')` and branches on its absence. Tests that do not
explicitly clear state may carry a `__Secure-session` cookie set by a prior test, causing the Worker
to treat the request as authenticated.

## 1. Dedicated anonymous context fixture

```ts
// test/fixtures/anonymous.ts
import { test as base, BrowserContext, Page } from '@playwright/test';

type AnonymousFixtures = {
  anonContext: BrowserContext;
  anonPage: Page;
};

export const test = base.extend<AnonymousFixtures>({
  // A fresh browser context with no storage state, no cookies, no
  // service workers from prior runs.
  anonContext: async ({ browser }, use) => {
    const ctx = await browser.newContext({
      storageState: undefined,    // explicitly no auth state
      serviceWorkers: 'block',    // prevent SW cache interference
    });
    await use(ctx);
    await ctx.close();
  },

  anonPage: async ({ anonContext }, use) => {
    const page = await anonContext.newPage();
    await use(page);
    await page.close();
  },
});

export { expect } from '@playwright/test';
```

## 2. Verifying no cookies survive between tests

```ts
// test/anonymous/cookie-isolation.spec.ts
import { test, expect } from '../fixtures/anonymous';

test.describe('anonymous session isolation', () => {
  test('no cookies are present on first navigation', async ({ anonPage }) => {
    const response = await anonPage.goto('/');
    expect(response?.status()).toBe(200);

    const cookies = await anonPage.context().cookies();
    const sessionCookies = cookies.filter(c =>
      c.name.startsWith('__Secure-') || c.name === 'session',
    );
    expect(sessionCookies).toHaveLength(0);
  });

  test('localStorage is empty for anonymous users', async ({ anonPage }) => {
    await anonPage.goto('/');
    const keys = await anonPage.evaluate(() => Object.keys(localStorage));
    expect(keys).toHaveLength(0);
  });
});
```

## 3. Anonymous access to gated routes returns 401

```ts
// test/anonymous/auth-gates.spec.ts
import { test, expect } from '../fixtures/anonymous';

const GATED_ROUTES = ['/dashboard', '/settings', '/api/me'];

for (const route of GATED_ROUTES) {
  test(`anonymous request to ${route} is rejected`, async ({ anonPage }) => {
    const [response] = await Promise.all([
      anonPage.waitForResponse(resp => resp.url().includes(route)),
      anonPage.goto(route),
    ]);
    // Workers should return 401 or redirect to /login — not 200
    expect([401, 302, 307]).toContain(response.status());
  });
}
```

## 4. Anonymous API requests carry no authorization header

```ts
// test/anonymous/api-headers.spec.ts
import { test, expect } from '../fixtures/anonymous';

test('anonymous fetch carries no Authorization header', async ({ anonPage }) => {
  let capturedAuthHeader: string | null = null;

  await anonPage.route('**/api/**', async route => {
    capturedAuthHeader =
      route.request().headers()['authorization'] ?? null;
    await route.continue();
  });

  await anonPage.goto('/');
  // Trigger an API call the page makes on load
  await anonPage.waitForLoadState('networkidle');

  expect(capturedAuthHeader).toBeNull();
});
```

## 5. Parallel anonymous tests do not share context

```ts
// playwright.config.ts (excerpt)
import { defineConfig } from '@playwright/test';

export default defineConfig({
  // Each worker gets its own browser; contexts never cross workers
  workers: process.env.CI ? 4 : 2,
  use: {
    baseURL: process.env.BASE_URL ?? 'https://example.com',
    // No global storageState — anonymous is the baseline
  },
  projects: [
    {
      name: 'anonymous',
      testMatch: /anonymous\/.*.spec.ts/,
      use: {
        storageState: undefined,
      },
    },
    {
      name: 'authenticated',
      testMatch: /auth\/.*.spec.ts/,
      use: {
        storageState: 'playwright/.auth/user.json',
      },
    },
  ],
});
```

## 6. Asserting public page renders without a Worker redirect

```ts
// test/anonymous/public-pages.spec.ts
import { test, expect } from '../fixtures/anonymous';

test('home page renders marketing content for anonymous user', async ({
  anonPage,
}) => {
  await anonPage.goto('/');
  // Must NOT be redirected to /login
  expect(anonPage.url()).not.toContain('/login');
  await expect(anonPage.locator('h1')).toBeVisible();
  // Ensure login CTA is present (not the dashboard nav)
  await expect(anonPage.getByRole('link', { name: /sign in/i })).toBeVisible();
  await expect(
    anonPage.getByRole('link', { name: /dashboard/i }),
  ).not.toBeVisible();
});
```

## Anti-patterns

- **Using the default `page` fixture for anonymous tests**: the context may carry `storageState`
  injected via `use.storageState` in `playwright.config.ts`, silently authenticating the request.
- **Calling `page.context().clearCookies()` in `beforeEach`**: this clears cookies on a shared
  context, which races with parallel test workers using the same context object.
- **Asserting on redirect URL alone**: the Workers may issue a 302 to `/login?next=…` for some
  gated routes but serve a 200 with an empty body for API routes; always check status code as well.
- **Blocking service workers globally in `playwright.config.ts`**: breaks SW-dependent features in
  the authenticated project; scope the block to the anonymous fixture only.

## Gotchas

- `storageState: undefined` in `use` config is not the same as omitting the key if a parent config
  sets it; always pass `undefined` explicitly in the anonymous project config.
- Cloudflare Pages Functions can set `__Host-` or `__Secure-` prefixed cookies on the first
  response even for anonymous visits (e.g. CSRF tokens). These are expected and should not be
  treated as auth leakage; filter cookies by name prefix before asserting.
- When running against a local `wrangler pages dev` instance, `localhost` ignores `Secure` cookie
  flag; cookie assertions about `Secure` flag will behave differently locally vs. production.
- `page.waitForLoadState('networkidle')` can time out on pages that poll an API; use
  `waitForLoadState('domcontentloaded')` or `waitForResponse` with a specific route pattern instead.

## Verification

```bash
# Run anonymous project only
npx playwright test --project=anonymous

# Confirm no auth cookies are set
npx playwright test --project=anonymous --reporter=list 2>&1 | grep 'cookie'

# Run in headed mode to visually inspect anonymous page state
npx playwright test --project=anonymous --headed test/anonymous/public-pages.spec.ts
```

## Related

- `playwright-authentication-state.md`
- `playwright-workers-auth-flow-session-persistence-e2e.md`
- `playwright-d1-state-reset-between-tests.md`
- `playwright-cloudflare-pages-e2e.md`
- `playwright-fixtures.md`

## Sources

- https://playwright.dev/docs/browser-contexts
- https://playwright.dev/docs/auth
- https://developers.cloudflare.com/pages/functions/
- https://playwright.dev/docs/test-projects
