# feature-cookbook-deploy

**Issue:** Deploy recipes — preview, canary, blue-green, rollback
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a feature. It works in staging. You push to
production. Users see errors. You roll back. The rollback
fails. You're stuck with a broken production. You wish
you'd had a canary deploy.

## Root cause
**Deploys are risky.** A safe deploy pattern is essential.

**Source:** Various deploy guides.

## The "preview environment" pattern

For every PR, a unique environment:
```yaml
# .github/workflows/preview.yml
on: [pull_request]
jobs:
  deploy-preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npm run build
      - run: wrangler pages deploy dist --project-name my-app-preview
      - run: |
        PR_NUMBER=$(echo $GITHUB_REF | cut -d/ -f3)
        echo "Preview URL: https://pr-${PR_NUMBER}.my-app-preview.pages.dev"
```

Every PR has a URL; reviewers can test.

## The "canary" pattern

For canary, deploy to a small subset first:
```ts
// 1. Deploy to canary
await wrangler deploy --env canary;

// 2. Monitor metrics for 1 hour
// (p99 latency, error rate)

// 3. If good, deploy to production
if (metricsAreGood) {
  await wrangler deploy --env production;
}
```

The canary catches issues before production.

## The "blue-green" pattern

For blue-green, two environments:
```yaml
# blue: current production
# green: new version

steps:
  - name: Deploy to green
    run: wrangler deploy --env green

  - name: Run smoke tests on green
    run: ./smoke-test.sh https://green.example.com

  - name: Switch traffic to green
    run: cf-cli route update --hostname api.example.com --destination green

  - name: Monitor
    run: ./monitor.sh --duration 1h
```

Switch is instant; rollback is instant.

## The "feature flag" deploy

For feature flag deploy, the code is shipped but the
feature is off:
```ts
// 1. Deploy
wrangler deploy --env production

// 2. Enable the flag for 1%
await enableFeature('new-dashboard', { percentage: 1 });

// 3. Monitor
// (errors, latency)

// 4. Roll out gradually
await enableFeature('new-dashboard', { percentage: 10 });
await enableFeature('new-dashboard', { percentage: 50 });
await enableFeature('new-dashboard', { percentage: 100 });
```

The flag controls the rollout; no redeploy needed.

## The "rollback" pattern

For instant rollback, use the previous version:
```bash
# Save the current version
wrangler versions list
# Find the previous version ID
PREV_ID="abc-123"

# Roll back
wrangler rollback --version-id $PREV_ID
```

CF Workers has a built-in rollback (via versions).

## The "rollback decision" pattern

Roll back when:
- **Error rate > 2x baseline** for > 5 min
- **Latency p99 > 2x baseline** for > 5 min
- **Critical functionality is broken**
- **Data corruption is detected**
- **Security vulnerability is discovered**

Default: roll back. Better safe than sorry.

## The "smoke test" pattern

After deploy, run a smoke test:
```ts
const smokeTests = [
  { name: 'Homepage loads', url: '/', expectStatus: 200 },
  { name: 'Login works', url: '/api/login', method: 'POST', body: { email: 'smoke@test.com', password: '...' }, expectStatus: 200 },
  { name: 'API health', url: '/api/health', expectStatus: 200 },
  { name: 'CDN serves static', url: '/static/main.js', expectStatus: 200 },
];

for (const test of smokeTests) {
  const res = await fetch(`https://staging.example.com${test.url}`, { method: test.method, body: JSON.stringify(test.body) });
  expect(res.status).toBe(test.expectStatus);
}
```

A 5-min smoke test catches 80% of deploy issues.

## The "deploy timing" pattern

For risky deploys, deploy off-peak:
- **Best:** Weekday morning (team is online; issues are
  caught quickly)
- **OK:** Weekday afternoon
- **Avoid:** Weeknight (team is offline)
- **Avoid:** Weekend (team is offline)
- **Avoid:** Friday (no time to fix)

## The "deploy notification" pattern

For every deploy, notify the team:
```yaml
- name: Notify Slack
  if: always()
  uses: slackapi/slack-github-action@v1
  with:
    payload: |
      {
        "text": "Deploy to ${{ github.event.inputs.environment }}: ${{ job.status }}"
      }
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```

The team knows when a deploy happens.

## The "deploy log" pattern

For every deploy, log to a record:
```ts
await env.DB!.prepare(`
  INSERT INTO deploys (id, environment, version, deployed_by, started_at, completed_at, status)
  VALUES (?, ?, ?, ?, ?, ?, ?)
`).bind(
  crypto.randomUUID(),
  'production',
  'v1.2.3',
  ctx.user.email,
  startedAt.toISOString(),
  completedAt.toISOString(),
  'success',
).run();
```

The deploy history is queryable.

## The "deploy verification" pattern

For verification, assert the deploy is correct:
```ts
// After deploy, check that the new version is active
const response = await fetch('https://example.com/api/version');
const { version } = await response.json();
expect(version).toBe('v1.2.3');
```

The verification catches a "deploy didn't take" issue.

## The "traffic shift" pattern

For traffic shift, use CF's load balancer:
```yaml
# Cloudflare Load Balancer
default_pool: blue
pop_pools:
  LAX: blue
  JFK: green  # 10% on green
  FRA: blue
```

The traffic is shifted gradually.

## The "deploy automation" pattern

For automation, use a CI/CD pipeline:
```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm test
      - run: npm run build
      - run: wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

The CI runs all checks before deploy.

## The "deploy approval" pattern

For prod deploys, require approval:
```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://example.com
    steps:
      # ...
```

The GitHub Environment has a required reviewer.

## The "deploy audit" pattern

For audit, log every deploy:
```ts
await writeAudit(env, {
  userId: ctx.user.id,
  action: 'deploy.completed',
  resourceType: 'deployment',
  resourceId: deployId,
  metadata: { version, environment, duration },
});
```

The audit log shows the deploy history.

## Verification
- **Test:** Deploy works
- **Test:** Rollback works
- **Live:** Smoke test passes
- **Live:** Canary is healthy
- **Audit:** Monthly review of deploys

## Gotchas
- **The "deploy without tests" anti-pattern.** Always run
  tests before deploy.
- **The "deploy without rollback plan" anti-pattern.**
  Always have a way to roll back.
- **The "deploy to production first" anti-pattern.** Always
  deploy to staging first.
- **The "deploy on Friday" anti-pattern.** Avoid if
  possible; have a rollback plan.
- **The "deploy without monitoring" anti-pattern.** Always
  monitor after deploy.

## Related
- `safe-deploy-checklist.md`
- `zero-downtime-deploys.md`
- `feature-rollout-strategies.md`
- `feature-flags.md`
- `preview-environments.md`
- `feature-environment-promotion.md`
- `incident-response.md`
