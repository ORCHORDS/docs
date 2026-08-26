# Synthetic Monitoring with Playwright for Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You have deployed Workers-backed APIs or full-stack apps and want to verify they behave correctly from a real browser or HTTP client on a schedule, from multiple regions, without relying solely on unit tests or passive error monitoring. You need screenshot evidence on failure stored durably.

## Context

Synthetic monitoring executes scripted interactions against production (or staging) endpoints at regular intervals. Playwright runs headful/headless Chromium, Firefox, or WebKit and can assert on response bodies, DOM state, network requests, and performance timing. Because Workers run at the edge you want synthetic checks from multiple PoPs to detect regional degradation.

GitHub Actions provides free cron scheduling and matrix builds per region. Analytics Engine receives structured test results for trend queries. R2 receives screenshots on assertion failure for post-mortem analysis.

## Solution

### 1. Playwright test as synthetic check

```typescript
// tests/synthetic/api-health.spec.ts
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.SYNTHETIC_TARGET_URL ?? 'https://api.example.com';
const AE_ENDPOINT = process.env.AE_INGEST_URL ?? '';
const AE_TOKEN = process.env.AE_TOKEN ?? '';

async function reportResult(
  testName: string,
  passed: boolean,
  durationMs: number,
  region: string,
  errorMessage?: string
) {
  if (!AE_ENDPOINT) return;
  await fetch(AE_ENDPOINT, {
    method: 'POST',
    headers: { Authorization: `Bearer ${AE_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      dataset: 'synthetic_checks',
      indexes: { test_name: testName, region, status: passed ? 'pass' : 'fail' },
      blobs: { error: errorMessage ?? '' },
      doubles: { duration_ms: durationMs },
      timestamp: new Date().toISOString(),
    }),
  });
}

