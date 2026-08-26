# End-to-End Testing Multi-Step Payment Flows with Playwright and Stripe Test Cards

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your application processes payments through Stripe. Manual QA for the checkout flow is slow, error-prone, and cannot cover every card scenario (declined cards, 3D Secure, expired cards, insufficient funds). You need automated E2E tests that:

- Exercise the full user journey: cart → checkout → payment → confirmation.
- Cover happy paths and failure modes (declined, SCA/3DS challenge, network error).
- Run in CI without hitting Stripe's live API or charging real cards.
- Avoid flakiness caused by Stripe's 3DS challenge iframes loading asynchronously.

---

## Context

Stripe provides a dedicated test mode with:

- **Test API keys** (`sk_test_...`, `pk_test_...`) — all API calls go to Stripe's test environment.
- **Test card numbers** — `4242424242424242` (success), `4000000000000002` (decline), `4000002500003155` (3DS required), etc.
- **Stripe CLI** — webhook forwarding to `localhost` for testing post-payment webhooks without ngrok.

The challenge with Playwright is that Stripe's Payment Element loads in a cross-origin iframe, so direct `page.fill()` on iframe inputs requires entering the iframe's frame context first.

Stack: **Next.js 15 (App Router), Stripe Elements, Playwright 1.48, Stripe CLI 1.21**.

---

## 1. Environment Configuration

### `.env.test`

```bash
# Stripe test keys — safe to use in CI; never use live keys
STRIPE_SECRET_KEY=sk_test_51...
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_51...
STRIPE_WEBHOOK_SECRET=whsec_test_...  # From `stripe listen` output
```

### `playwright.config.ts`

```typescript
import { defineConfig, devices } from "@playwright/test";
import dotenv from "dotenv";

dotenv.config({ path: ".env.test" });

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000, // Stripe 3DS flows can take >10 seconds
  expect: { timeout: 10_000 },
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    video: "on-first-retry",
  },
  webServer: {
    command: "npm run dev",
    port: 3000,
    reuseExistingServer: !process.env.CI,
    env: {
      STRIPE_SECRET_KEY: process.env.STRIPE_SECRET_KEY!,
      NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY:
        process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY!,
    },
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
```

---

## 2. Test Card Constants

```typescript
// e2e/fixtures/stripe-cards.ts
export const STRIPE_TEST_CARDS = {
  /** Succeeds immediately, no 3DS */
  VISA_SUCCESS: {
    number: "4242 4242 4242 4242",
    expiry: "12/28",
    cvc: "123",
    zip: "10001",
  },
  /** Always declined */
  VISA_DECLINED: {
    number: "4000 0000 0000 0002",
    expiry: "12/28",
    cvc: "123",
    zip: "10001",
  },
  /** Requires 3DS authentication */
  VISA_3DS_REQUIRED: {
    number: "4000 0025 0000 3155",
    expiry: "12/28",
    cvc: "123",
    zip: "10001",
  },
  /** 3DS required but authentication fails */
  VISA_3DS_FAIL: {
    number: "4000 0084 0000 1629",
    expiry: "12/28",
    cvc: "123",
    zip: "10001",
  },
  /** Insufficient funds */
  VISA_INSUFFICIENT_FUNDS: {
    number: "4000 0000 0000 9995",
    expiry: "12/28",
    cvc: "123",
    zip: "10001",
  },
} as const;

export type StripeTestCard =
  (typeof STRIPE_TEST_CARDS)[keyof typeof STRIPE_TEST_CARDS];
```

---

## 3. Payment Page Object Model

