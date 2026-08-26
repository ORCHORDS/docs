# Playwright Workers Feature Flag A/B Test Verification

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare Workers application serves different UI variants to users based on feature flags resolved at the edge. Manual QA must open two browsers and toggle a flag to check each variant. Automated Playwright tests need to verify both the control and the variant render correctly, that the correct analytics events are fired, and that the flag resolution logic in the Worker behaves consistently — without depending on a live feature-flag service that may be unavailable in CI.

## Context

Feature flags in a Workers application are commonly resolved in one of three ways: reading a KV namespace, calling a remote flag service (LaunchDarkly, Statsig, etc.), or decoding a signed cookie set by the Worker itself. Playwright intercepts Worker responses or injects request headers/cookies to force a specific flag variant in each test. This approach tests the full rendering path without requiring a live flag service and without modifying the deployed Worker code.

---

## Strategy 1 — Force a flag variant via request header interception

The Worker reads an `X-Feature-Flag` header (added by a trusted CDN or internal proxy) to select the variant. Playwright sets this header on every request within a test.

```typescript
// tests/feature-flags/checkout-redesign.spec.ts
import { test, expect } from '@playwright/test';

test.describe('checkout-redesign flag', () => {
  test('control shows legacy checkout', async ({ page }) => {
    await page.route('**/*', (route) =>
      route.continue({
        headers: {
          ...route.request().headers(),
          'X-Feature-Flag-checkout-redesign': 'control',
        },
      })
    );

    await page.goto('/checkout');
    await expect(page.getByTestId('legacy-checkout-form')).toBeVisible();
    await expect(page.getByTestId('new-checkout-form')).not.toBeAttached();
  });

  test('variant shows new checkout', async ({ page }) => {
    await page.route('**/*', (route) =>
      route.continue({
        headers: {
          ...route.request().headers(),
          'X-Feature-Flag-checkout-redesign': 'variant-a',
        },
      })
    );

    await page.goto('/checkout');
    await expect(page.getByTestId('new-checkout-form')).toBeVisible();
    await expect(page.getByTestId('legacy-checkout-form')).not.toBeAttached();
  });
});
```

---

## Strategy 2 — Mock the KV flag store via `page.route`

When the Worker fetches flag configuration from KV, intercept the internal Worker fetch and return a crafted response to pin the flag value.

```typescript
// tests/feature-flags/kv-flag-mock.spec.ts
import { test, expect } from '@playwright/test';

function routeWithFlag(page: import('@playwright/test').Page, flagName: string, value: string) {
  // Intercept the Worker's KV-backed flag resolution endpoint
  return page.route(`**/internal/flags/${flagName}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ flag: flagName, value, ttl: 60 }),
    })
  );
}

test.describe('dark-mode-beta flag via KV mock', () => {
  test('control renders light theme', async ({ page }) => {
    await routeWithFlag(page, 'dark-mode-beta', 'off');
    await page.goto('/settings');

    const body = page.locator('body');
    await expect(body).not.toHaveClass(/theme-dark/);
    await expect(page.getByTestId('theme-toggle')).toHaveText('Enable dark mode');
  });

  test('variant renders dark theme', async ({ page }) => {
    await routeWithFlag(page, 'dark-mode-beta', 'on');
    await page.goto('/settings');

    const body = page.locator('body');
    await expect(body).toHaveClass(/theme-dark/);
    await expect(page.getByTestId('theme-toggle')).toHaveText('Disable dark mode');
  });
});
```

---

## Strategy 3 — Verify analytics events fired per variant

Each variant must fire a different analytics event. Use `page.waitForEvent('request')` to assert the correct event is sent.

```typescript
// tests/feature-flags/analytics-events.spec.ts
import { test, expect } from '@playwright/test';

test.describe('pricing-page-v2 analytics', () => {
  async function captureAnalyticsEvents(
    page: import('@playwright/test').Page,
    variant: string
  ): Promise<string[]> {
    const events: string[] = [];

    await page.route('**/analytics/track', async (route) => {
      const body = await route.request().postDataJSON();
      if (body?.event) events.push(body.event);
      await route.fulfill({ status: 204, body: '' });
    });

    await page.route('**/*', (route) =>
      route.continue({
        headers: {
          ...route.request().headers(),
          'X-Feature-Flag-pricing-page-v2': variant,
        },
      })
    );

    await page.goto('/pricing');
    // Allow time for page-view events to flush
    await page.waitForTimeout(500);
    return events;
  }

  test('control fires legacy_pricing_viewed', async ({ page }) => {
    const events = await captureAnalyticsEvents(page, 'control');
    expect(events).toContain('legacy_pricing_viewed');
    expect(events).not.toContain('pricing_v2_viewed');
  });

  test('variant fires pricing_v2_viewed', async ({ page }) => {
    const events = await captureAnalyticsEvents(page, 'variant-b');
    expect(events).toContain('pricing_v2_viewed');
    expect(events).not.toContain('legacy_pricing_viewed');
  });
});
```

---

## Strategy 4 — Cookie-based flag injection

When the Worker uses a signed flag cookie, set it directly in the browser context before navigation.

```typescript
// tests/feature-flags/cookie-flag.spec.ts
import { test, expect } from '@playwright/test';

const FLAG_COOKIE_NAME = 'cf_flags';

