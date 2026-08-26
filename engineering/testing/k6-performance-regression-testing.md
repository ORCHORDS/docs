# k6-performance-regression-testing

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A release ships with a 40 % p95 latency increase that was
not caught in CI. Load tests ran manually months ago and
the numbers were never compared against the new build.

## Context

k6 is a Go-backed, JavaScript-scripted load-testing tool
designed for developer workflows. Scripts run as virtual
users (VUs) that execute a default function in a loop.
Thresholds turn performance budgets into pass/fail CI
gates. Running k6 against a staging URL on every merge to
`main` creates a regression baseline that surfaces latency
increases before they reach production.

## Script Structure and VU Ramp Patterns

```js
// scripts/perf-regression.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const apiDuration = new Trend('api_duration', true);
const errorRate   = new Rate('error_rate');

export const options = {
  // Ramp up → steady state → ramp down
  stages: [
    { duration: '30s', target: 10 },  // warm-up
    { duration: '2m',  target: 50 },  // load
    { duration: '30s', target: 0 },   // cool-down
  ],
  thresholds: {
    http_req_duration:       ['p(95)<400', 'p(99)<800'],
    error_rate:              ['rate<0.01'],
    'http_req_duration{name:list-items}': ['p(95)<200'],
  },
};

export default function () {
  const res = http.get(
    `${__ENV.BASE_URL}/api/items`,
    { tags: { name: 'list-items' } }
  );
  check(res, { 'status 200': (r) => r.status === 200 });
  apiDuration.add(res.timings.duration);
  errorRate.add(res.status !== 200);
  sleep(1);
}
```

VU ramp patterns:

| Pattern     | Stages shape            | Use case             |
|-------------|-------------------------|----------------------|
| Steady load | ramp / flat / ramp-down | Baseline comparison  |
| Stress      | progressive ramp-up     | Find breaking point  |
| Spike       | instant jump            | Flash-sale sim       |

## Thresholds as Pass/Fail Gates

Thresholds abort the test run with exit code 99 when
breached, making `k6 run` behave like a test assertion:

```js
thresholds: {
  // Built-in metric — p95 response time
  http_req_duration: ['p(95)<400'],

  // Custom metric tag — per-endpoint budget
  'http_req_duration{name:list-items}': ['p(95)<200'],

  // Abort immediately if error rate spikes above 5 %
  error_rate: ['rate<0.05', { abortOnFail: true }],
},
```

CI step exits non-zero on breach → build fails.

## Cloudflare Workers Testing

Test a Workers staging deployment the same way as any
HTTP endpoint — k6 runs outside the Cloudflare network:

```js
// workers-perf.js
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.WORKER_URL
  || 'https://staging.myapp.workers.dev';

export const options = {
  vus: 20,
  duration: '1m',
  thresholds: { http_req_duration: ['p(95)<100'] },
};

export default function () {
  const r = http.get(`${BASE}/api/search?q=test`);
  check(r, {
    'status 200':       (res) => res.status === 200,
    'body non-empty':   (res) => res.body.length > 0,
    'sub-100ms':        (res) => res.timings.duration < 100,
  });
}
```

Workers cold-start adds ~5 ms on the first request per VU;
include a warm-up stage or discard VU iteration 0.

## CI Integration and Grafana Cloud k6

GitHub Actions workflow:

```yaml
- name: Performance regression gate
  env:
    BASE_URL: ${{ vars.STAGING_URL }}
    K6_CLOUD_TOKEN: ${{ secrets.K6_CLOUD_TOKEN }}
  run: |
    k6 run \
      --out cloud \
      --tag testrun=${{ github.sha }} \
      scripts/perf-regression.js
```

`--out cloud` streams metrics to Grafana Cloud k6
in real time. Each run is tagged with the commit SHA,
enabling commit-by-commit p95/p99 comparison in the
Grafana dashboard.

Compare p95 between releases by running each build with
`--summary-export=<file>.json` and diffing the
`metrics.http_req_duration.values["p(95)"]` key with `jq`
or the Grafana Cloud k6 trend view.

## Anti-patterns

- Using `k6 cloud run` without thresholds — results are
  informational only; the CI step always passes.
- Running load tests against the production database
  without read replicas — VU traffic hits live user data.
- Hard-coding absolute thresholds (e.g. `p(95)<400`)
  without measuring baseline first — threshold is
  arbitrary and may be too tight or too loose.
- Sharing one auth token across all VUs — a rate-limited
  token causes correlated failures at scale.

## Gotchas

- k6 scripts are JavaScript but execute in a Go runtime —
  Node.js built-ins (`fs`, `process`, `require`) are
  unavailable; use k6's own `open()` for file reads.
- `sleep(1)` between iterations is essential for realistic
  think-time; omitting it drives artificial VU concurrency.
- The `stages` option is shorthand for the `ramping-vus`
  executor; for precise control use `scenarios` with an
  explicit executor key.
- Custom `Trend` metrics need `true` as the second arg
  to surface percentiles in thresholds — plain
  `new Trend('x')` only reports min/avg/max.

## Verification

```bash
# Dry-run: 1 VU, 10 s, print summary to stdout
k6 run --vus 1 --duration 10s scripts/perf-regression.js

# Expect exit code 0 if all thresholds pass
echo "Exit: $?"

# Confirm p95 value in summary JSON
k6 run --summary-export=/tmp/summary.json \
  scripts/perf-regression.js
jq '.metrics.http_req_duration.values' /tmp/summary.json
```

## Related

- `testing/performance-testing-k6.md`
- `testing/performance-regression-gates-ci.md`
- `testing/load-test-scenarios.md`
- `testing/soak-endurance-testing-methodology.md`

## Source URLs (verified 2026-08-17)

- https://grafana.com/docs/k6/latest/get-started/running-k6/
- https://grafana.com/docs/k6/latest/using-k6/thresholds/
- https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-vus/
- https://grafana.com/docs/grafana-cloud/testing/k6/
- https://developers.cloudflare.com/workers/testing/