```typescript
// e2e/pages/checkout.page.ts
import { type Page, type FrameLocator, expect } from "@playwright/test";
import type { StripeTestCard } from "../fixtures/stripe-cards";

export class CheckoutPage {
  private readonly page: Page;
  // Stripe Elements loads inside an iframe
  private stripeFrame: FrameLocator;

  constructor(page: Page) {
    this.page = page;
    // The iframe's name attribute matches Stripe's internal iframe name pattern
    this.stripeFrame = page.frameLocator(
      'iframe[name^="__privateStripeFrame"]'
    );
  }

  async goto() {
    await this.page.goto("/checkout");
    // Wait for Stripe Elements to be ready
    await this.page.waitForSelector('[data-testid="payment-element"]');
  }

  async fillCard(card: StripeTestCard) {
    // Enter the Stripe iframe context for card number
    const cardNumberFrame = this.stripeFrame.locator(
      '[data-elements-stable-field-name="cardNumber"]'
    );
    await cardNumberFrame.click();
    await cardNumberFrame.fill(card.number);

    const expiryFrame = this.stripeFrame.locator(
      '[data-elements-stable-field-name="cardExpiry"]'
    );
    await expiryFrame.click();
    await expiryFrame.fill(card.expiry);

    const cvcFrame = this.stripeFrame.locator(
      '[data-elements-stable-field-name="cardCvc"]'
    );
    await cvcFrame.click();
    await cvcFrame.fill(card.cvc);
  }

  async fillBilling(opts: {
    name: string;
    email: string;
    address: string;
    city: string;
    state: string;
    zip: string;
  }) {
    await this.page.fill('[name="billingName"]', opts.name);
    await this.page.fill('[name="email"]', opts.email);
    await this.page.fill('[name="address"]', opts.address);
    await this.page.fill('[name="city"]', opts.city);
    await this.page.selectOption('[name="state"]', opts.state);
    await this.page.fill('[name="zip"]', opts.zip);
  }

  async submitPayment() {
    await this.page.click('[data-testid="submit-payment"]');
  }

  async waitForSuccess() {
    await expect(this.page).toHaveURL(/\/order-confirmation/, {
      timeout: 30_000,
    });
    await expect(
      this.page.locator('[data-testid="order-success-message"]')
    ).toBeVisible();
  }

  async waitForDeclined() {
    await expect(
      this.page.locator('[data-testid="payment-error"]')
    ).toContainText(/declined/i, { timeout: 15_000 });
  }

  async handle3DSChallenge(action: "authorize" | "fail") {
    // Stripe's 3DS challenge appears in a popup or nested iframe
    // The test environment's challenge page has simple buttons
    const challengeFrame = this.page.frameLocator(
      'iframe[name="stripe-challenge-frame"]'
    );

    if (action === "authorize") {
      await challengeFrame
        .locator("#test-source-authorize-3ds")
        .click({ timeout: 20_000 });
    } else {
      await challengeFrame
        .locator("#test-source-fail-3ds")
        .click({ timeout: 20_000 });
    }
  }
}
```

---

## 4. Happy Path Test

```typescript
// e2e/checkout.spec.ts
import { test, expect } from "@playwright/test";
import { CheckoutPage } from "./pages/checkout.page";
import { STRIPE_TEST_CARDS } from "./fixtures/stripe-cards";

const defaultBilling = {
  name: "Test User",
  email: "test@example.com",
  address: "123 Main St",
  city: "New York",
  state: "NY",
  zip: "10001",
};

test.describe("Checkout — happy path", () => {
  test("completes payment with a valid Visa card", async ({ page }) => {
    const checkout = new CheckoutPage(page);

    // Step 1: Navigate and fill cart (assumes items already in cart)
    await page.goto("/cart");
    await page.click('[data-testid="proceed-to-checkout"]');

    // Step 2: Fill billing info
    await checkout.fillBilling(defaultBilling);

    // Step 3: Fill card details inside Stripe iframe
    await checkout.fillCard(STRIPE_TEST_CARDS.VISA_SUCCESS);

    // Step 4: Submit
    await checkout.submitPayment();

    // Step 5: Assert success
    await checkout.waitForSuccess();

    // Assert order ID appears in URL or page
    await expect(page).toHaveURL(/order-confirmation\?order_id=/);
    await expect(
      page.locator('[data-testid="order-id"]')
    ).not.toBeEmpty();
  });
});
```

---

## 5. Failure Scenario Tests

