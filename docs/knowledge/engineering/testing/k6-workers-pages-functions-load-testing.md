# k6 Workers Pages Functions Load Testing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Cloudflare Pages site on example.com uses Pages Functions (`/functions` directory) to handle
form submissions, API proxying, and server-side rendering. Under load you observe 503 errors,
unexpected cold-start latency spikes, and KV read stalls that do not surface in unit tests. You need
a k6 load test that targets Pages Functions endpoints specifically, distinguishes function-level
latency from static-asset CDN latency, and fails the CI gate when P99 exceeds your SLO.

## Context

Cloudflare Pages Functions run on the same Workers runtime as standalone Workers but have a distinct
deployment pipeline and URL structure (`/api/*`, `/form`, etc., mapped via `functions/` files).
They share Workers limits (CPU time, memory, subrequest count). A k6 test can probe these endpoints
directly using the Pages preview URL or production domain. Because Pages CDN serves static assets
from edge cache, you must ensure k6 only measures dynamic function responses and does not conflate
cache hits with function latency.

## 1. Project structure and wrangler Pages local dev

```bash
# Start Pages Functions locally for development load tests
npx wrangler pages dev ./public --binding KV=my-kv-namespace --port 8788

# Or target the deployed preview branch
export PAGES_URL="https://my-branch.pages.dev"
```

```toml
# wrangler.toml (Pages project)
name = "my-pages-app"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "KV"
id = "abcdef1234567890"
```

## 2. k6 script: targeting Pages Function endpoints

```js
// load-tests/pages-functions.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const fnLatency = new Trend('pages_fn_latency', true);
const errorRate = new Rate('pages_fn_errors');

export const options = {
  stages: [
    { duration: '30s', target: 50 },   // ramp up
    { duration: '2m',  target: 50 },   // steady state
    { duration: '30s', target: 0 },    // ramp down
  ],
  thresholds: {
    // Pages Function P99 must stay under 800 ms
    pages_fn_latency: ['p(99)<800'],
    pages_fn_errors: ['rate<0.01'],
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.PAGES_URL || 'http://localhost:8788';

export default function () {
  // Target a Pages Function endpoint, not a static asset
  const res = http.get(`${BASE_URL}/api/items`, {
    headers: {
      // Bypass CDN cache for static assets by targeting /api paths
      'Cache-Control': 'no-store',
      Accept: 'application/json',
    },
  });

  fnLatency.add(res.timings.duration);
  errorRate.add(res.status >= 400);

  check(res, {
    'status is 200': r => r.status === 200,
    'response is JSON': r => r.headers['Content-Type']?.includes('application/json'),
    'no CF-Cache-Status: HIT': r => r.headers['CF-Cache-Status'] !== 'HIT',
  });

  sleep(0.5);
}
```

## 3. POST form submission through a Pages Function

```js
// load-tests/pages-form-submit.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const submitLatency = new Trend('form_submit_latency', true);

export const options = {
  vus: 20,
  duration: '1m',
  thresholds: {
    form_submit_latency: ['p(95)<500', 'p(99)<1000'],
  },
};

const BASE_URL = __ENV.PAGES_URL || 'http://localhost:8788';

export default function () {
  const payload = JSON.stringify({
    email: `user_${__VU}_${__ITER}@example.com`,
    message: 'Load test submission',
  });

  const res = http.post(`${BASE_URL}/api/contact`, payload, {
    headers: { 'Content-Type': 'application/json' },
  });

  submitLatency.add(res.timings.duration);

  check(res, {
    'form accepted': r => r.status === 200 || r.status === 201,
    'no server error': r => r.status < 500,
  });

  sleep(1);
}
```

## 4. Middleware chain latency breakdown

