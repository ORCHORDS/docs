# deployment-verification-smoke-tests

**Issue:** Automated smoke tests to run immediately after a production deploy to confirm basic functionality
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A deploy succeeds at the infrastructure level (pods healthy, task running) but the application is broken in ways health checks cannot detect — wrong env var, missing secret, bad config. Smoke tests catch these within seconds.

## Pattern / Solution
**What smoke tests must cover**
1. Auth critical path — login returns 200 and a valid token
2. Data read — primary entity list/get returns non-empty 200
3. Data write — create a test record, assert it persists, delete it
4. External dependency liveness — downstream API reachable (not just DNS)
5. Feature-flagged surface if a flag just changed

**Playwright smoke suite (runs in CI post-deploy)**
```typescript
// smoke/post-deploy.spec.ts
import { test, expect } from '@playwright/test';

test('health endpoint', async ({ request }) => {
  const r = await request.get('/healthz');
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body.status).toBe('ok');
});

test('auth flow returns token', async ({ request }) => {
  const r = await request.post('/api/auth/login', {
    data: { email: process.env.SMOKE_EMAIL, password: process.env.SMOKE_PASSWORD },
  });
  expect(r.status()).toBe(200);
  const { token } = await r.json();
  expect(token).toBeTruthy();
});

test('primary read path', async ({ request }) => {
  const r = await request.get('/api/v1/items?limit=1', {
    headers: { Authorization: `Bearer ${process.env.SMOKE_TOKEN}` },
  });
  expect(r.status()).toBe(200);
});
```

**GitHub Actions post-deploy step**
```yaml
- name: Run smoke tests
  run: npx playwright test smoke/
  env:
    BASE_URL: https://api.production.example.com
    SMOKE_EMAIL: ${{ secrets.SMOKE_EMAIL }}
    SMOKE_PASSWORD: ${{ secrets.SMOKE_PASSWORD }}
```

## Gotchas
- Smoke test credentials must be a dedicated service account — never a real user
- Tests must be idempotent; write tests must clean up their own data
- Run smoke tests against the actual production URL, not a staging clone
- Timeout each test at 10 s max — if prod is that slow, it is already an incident
- Gate the "deployment successful" Slack notification on smoke test pass, not just pod readiness

## Related
- `zero-downtime-deployment-checklist.md`
- `post-deploy-monitoring-checklist.md`
- `synthetic-monitoring-deploy.md`