```typescript
// e2e/checkout-failures.spec.ts
import { test, expect } from "@playwright/test";
import { CheckoutPage } from "./pages/checkout.page";
import { STRIPE_TEST_CARDS } from "./fixtures/stripe-cards";

test.describe("Checkout — card failure scenarios", () => {
  test("shows error message when card is declined", async ({ page }) => {
    const checkout = new CheckoutPage(page);
    await page.goto("/checkout");
    await checkout.fillCard(STRIPE_TEST_CARDS.VISA_DECLINED);
    await checkout.submitPayment();
    await checkout.waitForDeclined();

    // User should still be on checkout page (not redirected)
    await expect(page).toHaveURL("/checkout");

    // Error is dismissible
    await page.click('[data-testid="dismiss-error"]');
    await expect(
      page.locator('[data-testid="payment-error"]')
    ).not.toBeVisible();
  });

  test("shows insufficient funds error", async ({ page }) => {
    const checkout = new CheckoutPage(page);
    await page.goto("/checkout");
    await checkout.fillCard(STRIPE_TEST_CARDS.VISA_INSUFFICIENT_FUNDS);
    await checkout.submitPayment();

    await expect(
      page.locator('[data-testid="payment-error"]')
    ).toContainText(/insufficient/i, { timeout: 15_000 });
  });
});
```

---

## 6. 3DS Authentication Flow Tests

```typescript
// e2e/checkout-3ds.spec.ts
import { test, expect } from "@playwright/test";
import { CheckoutPage } from "./pages/checkout.page";
import { STRIPE_TEST_CARDS } from "./fixtures/stripe-cards";

test.describe("Checkout — 3DS authentication", () => {
  test("completes payment when 3DS is authorized", async ({ page }) => {
    const checkout = new CheckoutPage(page);
    await page.goto("/checkout");
    await checkout.fillCard(STRIPE_TEST_CARDS.VISA_3DS_REQUIRED);
    await checkout.submitPayment();

    // 3DS challenge iframe appears
    await checkout.handle3DSChallenge("authorize");

    // Payment should now complete
    await checkout.waitForSuccess();
  });

  test("shows error when 3DS authentication fails", async ({ page }) => {
    const checkout = new CheckoutPage(page);
    await page.goto("/checkout");
    await checkout.fillCard(STRIPE_TEST_CARDS.VISA_3DS_REQUIRED);
    await checkout.submitPayment();

    await checkout.handle3DSChallenge("fail");

    await expect(
      page.locator('[data-testid="payment-error"]')
    ).toContainText(/authentication/i, { timeout: 20_000 });
    await expect(page).toHaveURL("/checkout");
  });
});
```

---

## 7. Webhook Verification Test

```typescript
// e2e/webhook.spec.ts — requires Stripe CLI running: stripe listen --forward-to localhost:3000/api/webhooks/stripe
import { test, expect } from "@playwright/test";
import { CheckoutPage } from "./pages/checkout.page";
import { STRIPE_TEST_CARDS } from "./fixtures/stripe-cards";

test("webhook updates order status to paid after payment", async ({ page }) => {
  const checkout = new CheckoutPage(page);
  await page.goto("/checkout");
  await checkout.fillCard(STRIPE_TEST_CARDS.VISA_SUCCESS);
  await checkout.submitPayment();
  await checkout.waitForSuccess();

  // Extract order ID from URL
  const url = new URL(page.url());
  const orderId = url.searchParams.get("order_id");
  expect(orderId).toBeTruthy();

  // Poll the order status API (webhook may arrive within 2–5 seconds)
  await expect(async () => {
    const response = await page.request.get(`/api/orders/${orderId}/status`);
    const data = await response.json();
    expect(data.status).toBe("paid");
  }).toPass({ timeout: 15_000, intervals: [1_000, 2_000, 3_000] });
});
```

---

