# synthetic-monitoring-deploy

**Issue:** Running synthetic checks continuously in production to detect outages before real users do
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Real-user monitoring (RUM) only fires when actual users are affected. Synthetic monitoring runs scripted transactions every minute from external locations and alerts before the first user hits an error — or during off-peak hours when real traffic is low.

## Pattern / Solution
**What to check synthetically**
- Homepage loads (CDN / static assets)
- Auth login flow (end-to-end, not just the endpoint)
- Primary value-add action (search, checkout, create)
- API health endpoint from multiple regions

**Checkly (recommended for JS/TS teams)**
```typescript
// checks/api-health.check.ts
import { ApiCheck, AssertionBuilder } from 'checkly/constructs';

new ApiCheck('api-health', {
  name: 'API Health',
  activated: true,
  muted: false,
  request: {
    url: 'https://api.example.com/healthz',
    method: 'GET',
    assertions: [
      AssertionBuilder.statusCode().equals(200),
      AssertionBuilder.responseTime().lessThan(500),
      AssertionBuilder.jsonBody('$.status').equals('ok'),
    ],
  },
  locations: ['us-east-1', 'eu-west-1', 'ap-southeast-1'],
  frequency: 1, // every minute
});
```

**Deploy-time synthetic check gate**
```yaml
# In CI: run synthetics against staging before promoting to prod
- name: Run Checkly synthetics on staging
  run: npx checkly test --env staging
  env:
    CHECKLY_API_KEY: ${{ secrets.CHECKLY_API_KEY }}
```

**Alert routing**
- Single-region failure → Slack #alerts (possible regional issue)
- Multi-region failure for 2 consecutive checks → PagerDuty P1

## Gotchas
- Synthetic checks from a single region can false-positive due to regional network issues; always require 2 regions to fail before paging
- Authenticated checks need dedicated synthetic users in the database — real user credentials rotate and break checks
- Check frequency vs. cost: 1-minute checks on 3 regions = 4,320 check runs/day — review pricing
- Suppress synthetic alerts during known maintenance windows or deploy freezes

## Related
- `deployment-verification-smoke-tests.md`
- `post-deploy-monitoring-checklist.md`
- `slo-alerting-thresholds.md`