test('GET /health returns 200 with expected JSON', async ({ page, request }) => {
  const region = process.env.SYNTHETIC_REGION ?? 'unknown';
  const start = Date.now();
  let passed = false;
  let errorMessage: string | undefined;

  try {
    const response = await request.get(`${BASE_URL}/health`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toMatchObject({ status: 'ok' });
    passed = true;
  } catch (err) {
    errorMessage = String(err);
    throw err;
  } finally {
    await reportResult('GET /health', passed, Date.now() - start, region, errorMessage);
  }
});

test('POST /api/echo returns request body', async ({ request }) => {
  const region = process.env.SYNTHETIC_REGION ?? 'unknown';
  const start = Date.now();
  let passed = false;
  let errorMessage: string | undefined;

  try {
    const payload = { hello: 'synthetic', ts: Date.now() };
    const response = await request.post(`${BASE_URL}/api/echo`, { data: payload });
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toMatchObject({ hello: 'synthetic' });
    passed = true;
  } catch (err) {
    errorMessage = String(err);
    throw err;
  } finally {
    await reportResult('POST /api/echo', passed, Date.now() - start, region, errorMessage);
  }
});
```

### 2. Screenshot on failure uploaded to R2

```typescript
// tests/synthetic/screenshot-on-failure.ts
import { FullConfig, FullResult, Reporter, Suite, TestCase, TestResult } from '@playwright/test/reporter';
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';

export default class R2ScreenshotReporter implements Reporter {
  private s3: S3Client;

  constructor() {
    this.s3 = new S3Client({
      region: 'auto',
      endpoint: process.env.R2_ENDPOINT ?? '',
      credentials: {
        accessKeyId: process.env.R2_ACCESS_KEY_ID ?? '',
        secretAccessKey: process.env.R2_SECRET_ACCESS_KEY ?? '',
      },
    });
  }

  async onTestEnd(test: TestCase, result: TestResult) {
    if (result.status !== 'failed') return;

    for (const attachment of result.attachments) {
      if (attachment.name !== 'screenshot' || !attachment.body) continue;
      const key = `synthetic/${process.env.SYNTHETIC_REGION ?? 'ci'}/${Date.now()}-${test.title.replace(/\s+/g, '-')}.png`;
      await this.s3.send(
        new PutObjectCommand({
          Bucket: process.env.R2_BUCKET ?? 'monitoring',
          Key: key,
          Body: attachment.body,
          ContentType: 'image/png',
          Metadata: { test: test.title, region: process.env.SYNTHETIC_REGION ?? 'ci' },
        })
      );
      console.log(`Screenshot uploaded to R2: ${key}`);
    }
  }
}
```

### 3. playwright.config.ts for multi-region matrix

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/synthetic',
  timeout: 15_000,
  retries: 1,
  reporter: [
    ['list'],
    ['./tests/synthetic/screenshot-on-failure.ts'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],
  use: {
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
```

### 4. GitHub Actions cron with region matrix

```yaml
# .github/workflows/synthetic-monitoring.yml
name: Synthetic Monitoring

on:
  schedule:
    - cron: '*/10 * * * *'   # every 10 minutes
  workflow_dispatch:

jobs:
  synthetic:
    strategy:
      fail-fast: false
      matrix:
        region: [us-east, eu-west, ap-southeast]
        runner: [ubuntu-latest]
    runs-on: ${{ matrix.runner }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - run: npx playwright install --with-deps chromium
      - name: Run synthetic checks
        env:
          SYNTHETIC_TARGET_URL: ${{ secrets.SYNTHETIC_TARGET_URL }}
          SYNTHETIC_REGION: ${{ matrix.region }}
          AE_INGEST_URL: ${{ secrets.AE_INGEST_URL }}
          AE_TOKEN: ${{ secrets.AE_TOKEN }}
          R2_ENDPOINT: ${{ secrets.R2_ENDPOINT }}
          R2_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY_ID }}
          R2_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_ACCESS_KEY }}
          R2_BUCKET: monitoring
        run: npx playwright test --project=chromium
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report-${{ matrix.region }}
          path: playwright-report/
          retention-days: 7
```

### 5. Alert Worker on assertion failure

```typescript
// src/workers/synthetic-alert.ts
import type { ScheduledEvent, Env } from '@cloudflare/workers-types';

interface Env {
  ANALYTICS_ENGINE: AnalyticsEngineDataset;
  ALERT_WEBHOOK_URL: string;
  DB: D1Database;
}

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    // Query recent failures in the last 15 minutes
    const result = await env.DB.prepare(`
      SELECT test_name, region, COUNT(*) as fail_count
      FROM synthetic_results
      WHERE status = 'fail'
        AND recorded_at > datetime('now', '-15 minutes')
      GROUP BY test_name, region
      HAVING fail_count >= 2
    `).all();

    for (const row of result.results) {
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: `SYNTHETIC ALERT: ${row.test_name} failing in ${row.region} (${row.fail_count} failures in 15m)`,
        }),
      });
    }
  },
};
```

## Implementation Details

- **Retry policy**: Set `retries: 1` in Playwright config. A flaky network should not page on the first failure; two consecutive failures within a window warrant an alert.
- **Regions**: GitHub Actions hosted runners are all US-East. True multi-region requires self-hosted runners or services like Checkly/k6 Cloud. The region matrix above is logical labeling unless you pin runners to specific cloud regions.
- **Analytics Engine ingestion**: Use the REST `/v1/accounts/{id}/analytics_engine/sql` endpoint to query results. The `blobs`, `doubles`, and `indexes` schema maps directly to AE column families.
- **Screenshot retention**: Set R2 lifecycle rules to expire `synthetic/` prefix after 30 days to control storage costs.

## Anti-patterns

- **Running synthetics only in CI on PR**: Synthetic checks must run against the live deployed environment on a schedule, not against a preview build in PR pipelines.
- **No deduplication on alerts**: Without a minimum failure count threshold you will get alerted on single transient network hiccups. Always require N failures within a window.
- **Storing screenshots in Git artifacts only**: GitHub artifact retention is 90 days max and not queryable. R2 provides durable storage with direct URL access for post-mortems.
- **Hardcoding base URLs**: Use `SYNTHETIC_TARGET_URL` env var so the same test suite targets staging or production without code changes.

## Gotchas

- Analytics Engine has an ingestion delay of up to 60 seconds. Don't query for results immediately after a test run in the same pipeline step.
- `request.post()` in Playwright APIRequestContext does not follow the page's cookie jar. If your endpoint requires session cookies, use `page.request` instead.
- GitHub Actions cron minimum interval is 5 minutes and may drift by several minutes under load.
- R2 presigned URLs expire. Store the R2 key (not the presigned URL) in your alert message and generate presigned URLs on demand in your dashboard.

## Verification

1. Trigger `workflow_dispatch` on the GitHub Actions workflow and confirm the run completes.
2. Deliberately break the `/health` endpoint and verify the alert webhook fires within two cron intervals.
3. Query Analytics Engine: `SELECT test_name, region, AVG(duration_ms) FROM synthetic_checks WHERE timestamp > NOW() - INTERVAL '1' HOUR GROUP BY 1, 2`.
4. Check R2 bucket for a screenshot PNG after introducing a failing assertion.

## Related

- `workers-uptime-monitor-cron-kv` — lightweight HTTP uptime checks without a browser
- `dead-man-switch-cron-alert` — alerting when a cron Worker stops reporting
- `workers-on-call-rotation-pagerduty` — routing synthetic alerts to the on-call engineer
- `real-user-monitoring-beacon` — complement synthetics with real user timing

## Sources

- https://playwright.dev/docs/api/class-apirequestcontext
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/r2/api/s3/api/
- https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule
