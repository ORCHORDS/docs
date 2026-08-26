# load-testing-before-deploy

**Issue:** Running load tests as a deployment gate to catch performance regressions before production
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Performance regressions introduced in code changes are invisible until production traffic exposes them. Load testing in the deploy pipeline catches regressions in staging before they reach users.

## Pattern / Solution
k6 load test script:
```javascript
// load-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '2m', target: 50 },    // ramp up
    { duration: '5m', target: 50 },    // steady state
    { duration: '1m', target: 0 },     // ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // 95th percentile < 500ms
    errors: ['rate<0.01'],             // error rate < 1%
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const res = http.get(`${__ENV.BASE_URL}/api/products`);
  check(res, { 'status 200': (r) => r.status === 200 });
  errorRate.add(res.status !== 200);
  sleep(1);
}
```

Run in CI (GitHub Actions):
```yaml
- name: Run k6 load test
  uses: grafana/k6-action@v0.3.1
  with:
    filename: tests/load-test.js
  env:
    BASE_URL: https://staging.myapp.example.com
    K6_CLOUD_TOKEN: ${{ secrets.K6_CLOUD_TOKEN }}

- name: Fail pipeline if thresholds exceeded
  if: failure()
  run: |
    echo "Load test failed — blocking deployment to production"
    exit 1
```

Compare p95 against baseline:
```bash
# Extract current p95 from k6 JSON output
CURRENT_P95=$(jq '.metrics.http_req_duration.values["p(95)"]' results.json)
BASELINE_P95=$(cat .perf-baseline)

# Allow max 20% regression
MAX_ALLOWED=$(echo "$BASELINE_P95 * 1.2" | bc)
if (( $(echo "$CURRENT_P95 > $MAX_ALLOWED" | bc -l) )); then
  echo "p95 regressed: ${CURRENT_P95}ms vs baseline ${BASELINE_P95}ms"
  exit 1
fi
```

## Gotchas
- Load test against staging, not production; production load tests require careful traffic shaping
- Static VU count does not model bursty real traffic; use arrival-rate executors for more realistic tests
- Warm up the cache before measuring — cold cache performance is not representative of steady state
- Load tests consume staging database connections; run after integration tests, not in parallel
- Store performance baselines in Git so regressions are detectable across PRs

## Related
- `performance-baseline-tracking.md`
- `kubernetes-horizontal-pod-autoscaler.md`
- `deployment-verification-smoke-tests.md`
