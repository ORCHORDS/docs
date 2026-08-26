# playwright-cloudflare-pages-e2e

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

E2E tests run against `localhost` but Cloudflare Pages
preview deployments fail silently: Cloudflare Access blocks
the test runner, preview URLs redirect to a login challenge,
or mobile viewports expose layout bugs that only exist on
the CDN-served build, not the dev server.

## Context

Cloudflare Pages creates a unique preview URL for every
pushed branch (`<branch>.<project>.pages.dev`). Testing
against these URLs exercises the real CDN path, edge cache
headers, and any Pages Functions (Workers) attached to the
deployment. The main challenges are: (1) discovering the
preview URL from CI, (2) bypassing Cloudflare Access on
preview branches, (3) asserting on Cloudflare-specific
response headers, and (4) running the same spec under
mobile and desktop viewport profiles.

## Discovering the Preview URL in CI

Wrangler prints the deployment URL on stdout. Capture it
and export it as an environment variable:

```yaml
# .github/workflows/e2e.yml
- name: Deploy to Pages
  id: deploy
  run: |
    OUTPUT=$(npx wrangler pages deploy ./dist \
      --project-name example project \
      --branch "${{ github.head_ref }}")
    echo "$OUTPUT"
    URL=$(echo "$OUTPUT" \
      | grep -oP 'https://[^\s]+pages\.dev')
    echo "PAGES_URL=$URL" >> "$GITHUB_OUTPUT"

- name: Run E2E tests
  env:
    BASE_URL: ${{ steps.deploy.outputs.PAGES_URL }}
  run: npx playwright test
```

`playwright.config.ts` reads `BASE_URL`:

```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:8788',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-chrome',
      use: { ...devices['Pixel 7'] } },
    { name: 'mobile-safari',
      use: { ...devices['iPhone 15'] } },
  ],
});
```

## Testing Behind Cloudflare Access

Preview deployments protected by Cloudflare Access reject
unauthenticated requests with HTTP 403 and an HTML login
page. Playwright receives the Access challenge rather than
the app.

Two strategies:

**Strategy A — Service Token (recommended for CI)**

Create a Cloudflare Access Service Token in the Access
dashboard and pass the credentials in request headers:

```ts
// playwright.config.ts
use: {
  baseURL: process.env.BASE_URL,
  extraHTTPHeaders: {
    'CF-Access-Client-Id':
      process.env.CF_ACCESS_CLIENT_ID ?? '',
    'CF-Access-Client-Secret':
      process.env.CF_ACCESS_CLIENT_SECRET ?? '',
  },
},
```

Store the token pair in GitHub Actions secrets. The Access
policy must include a rule that matches the service token.

**Strategy B — Bypass policy on preview branches**

In the Cloudflare Access policy, add an exception rule for
URL patterns matching `*--<project>.pages.dev` and restrict
it to your CI IP range via an IP CIDR rule. This avoids
managing token rotation but is less precise.

| Strategy              | Pros                        | Cons                      |
|-----------------------|-----------------------------|---------------------------|
| Service Token headers | Precise, auditable          | Token rotation required   |
| IP CIDR bypass        | No secret management        | Wide surface if IPs shift |
| No Access on preview  | Zero friction                | Exposes preview publicly  |

## Asserting Cloudflare-Specific Headers

Pages deployments add Cloudflare-managed headers. Assert
on them to confirm the response came from the edge:

```ts
// tests/cf-headers.spec.ts
import { test, expect } from '@playwright/test';

test('edge cache hit on second request', async ({
  request,
}) => {
  // Prime the cache
  await request.get('/');

  const res = await request.get('/');
  const cacheStatus =
    res.headers()['cf-cache-status'] ?? '';
  expect(['HIT', 'REVALIDATED']).toContain(
    cacheStatus.toUpperCase()
  );
});

test('security headers present', async ({ request }) => {
  const res = await request.get('/');
  expect(res.headers()['x-content-type-options'])
    .toBe('nosniff');
  expect(res.headers()['x-frame-options'])
    .toBe('SAMEORIGIN');
});

test('pages functions worker responds', async ({
  request,
}) => {
  const res = await request.get('/api/health');
  expect(res.status()).toBe(200);
  const body = await res.json<{ ok: boolean }>();
  expect(body.ok).toBe(true);
});
```

Common Cloudflare response headers to assert:

| Header                 | Expected value (example) | Notes                    |
|------------------------|--------------------------|--------------------------|
| `cf-cache-status`      | `HIT`                    | Only after first request |
| `cf-ray`               | `<hex>-<datacenter>`     | Confirms CDN path        |
| `server`               | `cloudflare`             | Present on all responses |
| `x-content-type-options` | `nosniff`              | Via Pages headers rule   |

