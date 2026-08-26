# Synthetic Monitoring — Uptime Probes, Transaction Checks, and Multi-Step Flows

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your monitoring only detects issues after users report them. You have
Prometheus metrics and error tracking, but they measure what happens
when requests arrive — not whether users can reach your service at all.
DNS resolution fails for 10 minutes but your internal health checks
pass because they bypass the public DNS. A third-party payment API goes
down but you do not know until customers complain about failed
checkouts. You need to detect outages from the user's perspective,
before users notice.

## Context

Synthetic monitoring (also called active monitoring or proactive
monitoring) simulates user interactions from external locations to
detect availability, performance, and correctness issues before real
users are affected. Unlike Real User Monitoring (RUM) which measures
actual user sessions, synthetic monitors run on a schedule from
predefined locations, providing baseline performance data and alerting
on degradation even when no real traffic is flowing (nights, weekends,
low-traffic periods). In 2026, synthetic monitoring is a standard
component of the observability stack, with tools like Checkly, Datadog
Synthetic Monitoring, Grafana Synthetic Monitoring, and Playwright-based
checks enabling code-defined multi-step transaction monitoring.

## Monitoring types

```
HTTP/API checks:
  → Simple HTTP request to an endpoint
  → Verify status code, response time, body content
  → Run every 30s-5min from multiple locations
  → Cheapest and most common

Multi-step API checks:
  → Chain of HTTP requests (login → create → verify → delete)
  → Validate complete API workflows
  → Run every 5-15min

Browser checks:
  → Full browser session (Playwright, Puppeteer)
  → Simulate user interactions (click, type, navigate)
  → Verify visual elements, JavaScript execution
  → Run every 5-30min from multiple locations

DNS checks:
  → Verify DNS resolution time and correctness
  → Detect DNS propagation issues
  → Alert on unexpected record changes

SSL/TLS checks:
  → Certificate expiration monitoring
  → Chain validation
  → Alert 30 days before expiry

TCP/UDP checks:
  → Port connectivity verification
  → Database, cache, queue reachability
  → Lower-level than HTTP
```

## Checkly (Monitoring as Code)

### HTTP check

```javascript
// __checks__/api-health.check.ts
import { ApiCheck, AssertionBuilder } from 'checkly/constructs';

new ApiCheck('api-health', {
  name: 'API Health Check',
  activated: true,
  frequency: 1, // Every 1 minute
  locations: ['us-east-1', 'eu-west-1', 'ap-southeast-1'],
  request: {
    method: 'GET',
    url: 'https://api.example.com/health',
    assertions: [
      AssertionBuilder.statusCode().equals(200),
      AssertionBuilder.responseTime().lessThan(500),
      AssertionBuilder.jsonBody('$.status').equals('healthy'),
    ],
  },
  alertChannels: [slackChannel, pagerdutyChannel],
});
```

### Browser check (Playwright)

```javascript
// __checks__/login-flow.spec.ts
import { test, expect } from '@playwright/test';

test('user can log in and view dashboard', async ({ page }) => {
  // Navigate to login page
  await page.goto('https://app.example.com/login');
  await expect(page).toHaveTitle(/Login/);

  // Fill in credentials
  await page.fill('[data-testid="email"]', 'synthetic@example.com');
  await page.fill('[data-testid="password"]', process.env.SYNTH_PASSWORD);
  await page.click('[data-testid="login-button"]');

  // Verify dashboard loads
  await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({
    timeout: 10000,
  });

  // Verify key data loads
  await expect(page.locator('[data-testid="revenue-widget"]')).toBeVisible();

  // Check for JavaScript errors
  const errors = [];
  page.on('pageerror', (err) => errors.push(err.message));
  expect(errors).toHaveLength(0);
});
```

### Multi-step API check

```javascript
// __checks__/checkout-flow.check.ts
import { MultiStepCheck } from 'checkly/constructs';

new MultiStepCheck('checkout-flow', {
  name: 'E-Commerce Checkout Flow',
  frequency: 10,
  locations: ['us-east-1', 'eu-west-1'],
  code: {
    content: `
      const { test, expect } = require('@playwright/test');

      test('complete checkout flow', async ({ request }) => {
        // Step 1: Add item to cart
        const cart = await request.post('https://api.example.com/cart', {
          data: { productId: 'test-product', quantity: 1 },
          headers: { Authorization: 'Bearer ' + process.env.API_TOKEN },
        });
        expect(cart.status()).toBe(201);
        const { cartId } = await cart.json();

        // Step 2: Create checkout
        const checkout = await request.post('https://api.example.com/checkout', {
          data: { cartId, paymentMethod: 'test-card' },
          headers: { Authorization: 'Bearer ' + process.env.API_TOKEN },
        });
        expect(checkout.status()).toBe(200);
        const { orderId } = await checkout.json();

        // Step 3: Verify order
        const order = await request.get(
          'https://api.example.com/orders/' + orderId,
          { headers: { Authorization: 'Bearer ' + process.env.API_TOKEN } }
        );
        expect(order.status()).toBe(200);
        const orderData = await order.json();
        expect(orderData.status).toBe('confirmed');
      });
    `,
  },
});
```

## Location strategy

```
Minimum locations:
  → 3 geographically distributed locations
  → At least 1 per region where users are concentrated
  → Alert only when 2+ locations fail (avoid false positives)

Common setup:
  US East (Virginia) — primary US
  EU West (Ireland/Frankfurt) — primary EU
  APAC (Singapore/Tokyo) — primary Asia
  US West (Oregon) — secondary US
  Additional: South America, Australia, Middle East

False positive reduction:
  → Require 2 consecutive failures before alerting
  → Or require failures from 2+ locations
  → Double-check: re-run immediately on failure before alerting
```

## Third-party monitoring

```
Monitor external dependencies from your users' perspective:

Payment APIs:
  → Check Stripe/Adyen status endpoint every 2 min
  → Verify payment intent creation works
  → Alert if response time > 2s or errors

CDN:
  → Fetch a static asset from CDN edge
  → Verify content hash matches expected
  → Measure TTFB from each region

Auth providers:
  → Test OAuth flow with a synthetic account
  → Verify token refresh works
  → Alert if login latency exceeds threshold

Email delivery:
  → Send test email, verify receipt via IMAP
  → Measure delivery latency
  → Alert if email not received within 5 min
```

## Anti-patterns

- **Internal-only health checks** — running health checks from
  within the same network as your services. These bypass DNS,
  load balancers, CDN, and WAF — the exact layers where many
  outages occur. Always run synthetic checks from external locations.
- **Checking only the homepage** — monitoring `/` returns 200 but
  the checkout flow is broken. Synthetic monitors should cover
  critical user journeys: login, search, checkout, API endpoints.
- **Hardcoded test data** — using production user accounts or
  real payment methods in synthetic checks. Create dedicated
  synthetic/test accounts and use test-mode APIs. Ensure synthetic
  traffic is excluded from analytics.
- **Too many locations, too frequently** — running browser checks
  every 30 seconds from 20 locations creates 40 browser sessions
  per minute. This is expensive and generates noise. Match frequency
  and location count to the criticality of the check.

## Gotchas

- **Synthetic traffic in analytics** — synthetic monitors generate
  HTTP requests and browser sessions that appear in analytics tools.
  Filter synthetic traffic by User-Agent header, IP allowlist, or
  a custom header. Exclude from conversion metrics and A/B tests.
- **Credential rotation** — synthetic monitors that log in need
  credentials. Rotate synthetic account passwords on the same
  schedule as real service accounts. Store in a secrets manager,
  not in the check configuration.
- **Rate limiting** — frequent synthetic checks from the same IPs
  may trigger your own rate limiting or WAF rules. Allowlist
  synthetic monitoring IPs or use a bypass header.
- **State pollution** — multi-step checks that create orders, send
  messages, or modify data in production. Use a dedicated test
  environment or clean up created resources at the end of each check
  run.

## Verification

- Critical user journeys have synthetic browser checks.
- API endpoints are monitored from 3+ geographic locations.
- Third-party dependencies are monitored independently.
- Alerts require 2+ location failures to reduce false positives.
- Synthetic traffic is excluded from analytics and A/B tests.
- SSL certificate expiry is monitored with 30-day warning.
- Check results feed into SLO calculations.

## Related

- `documentation/categories/monitoring/alerting-strategy-routing-escalation.md`
- `documentation/categories/monitoring/structured-logging-json-correlation.md`
- `documentation/categories/testing/chaos-engineering-fault-injection.md`

## Source URLs (verified 2026-08-16)

- Synthetic Monitoring Best Practices 2026 — https://www.checklyhq.com/guides/synthetic-monitoring/
- Synthetic Monitoring: Complete Guide for Engineering Teams — https://grafana.com/docs/grafana-cloud/testing/synthetic-monitoring/
- Synthetic vs Real User Monitoring 2026 — https://www.datadoghq.com/knowledge-center/synthetic-monitoring/
- Monitoring as Code with Checkly — https://www.checklyhq.com/docs/monitoring-as-code/
