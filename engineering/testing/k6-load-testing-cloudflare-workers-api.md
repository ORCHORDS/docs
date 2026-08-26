# k6-load-testing-cloudflare-workers-api

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

The example project API holds up fine under desktop traffic but
degrades when mobile clients hit the same Workers endpoints
with slower connections and higher parallel session counts.
D1 queries saturate under concurrent load, but the team
does not know the exact breaking point. Cloudflare rate
limiting returns 429s that go undetected in CI because
load tests were never written.

## Context

k6 is a Go-backed, JavaScript-scripted load-testing tool.
It drives virtual users (VUs) that execute a default
function in a tight loop, simulating real client behaviour.
Testing a Cloudflare Workers API with k6 runs k6 outside
the Cloudflare network — requests reach the edge as normal
HTTPS traffic. This means: cold-start latency is visible,
rate limiting fires as in production, and edge caching
behaviour is observable. For mobile simulation, k6 sets
User-Agent strings and uses the `scenarios` API with the
`ramping-vus` executor to simulate 3G / 4G LTE connection
profiles via throughput-limited virtual clients.

## Project Structure

```
scripts/
  k6/
    lib/
      mobile-profiles.js   # shared network + UA helpers
      auth.js              # token pool
    workers-load.js        # main load scenario
    d1-saturation.js       # D1 query saturation test
    rate-limit.js          # 429 detection test
```

## Mobile Connection Profile Simulation

k6 itself does not shape TCP bandwidth, but you can
simulate the effect of slower connections by inserting
`sleep()` based on payload size and throttling VU
concurrency to match a realistic mobile session count.
For Chromium-backed true bandwidth shaping, pipe through
a network proxy (toxiproxy) or use k6 Browser.

Shared profile constants:

```js
// scripts/k6/lib/mobile-profiles.js

// Sleep seconds = payload bytes / throughput bytes-per-sec
export const PROFILE = {
  '3G_SLOW': {
    downloadBps: (750  * 1024) / 8,  // 750 Kbps
    uploadBps:   (250  * 1024) / 8,  // 250 Kbps
    latencyMs:   100,
    ua: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
      + 'AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1',
  },
  '4G_LTE': {
    downloadBps: (4    * 1024 * 1024) / 8,  // 4 Mbps
    uploadBps:   (3    * 1024 * 1024) / 8,  // 3 Mbps
    latencyMs:   20,
    ua: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) '
      + 'AppleWebKit/537.36 Mobile Safari/537.36',
  },
  WIFI: {
    downloadBps: (20   * 1024 * 1024) / 8,  // 20 Mbps
    uploadBps:   (5    * 1024 * 1024) / 8,  //  5 Mbps
    latencyMs:   5,
    ua: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) '
      + 'AppleWebKit/537.36 Chrome/126.0 Safari/537.36',
  },
};

/**
 * Return the sleep duration in seconds that a client on
 * `profile` would need to download `bytes` bytes.
 */
export function transferDelay(profile, bytes) {
  return bytes / profile.downloadBps;
}
```

Profile summary:

| Profile   | Down       | Up        | Latency | Device  |
|-----------|------------|-----------|---------|---------|
| 3G slow   | 750 Kbps   | 250 Kbps  | 100 ms  | iOS UA  |
| 4G LTE    | 4 Mbps     | 3 Mbps    | 20 ms   | Android |
| Wi-Fi     | 20 Mbps    | 5 Mbps    | 5 ms    | Desktop |

## Main Load Scenario: Mobile vs Desktop VU Split

```js
// scripts/k6/workers-load.js
import http           from 'k6/http';
import { check, sleep } from 'k6';
import { PROFILE, transferDelay } from './lib/mobile-profiles.js';

const BASE = __ENV.WORKER_URL
  || 'https://api.example project.workers.dev';

export const options = {
  scenarios: {
    mobile_3g: {
      executor:        'ramping-vus',
      startVUs:        0,
      stages: [
        { duration: '30s', target: 20 },
        { duration: '2m',  target: 20 },
        { duration: '15s', target: 0  },
      ],
      env: { PROFILE_NAME: '3G_SLOW' },
      tags: { device: 'mobile_3g' },
    },
    mobile_4g: {
      executor:        'ramping-vus',
      startVUs:        0,
      stages: [
        { duration: '30s', target: 30 },
        { duration: '2m',  target: 30 },
        { duration: '15s', target: 0  },
      ],
      env: { PROFILE_NAME: '4G_LTE' },
      tags: { device: 'mobile_4g' },
    },
    desktop_wifi: {
      executor:        'ramping-vus',
      startVUs:        0,
      stages: [
        { duration: '30s', target: 50 },
        { duration: '2m',  target: 50 },
        { duration: '15s', target: 0  },
      ],
      env: { PROFILE_NAME: 'WIFI' },
      tags: { device: 'desktop' },
    },
  },

  thresholds: {
    // Global
    http_req_duration:                       ['p(95)<400'],
    // Mobile 3G budget is looser
    'http_req_duration{device:mobile_3g}':   ['p(95)<800'],
    'http_req_duration{device:mobile_4g}':   ['p(95)<500'],
    'http_req_duration{device:desktop}':     ['p(95)<200'],
    // Error rate
    http_req_failed:                         ['rate<0.01'],
  },
};

export default function () {
  const profile = PROFILE[__ENV.PROFILE_NAME || 'WIFI'];

  const res = http.get(`${BASE}/api/events`, {
    headers: { 'User-Agent': profile.ua },
    tags:    { name: 'list-events' },
  });

  check(res, {
    'status 200': (r) => r.status === 200,
    'has results': (r) => {
      try { return JSON.parse(r.body).results?.length > 0; }
      catch { return false; }
    },
  });

  // Simulate transfer time on slow connection
  sleep(transferDelay(profile, res.body?.length ?? 1024));
}
```

## D1 Query Saturation Test

Identify the VU count at which D1 starts returning errors
or exceeding the 30-second query timeout:

```js
// scripts/k6/d1-saturation.js
import http           from 'k6/http';
import { check }      from 'k6';
import { Rate, Trend } from 'k6/metrics';

const d1Errors    = new Rate('d1_errors');
const d1Duration  = new Trend('d1_duration', true);
const BASE        = __ENV.WORKER_URL
  || 'https://api.example project.workers.dev';

export const options = {
  // Progressive ramp: find the breaking point
  stages: [
    { duration: '1m',  target: 10  },
    { duration: '1m',  target: 50  },
    { duration: '1m',  target: 100 },
    { duration: '1m',  target: 200 },
    { duration: '30s', target: 0   },
  ],
  thresholds: {
    d1_errors:   ['rate<0.02'],
    d1_duration: ['p(99)<2000'],
  },
};

export default function () {
  // Heavy read: full-text search across D1 table
  const res = http.get(
    `${BASE}/api/search?q=event&limit=100`,
    { tags: { name: 'd1-search' } }
  );

  const isD1Error =
    res.status === 500 &&
    (res.body?.includes('D1') || res.body?.includes('SQL'));

  d1Errors.add(isD1Error);
  d1Duration.add(res.timings.duration);

  check(res, {
    'not D1 error': () => !isD1Error,
    'sub 2s':       (r) => r.timings.duration < 2000,
  });
}
```

Run with output to JSON for post-analysis:

```bash
k6 run \
  --out json=results/d1-saturation.json \
  --env WORKER_URL=https://staging.example project.workers.dev \
  scripts/k6/d1-saturation.js
```

## Cloudflare Rate Limiting Detection

Workers can enforce rate limits via the Rate Limiting API
or Cloudflare Rules. A 429 response must be tested
explicitly — standard load tests suppress it because checks
pass at low VU counts:

```js
// scripts/k6/rate-limit.js
import http             from 'k6/http';
import { check, sleep } from 'k6';
import { Rate }         from 'k6/metrics';

const rateLimitHits = new Rate('rate_limit_hits');
const BASE          = __ENV.WORKER_URL
  || 'https://api.example project.workers.dev';

export const options = {
  // Spike: all VUs start instantly to trip the rate limiter
  scenarios: {
    spike: {
      executor:  'constant-vus',
      vus:       200,
      duration:  '30s',
    },
  },
  thresholds: {
    // Expect the rate limiter to fire; confirm it recovers
    rate_limit_hits: ['rate<0.30'],  // <30% 429s is acceptable
  },
};

export default function () {
  const res = http.get(`${BASE}/api/events`, {
    headers: { 'User-Agent': 'k6-rate-limit-test/1.0' },
  });

  const is429 = res.status === 429;
  rateLimitHits.add(is429);

  check(res, {
    'accepted or rate limited': (r) =>
      r.status === 200 || r.status === 429,
    'retry-after present on 429': (r) =>
      r.status !== 429 ||
      r.headers['Retry-After'] !== undefined,
  });

  if (is429) {
    // Honour the Retry-After header when present
    const retryAfter =
      parseInt(res.headers['Retry-After'] ?? '1', 10);
    sleep(Math.min(retryAfter, 5));
  } else {
    sleep(0.1);
  }
}
```

Cloudflare rate limiting response codes:

| HTTP Code | Meaning                               | Action              |
|-----------|---------------------------------------|---------------------|
| 429       | Rate limit exceeded (Cloudflare rule) | Sleep, retry        |
| 503       | Worker threw / memory limit exceeded  | Investigate Worker  |
| 1015      | Cloudflare-level rate limit           | Retry-After present |

## CI Integration

```yaml
# .github/workflows/load.yml
name: Load tests
on:
  push:
    branches: [main]

jobs:
  k6:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install k6
        run: |
          curl -sfL https://dl.k6.io/key.gpg \
            | gpg --dearmor \
            | sudo tee /usr/share/keyrings/k6-archive-keyring.gpg
          echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] \
            https://dl.k6.io/deb stable main" \
            | sudo tee /etc/apt/sources.list.d/k6.list
          sudo apt-get update && sudo apt-get install k6

      - name: Mobile + desktop load test
        env:
          WORKER_URL: ${{ vars.STAGING_WORKER_URL }}
        run: |
          k6 run \
            --summary-export=results/load-summary.json \
            scripts/k6/workers-load.js

      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: k6-results-${{ github.sha }}
          path: results/
```

## Anti-patterns

- Running load tests against `*.workers.dev` with no auth
  when production bindings (D1, KV) are shared — load test
  traffic modifies real data.
- Using `sleep(1)` uniformly regardless of profile — this
  sets the same think-time for 3G and desktop VUs, defeating
  the purpose of profile separation.
- Omitting `abortOnFail` on the error rate threshold —
  a catastrophic failure (Worker crashed) keeps running and
  incurring cost.
- Hard-coding the Worker URL in scripts — use `__ENV`
  variables so staging and production targets are
  swappable without editing code.
- Interpreting 429s as test failures — they are expected
  responses from the rate limiter; assert on
  `rate_limit_hits` rate, not on raw `http_req_failed`.

## Gotchas

- k6 runs in a Go runtime; `require`, `fs`, `process.env`
  are not available. Read files with k6's `open()` at the
  top level (not inside the default function).
- Workers have a 128 MB memory limit per isolate; under
  high concurrent VU load a single Workers instance serves
  many requests in the same isolate — you are load testing
  the CPU budget, not memory separately.
- Cloudflare's edge caches responses; early VUs may return
  cached data faster than the Worker executes, skewing
  latency numbers downward. Tag cached vs. uncached
  requests using the `cf-cache-status` response header.
- `transferDelay()` simulates think-time but does not shape
  actual TCP bandwidth. True throughput simulation requires
  a network proxy or k6 Browser with CDP throttling.
- The D1 saturation test can leave orphan connections if
  the Worker does not close them. Monitor `cf-meta-db-wait`
  headers (if instrumented) for connection pool exhaustion.

## Verification

```bash
# Quick smoke run: 5 VUs, 20 s, print summary
k6 run --vus 5 --duration 20s \
  --env WORKER_URL=https://staging.example project.workers.dev \
  scripts/k6/workers-load.js

# Confirm exit code 0 means all thresholds passed
echo "k6 exit: $?"

# Parse p95 from JSON summary
jq '.metrics.http_req_duration.values["p(95)"]' \
  results/load-summary.json
```

## Related

- `testing/k6-performance-regression-testing.md`
- `testing/performance-testing-k6.md`
- `testing/load-test-scenarios.md`
- `testing/miniflare-d1-integration-testing.md`
- `testing/playwright-mobile-device-emulation.md`

## Source URLs (verified 2026-08-22)

- https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ramping-vus/
- https://grafana.com/docs/k6/latest/using-k6/thresholds/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
- https://developers.cloudflare.com/d1/observability/metrics-analytics/
- https://grafana.com/docs/k6/latest/javascript-api/k6-metrics/