## Mobile Viewport E2E Flows

Run the same page-object spec under multiple projects to
catch mobile-specific regressions:

```ts
// tests/home.spec.ts
import { test, expect } from '@playwright/test';
import { HomePage } from './pages/home.page';

test('hero CTA is tappable on mobile', async ({ page }) => {
  const home = new HomePage(page);
  await home.goto();

  const cta = page.getByRole('link', { name: /get started/i });
  // Confirm the element is within the viewport on mobile
  await expect(cta).toBeInViewport();

  const box = await cta.boundingBox();
  // Minimum tap target: 44 × 44 CSS px (Apple HIG / WCAG 2.5.5)
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);
});

test('nav menu collapses to hamburger on mobile', async ({
  page,
  isMobile,
}) => {
  await page.goto('/');

  if (isMobile) {
    await expect(
      page.getByRole('button', { name: /menu/i })
    ).toBeVisible();
    await expect(
      page.getByRole('navigation')
    ).not.toBeVisible();
  } else {
    await expect(
      page.getByRole('navigation')
    ).toBeVisible();
  }
});
```

`isMobile` is `true` when the project's device descriptor
sets `isMobile: true` (all `devices['iPhone *']` entries).

## Waiting for Edge Propagation

After a Pages deploy, CDN nodes take 10–30 s to propagate
assets. Use `waitForResponse` or a poll loop rather than a
fixed sleep:

```ts
// Global setup: poll until the new deployment responds
import { request } from '@playwright/test';

async function waitForDeployment(url: string) {
  const ctx = await request.newContext();
  for (let i = 0; i < 20; i++) {
    try {
      const res = await ctx.get(url, { timeout: 5000 });
      if (res.ok()) return;
    } catch {
      // network error — keep polling
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  throw new Error(`Deployment not reachable: ${url}`);
}

export default waitForDeployment;
```

Call from `globalSetup` in `playwright.config.ts`:

```ts
globalSetup: require.resolve('./tests/global-setup'),
```

## Anti-patterns

- Testing only against `localhost:8788` (`wrangler pages
  dev`) — Pages Functions may behave differently from
  production; cache headers are absent locally.
- Sharing a single Cloudflare Access Service Token across
  dev, staging, and CI — rotate separately per environment.
- Asserting `cf-cache-status: HIT` on the first request —
  the edge cold-starts and returns `MISS` or `DYNAMIC`.
- Using `page.waitForTimeout(5000)` after deploy to wait
  for propagation — flaky under slow edge propagation; use
  polling instead.
- Running mobile and desktop tests in the same Playwright
  worker process — project isolation prevents cross-device
  cookie/storage leakage; always use separate `projects`.

## Gotchas

- `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers
  are only forwarded on fetch/XHR requests, not on top-
  level navigation in some browsers. Use
  `page.setExtraHTTPHeaders()` inside the test for
  navigation as well as `request.get()`.
- Preview URLs expire after 90 days by default; old CI logs
  pointing to dead URLs will appear as failures if re-run.
- `cf-ray` header value changes on each request even for
  cached responses — never assert its exact value, only
  that it is non-empty.
- Cloudflare compresses responses at the edge; assert on
  `content-encoding: br` only when Brotli is confirmed in
  the Pages headers configuration.
- Pages Functions (`functions/` directory) deploy as
  Workers; they share the same `wrangler.toml` bindings but
  the `env` object is populated differently than in a
  standalone Worker.

## Verification

```bash
# Smoke-run against the deployed preview URL
BASE_URL=https://abc123.example project.pages.dev \
  npx playwright test tests/cf-headers.spec.ts \
  --reporter=list

# Run only mobile projects
npx playwright test --project=mobile-chrome \
                    --project=mobile-safari

# Debug a single test with the UI
BASE_URL=https://abc123.example project.pages.dev \
  npx playwright test --ui tests/home.spec.ts
```

A full suite of 30 specs across three projects (chromium,
mobile-chrome, mobile-safari) typically completes in under
4 minutes against a Pages preview URL using a 4-worker
Playwright run.

## Related

- `testing/playwright-setup.md`
- `testing/playwright-mobile-device-emulation.md`
- `testing/playwright-authentication-state.md`
- `testing/workers-unit-testing-fetch-mocking.md`
- `testing/visual-regression-testing-cloudflare-pages.md`

## Source URLs (verified 2026-08-22)

- https://developers.cloudflare.com/pages/how-to/preview-deployments/
- https://developers.cloudflare.com/cloudflare-one/identity/service-auth/service-tokens/
- https://developers.cloudflare.com/cache/concepts/cache-responses/
- https://playwright.dev/docs/test-projects
- https://playwright.dev/docs/api/class-apirequestcontext