async function setFlagCookie(
  context: import('@playwright/test').BrowserContext,
  flags: Record<string, string>
): Promise<void> {
  await context.addCookies([
    {
      name: FLAG_COOKIE_NAME,
      // In production this would be signed; in test environments the Worker
      // accepts an unsigned cookie when CF_FLAGS_SKIP_VERIFY=true is set.
      value: Buffer.from(JSON.stringify(flags)).toString('base64'),
      domain: 'localhost',
      path: '/',
      httpOnly: false,
    },
  ]);
}

test.describe('onboarding-v3 via cookie', () => {
  test('control shows original onboarding', async ({ page, context }) => {
    await setFlagCookie(context, { 'onboarding-v3': 'control' });
    await page.goto('/onboarding');

    await expect(page.getByTestId('onboarding-step-1')).toBeVisible();
    await expect(page.getByTestId('onboarding-v3-step-1')).not.toBeAttached();
  });

  test('variant shows new onboarding flow', async ({ page, context }) => {
    await setFlagCookie(context, { 'onboarding-v3': 'variant' });
    await page.goto('/onboarding');

    await expect(page.getByTestId('onboarding-v3-step-1')).toBeVisible();
    await expect(page.getByTestId('onboarding-step-1')).not.toBeAttached();
  });
});
```

---

## Strategy 5 — Parameterised test matrix across all variants

Run the same user journey for every defined variant using `test.describe.configure` and `test.each`-style parameterisation.

```typescript
// tests/feature-flags/variant-matrix.spec.ts
import { test, expect } from '@playwright/test';

const VARIANTS = [
  { name: 'control', expectCheckoutButton: 'Buy now', expectBadge: false },
  { name: 'variant-a', expectCheckoutButton: 'Add to cart', expectBadge: false },
  { name: 'variant-b', expectCheckoutButton: 'Add to cart', expectBadge: true },
] as const;

for (const variant of VARIANTS) {
  test(`product page renders correctly for ${variant.name}`, async ({ page }) => {
    await page.route('**/*', (route) =>
      route.continue({
        headers: {
          ...route.request().headers(),
          'X-Feature-Flag-product-page-v2': variant.name,
        },
      })
    );

    await page.goto('/products/widget-pro');

    await expect(page.getByRole('button', { name: variant.expectCheckoutButton })).toBeVisible();

    if (variant.expectBadge) {
      await expect(page.getByTestId('new-badge')).toBeVisible();
    } else {
      await expect(page.getByTestId('new-badge')).not.toBeAttached();
    }
  });
}
```

---

## Anti-patterns

- Depending on a live feature-flag service (LaunchDarkly, Statsig) in CI — the service may be unavailable, rate-limit test traffic, or charge for evaluation volume. Always intercept flag resolution in tests.
- Toggling flags via the flag service admin API from within a test — introduces network dependencies, requires API credentials in CI, and is slow compared to header/cookie injection.
- Asserting `expect(page.url()).toContain('variant=a')` to verify flag selection — the URL may not reflect the flag value; assert the rendered UI outcome instead.
- Running all variant tests in the same browser context without resetting cookies — flag cookies from one test bleed into the next test in the same context.
- Hardcoding the expected percentage split (50/50) in a test — deterministic flag forcing is the correct approach; statistical tests of cohort assignment belong in unit tests of the routing logic, not in Playwright.

---

## Gotchas

- `page.route` intercepts requests made by the browser, not requests made by the Worker itself during SSR. If the Worker fetches flag configuration server-side (e.g., via `fetch('https://flags-api.example.com')`), Playwright cannot intercept that. Inject the flag via header or cookie instead, so the Worker reads it from the incoming request.
- Cookies set with `context.addCookies` are origin-scoped. If the app navigates cross-origin during the test, the cookie may not be sent to the new origin.
- `page.route` callbacks run in the Node process, not in the browser. Avoid accessing browser APIs (e.g., `page.evaluate`) inside a route callback.
- Signed flag cookies require that the test environment skip signature verification. Add an environment variable (`CF_FLAGS_SKIP_VERIFY=1`) to the Worker when deployed to a test environment, and gate the skip on that variable — never in production.
- Playwright executes `page.route` handlers in registration order. Register the analytics intercept before the flag injection route to ensure both are active when the page loads.

---

## Verification

```bash
# Run all feature flag tests
npx playwright test tests/feature-flags/

# Run in headed mode to visually confirm each variant
npx playwright test tests/feature-flags/checkout-redesign.spec.ts --headed

# Generate an HTML report showing each variant
npx playwright test tests/feature-flags/ --reporter=html
npx playwright show-report
```

---

## Related

- `feature-flag-testing-strategy.md` — flag testing strategy and taxonomy
- `ab-test-engineering-validity.md` — statistical validity of A/B experiments
- `playwright-network-interception.md` — advanced route interception patterns
- `playwright-page-object-model.md` — encapsulating variant selectors in page objects
- `playwright-cloudflare-pages-e2e.md` — end-to-end testing Workers-backed pages

---

## Sources

- https://playwright.dev/docs/network#modify-requests
- https://playwright.dev/docs/api/class-browsercontext#browser-context-add-cookies
- https://developers.cloudflare.com/workers/runtime-apis/bindings/kv-namespaces/
- https://developers.cloudflare.com/workers/examples/ab-testing/
- https://playwright.dev/docs/api/class-page#page-route