## Anti-patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| Using `page.fill()` directly on card inputs | Stripe inputs live in cross-origin iframes; Playwright cannot reach them this way | Use `page.frameLocator()` to enter iframe context first |
| Hardcoding `sleep(3000)` after submit | Stripe processing time varies; causes flakiness | Use `expect(page).toHaveURL(...)` with generous timeout |
| Testing against live Stripe API | Charges real money; requires live keys in CI | Use `sk_test_...` / `pk_test_...` keys exclusively |
| Locating iframe by index (`iframe:nth-of-type(2)`) | Stripe may render multiple iframes; index is fragile | Use `iframe[name^="__privateStripeFrame"]` name prefix |
| Asserting webhook delivery synchronously | Webhooks arrive asynchronously after payment confirmation | Poll with `toPass()` or a dedicated `waitForWebhook` helper |
| Sharing Stripe customer/payment intent state across tests | Stripe payment intents are single-use; sharing causes "already confirmed" errors | Create a fresh payment intent in each test or `beforeEach` |

---

## Gotchas

- **3DS iframe timing** — the `stripe-challenge-frame` may not appear instantly after `submitPayment`; use `{ timeout: 20_000 }` on locator actions inside the challenge frame.
- **`frameLocator` vs `frame`** — `frameLocator` returns a locator that re-evaluates on each action (resilient to iframe reloads during 3DS); prefer it over `page.frame({ name: ... })`.
- **Stripe Element mount timing** — Stripe Payment Element loads asynchronously; always `waitForSelector('[data-testid="payment-element"]')` before interacting.
- **`data-elements-stable-field-name`** — this attribute is Stripe's internal testing hook; it is available in both test and production Stripe.js builds and is stable across minor versions.
- **CI Stripe CLI** — to forward webhooks in CI, run `stripe listen --forward-to localhost:3000/api/webhooks/stripe &` before tests and parse its output for the signing secret.
- **Card number spaces** — Stripe test card numbers in their docs use spaces (`4242 4242 4242 4242`); you can pass them with spaces to `fill()` and Stripe's input mask handles formatting.
- **Concurrent tests and rate limits** — Stripe's test mode has generous rate limits but running >50 concurrent payment tests can trigger 429s; shard test files, not individual tests.

---

## Verification

```bash
# Start Stripe CLI webhook forwarding (one-time setup per dev session)
stripe listen --forward-to localhost:3000/api/webhooks/stripe &

# Run all payment E2E tests
npx playwright test e2e/checkout*.spec.ts e2e/webhook.spec.ts

# Run with UI to debug iframe interactions
npx playwright test e2e/checkout-3ds.spec.ts --ui

# Run on CI (headed mode off, workers=1 to avoid rate limits)
npx playwright test --workers=2 --reporter=github
```

Expected CI output:

```
Running 7 tests using 2 workers
✓ completes payment with a valid Visa card (18.2s)
✓ shows error message when card is declined (7.4s)
✓ shows insufficient funds error (6.9s)
✓ completes payment when 3DS is authorized (22.1s)
✓ shows error when 3DS authentication fails (19.8s)
✓ webhook updates order status to paid after payment (24.3s)
7 passed (55.7s)
```

---

## Related

- [`playwright-e2e-testing-architecture-practices.md`](playwright-e2e-testing-architecture-practices.md) — overall Playwright architecture
- [`playwright-page-object-model.md`](playwright-page-object-model.md) — POM pattern
- [`playwright-network-interception.md`](playwright-network-interception.md) — intercepting API calls
- [`playwright-fixtures.md`](playwright-fixtures.md) — test fixture patterns
- [`auth-flow-testing-strategy.md`](auth-flow-testing-strategy.md) — auth flow testing strategies

---

## Sources

- [Stripe Docs — Test Cards](https://stripe.com/docs/testing)
- [Stripe Docs — 3D Secure Testing](https://stripe.com/docs/payments/3d-secure/authentication-flow#testing)
- [Playwright Docs — Frames](https://playwright.dev/docs/frames)
- [Playwright Docs — `toPass`](https://playwright.dev/docs/api/class-locatorassertions#locator-assertions-to-pass)
- [Stripe CLI — Webhook Forwarding](https://stripe.com/docs/stripe-cli/webhooks)