```js
// load-tests/pages-middleware-breakdown.js
import http from 'k6/http';
import { check } from 'k6';
import { Trend } from 'k6/metrics';

// Measure DNS + TLS + TTFB separately to isolate function cold-start
const ttfb = new Trend('pages_fn_ttfb', true);
const totalDuration = new Trend('pages_fn_total', true);

export const options = {
  vus: 10,
  duration: '2m',
  thresholds: {
    // Cold start (TTFB) must be under 200 ms at P95
    pages_fn_ttfb: ['p(95)<200'],
  },
};

const BASE_URL = __ENV.PAGES_URL || 'http://localhost:8788';

export default function () {
  const res = http.get(`${BASE_URL}/api/status`);

  ttfb.add(res.timings.waiting);          // time to first byte
  totalDuration.add(res.timings.duration); // full response duration

  check(res, { 'status 200': r => r.status === 200 });
}
```

## 5. CI GitHub Actions integration

```yaml
# .github/workflows/pages-load-test.yml
name: Pages Functions Load Test

on:
  deployment_status:

jobs:
  load-test:
    if: github.event.deployment_status.state == 'success'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run k6 load test against Pages preview URL
        uses: grafana/k6-action@v0.3.1
        with:
          filename: load-tests/pages-functions.js
        env:
          PAGES_URL: ${{ github.event.deployment_status.target_url }}
          K6_CLOUD_TOKEN: ${{ secrets.K6_CLOUD_TOKEN }}

      - name: Upload k6 results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: k6-results
          path: results.json
```

## Anti-patterns

- **Load testing static assets alongside functions**: `https://pages.dev/images/logo.png` will always
  hit CDN edge cache; mixing these into the same `Trend` metric hides actual function latency.
- **Using fixed `__VU` IDs as email addresses in POST bodies**: repeated submissions with the same
  email may trigger server-side deduplication, caching, or rate limiting that masks true behavior.
  Combine `__VU` and `__ITER` for uniqueness.
- **Pointing k6 at `localhost:8788` in CI**: wrangler dev may not be running. Use the deployed
  Pages URL via `PAGES_URL` env var; fall back to local only for pre-commit smoke runs.
- **Ignoring `CF-Cache-Status` header**: if a Pages Function sets `Cache-Control: public`, edge
  cache will serve subsequent requests without invoking the function at all, making P99 look
  artificially low.

## Gotchas

- Pages Functions URL routing follows the file path under `functions/`. `functions/api/items.ts`
  maps to `/api/items` but `functions/api/[id].ts` maps to `/api/:id`. Ensure k6 URLs match the
  actual routing.
- `wrangler pages dev` does not emulate KV TTL expiry or Durable Object storage limits; latency
  figures from local dev may differ significantly from production.
- The `deployment_status` GitHub Actions trigger fires for every environment (Preview and Production).
  Gate the load test on `github.event.deployment_status.environment_url` containing `pages.dev` to
  avoid hammering production on every PR.
- k6 open-source does not stream results to Grafana Cloud by default; set `K6_CLOUD_TOKEN` and add
  `-o cloud` to the k6 command, or use the `grafana/k6-action` which handles this automatically.

## Verification

```bash
# Local smoke run (5 VUs, 30 s)
k6 run --vus 5 --duration 30s \
  -e PAGES_URL=http://localhost:8788 \
  load-tests/pages-functions.js

# Check threshold summary
k6 run load-tests/pages-functions.js 2>&1 | grep -E 'pages_fn_latency|PASSED|FAILED'

# Target a specific preview URL
PAGES_URL="https://my-branch.pages.dev" k6 run load-tests/pages-functions.js
```

## Related

- `k6-load-testing-cloudflare-workers-api.md`
- `k6-performance-regression-testing.md`
- `k6-workers-rate-limiter-load-test.md`
- `playwright-cloudflare-pages-e2e.md`
- `performance-regression-gates-ci.md`

## Sources

- https://developers.cloudflare.com/pages/functions/
- https://grafana.com/docs/k6/latest/
- https://grafana.com/docs/k6/latest/using-k6/metrics/
- https://developers.cloudflare.com/pages/configuration/build-configuration/
