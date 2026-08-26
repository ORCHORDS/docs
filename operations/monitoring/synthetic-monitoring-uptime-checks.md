# Synthetic Monitoring and Uptime Checks

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your team discovers outages from customer reports, not from monitoring.
The application returns 200 OK on health checks but critical user
journeys (login, checkout, search) are broken. You have no visibility
into performance from different geographic regions. Third-party service
degradation (CDN, payment processor, auth provider) is invisible until
customers complain.

## Context

Synthetic monitoring simulates user interactions with your application
from external locations on a schedule — probing availability, latency,
and correctness before real users are affected. Unlike Real User
Monitoring (RUM) which observes actual traffic, synthetic monitoring runs
24/7 even when no users are active, providing baseline coverage and
proactive alerting. In 2026, synthetic monitoring is converging with
Playwright-based testing, allowing teams to reuse end-to-end test scripts
as production monitors. Monitoring-as-code approaches store check
definitions in Git alongside application code.

## Synthetic monitoring types

### 1. Uptime checks (HTTP)

Simple HTTP(S) requests that verify a URL returns the expected status
code and response body.

```yaml
# Basic uptime check
- name: API health
  url: https://api.example.com/health
  method: GET
  assertions:
    - statusCode: 200
    - responseTime: < 500ms
    - body: contains "ok"
  frequency: 30s
  locations: [us-east, eu-west, ap-southeast]
```

### 2. API checks (multi-step)

Chained API requests that verify business logic — authentication,
data retrieval, and state mutations.

```typescript
// Checkly API check
import { ApiCheck, AssertionBuilder } from 'checkly/constructs';

new ApiCheck('create-order-flow', {
  name: 'Create Order Flow',
  frequency: 5,
  locations: ['us-east-1', 'eu-west-1'],
  request: {
    method: 'POST',
    url: 'https://api.example.com/orders',
    headers: { Authorization: 'Bearer {{API_TOKEN}}' },
    body: JSON.stringify({ item: 'test-sku', quantity: 1 }),
    assertions: [
      AssertionBuilder.statusCode().equals(201),
      AssertionBuilder.jsonBody('$.orderId').isNotNull(),
    ],
  },
});
```

### 3. Browser checks (Playwright-based)

Full browser automation that simulates real user journeys — navigating
pages, clicking buttons, filling forms, and asserting on rendered content.

```typescript
// Checkly browser check using Playwright
import { test, expect } from '@playwright/test';

test('checkout flow', async ({ page }) => {
  await page.goto('https://shop.example.com');
  await page.click('[data-testid="product-card"]');
  await page.click('[data-testid="add-to-cart"]');
  await page.click('[data-testid="checkout"]');

  await page.fill('#email', 'test@example.com');
  await page.fill('#card-number', '4242424242424242');
  await page.click('[data-testid="pay"]');

  await expect(page.locator('.confirmation')).toContainText('Order confirmed');
});
```

### 4. DNS and certificate checks

Verify DNS resolution, SSL certificate validity, and certificate
expiration dates.

## Monitoring-as-code

### Checkly CLI

```typescript
// checkly.config.ts
import { defineConfig } from 'checkly';

export default defineConfig({
  projectName: 'Production Monitors',
  logicalId: 'prod-monitors',
  checks: {
    frequency: 5,
    locations: ['us-east-1', 'eu-west-1', 'ap-southeast-1'],
    tags: ['production'],
    runtimeId: '2024.02',
    browserChecks: {
      testMatch: '**/__checks__/**/*.spec.ts',
    },
  },
});
```

### Grafana Cloud Synthetic Monitoring

```yaml
# k6 script reused as synthetic monitor
import http from 'k6/http';
import { check } from 'k6';

export default function () {
  const res = http.get('https://api.example.com/health');
  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
  });
}
```

Grafana Cloud runs k6 scripts as synthetic monitors from global probes,
allowing teams to reuse load test scripts as availability monitors.

## Tool comparison

| Feature | Checkly | Grafana Cloud | Datadog Synthetic | Pingdom |
|---|---|---|---|---|
| Browser checks | Playwright | k6 browser | Puppeteer-based | No |
| API checks | Yes | k6 scripts | Yes | Limited |
| Monitoring-as-code | CLI + Terraform | Terraform | Terraform | No |
| Locations | 20+ | 25+ | 100+ | 100+ |
| Pricing model | Per check | Per probe | Per 10k tests | Per check |
| CI integration | GitHub Actions, CLI | CLI | CI/CD | Limited |
| Alert channels | Slack, PagerDuty, webhooks | Grafana OnCall | PagerDuty, Slack, etc. | Email, SMS, webhooks |

## Multi-location strategy

Run checks from at least 3 geographic regions to:
- Detect region-specific outages (CDN PoP failure, regional DNS issues).
- Measure latency from where your users actually are.
- Avoid false positives — require failure from 2+ locations before alerting.

```
Alert rule: page only when 2 of 3 locations fail consecutively
  Location 1 (us-east): FAIL  ─┐
  Location 2 (eu-west): FAIL  ─┼→ ALERT (2/3 failed)
  Location 3 (ap-south): PASS ─┘
```

## Anti-patterns

- **Health endpoint only** — monitoring `/health` which returns 200 as
  long as the server boots, while the database connection pool is
  exhausted and all real requests fail. Monitor real user journeys, not
  just health endpoints.
- **Single location** — running all checks from one region produces
  false positives during regional network issues and misses region-
  specific outages.
- **No assertion on body** — checking only status code. A 200 response
  with an error message in the body is still a broken page. Assert on
  response content.
- **Too-frequent browser checks** — running Playwright checks every 30
  seconds is expensive and creates unnecessary load. 1-5 minute intervals
  are sufficient for most browser checks.

## Gotchas

- **Test data management** — browser checks that create real orders,
  users, or records pollute production databases. Use dedicated test
  accounts and clean up after each run, or use a test/staging environment.
- **Authentication tokens** — checks that require authentication must
  handle token expiration and refresh. Store credentials as encrypted
  environment variables, never in check scripts.
- **Third-party rate limits** — synthetic checks hitting third-party
  APIs (payment processors, auth providers) may trigger rate limiting.
  Use sandbox/test endpoints where available.
- **Alert fatigue from synthetic checks** — transient network issues
  between monitoring locations and your servers cause false positives.
  Require consecutive failures from multiple locations before alerting.

## Verification

- Critical user journeys (login, checkout, core features) have browser
  checks.
- API endpoints have multi-step checks verifying business logic.
- Checks run from at least 3 geographic regions.
- Alert rules require failure from 2+ locations to avoid false positives.
- Check definitions are stored in Git (monitoring-as-code).
- Synthetic check results are visible in the team's observability dashboard.

## Related

- `documentation/categories/monitoring/frontend-real-user-monitoring-rum.md`
- `documentation/categories/testing/event-driven-async-api-testing.md`
- `documentation/categories/lessons/on-call-rotation-best-practices.md`

## Source URLs (verified 2026-08-16)

- Checkly documentation — https://www.checklyhq.com/docs/
- Grafana Cloud Synthetic Monitoring — https://grafana.com/docs/grafana-cloud/testing/synthetic-monitoring/
- Datadog Synthetic Monitoring — https://docs.datadoghq.com/synthetics/
- Synthetic vs RUM comparison — https://www.catchpoint.com/blog/rum-vs-synthetic-monitoring
