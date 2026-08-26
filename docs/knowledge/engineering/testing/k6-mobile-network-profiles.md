# Load Testing with k6 Targeting Mobile Network Profiles

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Your Cloudflare Workers API passes desktop-grade load tests easily but degrades under real-world
mobile traffic: 3G users in emerging markets time out on the `/search` endpoint; background
Workers fan-out adds 800 ms that is invisible at 100 Mbps but catastrophic at 1.5 Mbps. You need
load tests that model actual mobile network conditions — bandwidth caps, latency, packet loss, and
concurrent connection limits — so you catch regressions before they reach production.

## Context

k6 runs JavaScript test scripts in a headless Go runtime. It does not control the network stack
directly (it is not a browser), but it can simulate mobile network behaviour by:

1. **Throttling at the OS or proxy level** — `tc netem` on Linux or a proxy such as
   `toxiproxy` in CI, combined with k6's normal HTTP load.
2. **Tuning k6's HTTP client settings** — connection concurrency, timeout budgets, and
   keep-alive behaviour that mirrors constrained mobile clients.
3. **Modelling realistic payload sizes and think-times** — mobile requests carry smaller
   payloads, have longer inter-request pauses (user interaction model), and retry more
   aggressively on transient errors.
4. **k6 Browser extension** — when testing a Next.js / Cloudflare Pages UI, the k6 Browser
   module runs Chromium with `DevTools.Network.emulateNetworkConditions` to replicate
   network presets like "Slow 3G" or "4G LTE".

Stack: k6 v0.55+, Grafana k6 Cloud (optional), toxiproxy v2, GitHub Actions, Cloudflare Workers.

---

## Network Profile Constants

Define standard mobile network conditions as k6 shared constants so every scenario references
the same numbers.

```js
// lib/network-profiles.js
/**
 * Mobile network profiles derived from Chrome DevTools presets.
 * bandwidth: bytes/sec (download)
 * latency:   one-way milliseconds (k6 uses this as round-trip add-on via think time)
 * loss:      probability 0–1 (simulated via toxiproxy in CI, not native k6)
 */
export const NETWORK_PROFILES = {
  // Emerging-market 2G (GPRS)
  GPRS: {
    bandwidth: 6_400,        // 50 kbps download
    latency: 500,
    loss: 0.02,
    maxConnections: 1,
    timeout: '60s',
    label: 'GPRS-50kbps',
  },
  // Typical developing-market 3G
  SLOW_3G: {
    bandwidth: 46_875,       // 375 kbps
    latency: 100,
    loss: 0.01,
    maxConnections: 2,
    timeout: '30s',
    label: 'Slow3G-375kbps',
  },
  // Average global mobile (Fast 3G / early 4G)
  FAST_3G: {
    bandwidth: 187_500,      // 1.5 Mbps
    latency: 40,
    loss: 0.005,
    maxConnections: 4,
    timeout: '15s',
    label: 'Fast3G-1.5Mbps',
  },
  // 4G LTE (comfortable urban)
  LTE: {
    bandwidth: 2_500_000,    // 20 Mbps
    latency: 10,
    loss: 0.001,
    maxConnections: 6,
    timeout: '10s',
    label: 'LTE-20Mbps',
  },
};
```

---

## k6 HTTP Load Test with Throttled Scenarios

```js
// tests/load/mobile-api.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import { NETWORK_PROFILES } from '../../lib/network-profiles.js';

// Custom metrics tagged per network profile.
const apiLatency = new Trend('api_latency', true);
const errorRate  = new Rate('error_rate');
const timeouts   = new Counter('timeouts');

const BASE_URL = __ENV.BASE_URL || 'https://api.staging.example.com';

// Run three scenarios in parallel, each modelling a different network tier.
export const options = {
  scenarios: {
    gprs_users: {
      executor: 'constant-vus',
      vus: 5,
      duration: '3m',
      tags: { network: NETWORK_PROFILES.GPRS.label },
      env: { NETWORK_PROFILE: 'GPRS' },
    },
    slow_3g_users: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 20 },
        { duration: '2m', target: 20 },
        { duration: '30s', target: 0 },
      ],
      tags: { network: NETWORK_PROFILES.SLOW_3G.label },
      env: { NETWORK_PROFILE: 'SLOW_3G' },
    },
    lte_users: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 30,
      maxVUs: 60,
      stages: [
        { duration: '1m', target: 30 },
        { duration: '2m', target: 30 },
        { duration: '30s', target: 0 },
      ],
      tags: { network: NETWORK_PROFILES.LTE.label },
      env: { NETWORK_PROFILE: 'LTE' },
    },
  },
  thresholds: {
    // P95 latency must stay under each profile's acceptable budget.
    'api_latency{network:Slow3G-375kbps}': ['p(95)<4000'],  // 4 s P95 on Slow 3G
    'api_latency{network:LTE-20Mbps}':     ['p(95)<800'],   // 800 ms P95 on LTE
    'error_rate':                           ['rate<0.02'],   // < 2% errors globally
    'http_req_failed':                      ['rate<0.01'],
  },
};

function getProfile() {
  return NETWORK_PROFILES[__ENV.NETWORK_PROFILE ?? 'LTE'];
}

export default function () {
  const profile = getProfile();

  const params = {
    timeout: profile.timeout,
    headers: {
      'Content-Type': 'application/json',
      // Simulate a real mobile UA so Workers can log the profile.
      'User-Agent': 'OrchordsApp/3.2 (Android 14; Mobile)',
      'X-Network-Profile': profile.label,
    },
    // k6 does not have per-VU bandwidth throttling natively.
    // The actual bandwidth cap is applied by toxiproxy (see CI section).
    // Here we model the *concurrency* limit of a mobile HTTP client.
    // Each VU represents one mobile connection, so no extra tuning needed.
  };

  // Simulate mobile interaction model: search → item detail → add-to-cart.
  const searchRes = http.get(
    `${BASE_URL}/v1/search?q=guitar&limit=10`,
    params,
  );

  check(searchRes, {
    'search 200': r => r.status === 200,
    'search has results': r => {
      try { return JSON.parse(r.body).items?.length > 0; }
      catch { return false; }
    },
  }) || errorRate.add(1);

  if (searchRes.timings.duration > Number(profile.timeout.replace('s', '')) * 1000) {
    timeouts.add(1);
  }

  apiLatency.add(searchRes.timings.duration, { network: profile.label });

  // Mobile user think-time: longer on slow networks (user waits for render).
  sleep(profile.latency / 500 + Math.random() * 2);

  // Fetch first item detail only if search succeeded.
  if (searchRes.status === 200) {
    const items = JSON.parse(searchRes.body)?.items ?? [];
    if (items.length > 0) {
      const detailRes = http.get(`${BASE_URL}/v1/items/${items[0].id}`, params);
      apiLatency.add(detailRes.timings.duration, { network: profile.label });
      check(detailRes, { 'detail 200': r => r.status === 200 }) || errorRate.add(1);
    }
  }

  sleep(1 + Math.random() * 3);
}
```

---

## Toxiproxy Integration for Real Bandwidth Caps in CI

k6 itself does not throttle bandwidth. For accurate mobile simulation, route traffic through
`toxiproxy`, which supports `bandwidth` and `latency` toxics.

### docker-compose.toxiproxy.yml

```yaml
version: '3.9'
services:
  toxiproxy:
    image: ghcr.io/shopify/toxiproxy:2.9.0
    ports:
      - "8474:8474"   # toxiproxy REST API
      - "8080:8080"   # slow-3g proxy
      - "8081:8081"   # gprs proxy
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8474/version"]
      interval: 2s
      timeout: 5s
      retries: 10
```

### scripts/setup-toxiproxy.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

PROXY_API="http://localhost:8474"
UPSTREAM="${UPSTREAM_HOST:-api.staging.example.com}:443"

# Create a Slow 3G proxy (375 kbps down, 100 ms latency).
curl -s -X POST "$PROXY_API/proxies" -H 'Content-Type: application/json' -d "{
  \"name\": \"slow3g\",
  \"listen\": \"0.0.0.0:8080\",
  \"upstream\": \"$UPSTREAM\",
  \"enabled\": true
}"

# Add bandwidth toxic: 375 kbps = 375000 / 8 bytes per 1000 ms = 46875 bytes/s.
# toxiproxy rate is in KB/s.
curl -s -X POST "$PROXY_API/proxies/slow3g/toxics" -H 'Content-Type: application/json' -d '{
  "name": "bandwidth",
  "type": "bandwidth",
  "stream": "downstream",
  "attributes": { "rate": 46 }
}'

# Add latency toxic: 100 ms one-way.
curl -s -X POST "$PROXY_API/proxies/slow3g/toxics" -H 'Content-Type: application/json' -d '{
  "name": "latency",
  "type": "latency",
  "stream": "downstream",
  "attributes": { "latency": 100, "jitter": 20 }
}'

echo "toxiproxy slow3g proxy ready on :8080"
```

### GitHub Actions job

```yaml
# .github/workflows/load-test-mobile.yml
name: Mobile Load Test

on:
  schedule:
    - cron: '0 2 * * 1'   # Weekly Monday 02:00 UTC
  workflow_dispatch:
    inputs:
      profile:
        description: 'Network profile (GPRS|SLOW_3G|FAST_3G|LTE)'
        default: 'SLOW_3G'

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Start toxiproxy
        run: |
          docker compose -f docker-compose.toxiproxy.yml up -d
          sleep 5
          bash scripts/setup-toxiproxy.sh
        env:
          UPSTREAM_HOST: ${{ vars.STAGING_API_HOST }}

      - name: Install k6
        run: |
          curl -fsSL https://dl.k6.io/key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/k6-archive-keyring.gpg
          echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
            | sudo tee /etc/apt/sources.list.d/k6.list
          sudo apt-get update && sudo apt-get install -y k6

      - name: Run mobile load test
        run: |
          k6 run \
            --env BASE_URL=http://localhost:8080 \
            --out json=results/k6-mobile.json \
            --summary-export=results/k6-summary.json \
            tests/load/mobile-api.js
        env:
          NETWORK_PROFILE: ${{ github.event.inputs.profile || 'SLOW_3G' }}

      - name: Upload results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: k6-mobile-results
          path: results/
          retention-days: 30
```

---

## k6 Browser: Emulating Mobile Network in a Headless Browser

When testing the Next.js front-end (Cloudflare Pages), use `k6/browser` with Chrome DevTools
Network emulation — this is the closest equivalent to Lighthouse's mobile throttling.

```js
// tests/load/mobile-browser.js
import { browser } from 'k6/browser';
import { check } from 'k6';

export const options = {
  scenarios: {
    mobile_slow3g: {
      executor: 'constant-vus',
      vus: 2,
      duration: '2m',
      options: {
        browser: {
          type: 'chromium',
        },
      },
    },
  },
  thresholds: {
    'browser_web_vital_lcp{scenario:mobile_slow3g}': ['p(75)<5000'],
    'browser_web_vital_cls{scenario:mobile_slow3g}': ['p(75)<0.1'],
  },
};

export default async function () {
  const page = await browser.newPage();

  // Emulate a mid-range Android device with Slow 3G conditions.
  await page.emulateMedia({ media: 'screen' });
  const client = await page.context().newCDPSession(page);

  await client.send('Network.enable');
  await client.send('Network.emulateNetworkConditions', {
    offline: false,
    downloadThroughput: (375 * 1024) / 8,   // 375 kbps in bytes/s
    uploadThroughput: (375 * 1024) / 8,
    latency: 100,
  });

  // Also emulate a mid-range device (2x CPU throttle).
  await client.send('Emulation.setCPUThrottlingRate', { rate: 4 });

  try {
    await page.goto(`${__ENV.PAGES_URL}/`, { waitUntil: 'networkidle' });

    check(page, {
      'home renders': () => page.locator('h1').isVisible(),
    });

    await page.locator('[data-testid="search-input"]').fill('guitar');
    await page.keyboard.press('Enter');
    await page.waitForSelector('[data-testid="search-results"]', { timeout: 10_000 });

    check(page, {
      'results visible': () =>
        page.locator('[data-testid="search-results"]').isVisible(),
    });
  } finally {
    await page.close();
  }
}
```

---

## Anti-patterns

**Relying solely on k6's `--rps` or VU model to simulate mobile load without network
throttling.**
Higher RPS from many fast VUs does not model the serialised, high-latency nature of a 3G mobile
client. A single mobile user on Slow 3G can consume a Worker's connection slot for 4+ seconds;
an unthrottled VU completes the same request in < 100 ms. The failure mode is invisible.

**Setting `timeout` to the same value for all network profiles.**
A 10-second timeout that passes for LTE users is a timeout violation for GPRS users on any
payload > 60 KB. Profile-specific timeouts must match bandwidth expectations.

**Running mobile load tests against the production origin.**
Toxiproxy or network throttling in CI does not touch the Cloudflare network; it only throttles
the connection between the k6 runner and the origin. Run against a staging Worker or use
Cloudflare's API Shield / Rate Limiting to ensure production is not affected.

**Ignoring jitter.**
Real mobile networks have significant jitter (20–80 ms). Tests with a fixed latency pass but
real users experience timeout cascades. Always add `jitter` to toxiproxy latency toxics.

---

## Gotchas

- **k6 does not natively throttle bandwidth per VU** — the `http.setResponseCallback` hook can
  read timing data but cannot limit transfer rate. Toxiproxy (or `tc netem`) is required for
  true bandwidth caps.

- **toxiproxy works at the TCP level** — it does not terminate TLS. To proxy HTTPS traffic in
  CI you need either (a) a non-TLS staging endpoint, (b) a TLS-terminating reverse proxy in
  front of toxiproxy, or (c) use HTTP for internal CI traffic only.

- **k6 Browser + CDP network emulation throttles only the Chromium renderer** — the Worker
  itself still receives the request at full speed. The throttling models the last-mile user
  experience, not origin-to-CDN bandwidth.

- **`sleep()` distribution matters** — `sleep(1)` is a fixed think-time. Mobile interaction
  models have long tail distributions; use `sleep(exponential(2))` from `k6/x/faker` or a
  simple `sleep(Math.random() * 5)` to avoid artificial synchronisation waves.

---

## Verification

```bash
# 1. Confirm toxiproxy is capping correctly.
docker run --rm --network host appropriate/curl curl -o /dev/null \
  -w "%{speed_download}\n" http://localhost:8080/v1/search?q=test
# Expected: ~46000 bytes/s on slow3g proxy.

# 2. Dry-run k6 with 1 VU for 30 s to sanity-check the script.
k6 run --env BASE_URL=http://localhost:8080 --vus 1 --duration 30s tests/load/mobile-api.js

# 3. Check threshold output: look for "✓" on all p95 assertions.
# 4. Inspect k6-summary.json for per-network metric breakdowns.
# 5. Run the browser test against staging Pages URL.
k6 run --env PAGES_URL=https://staging.pages.dev tests/load/mobile-browser.js
```

---

## Related

- `k6-load-testing-cloudflare-workers-api.md`
- `k6-performance-regression-testing.md`
- `performance-regression-testing-workers.md`
- `playwright-mobile-device-emulation.md`
- `lighthouse-ci-integration.md`

## Sources

- k6 documentation — network emulation: https://k6.io/docs/using-k6/scenarios/
- toxiproxy: https://github.com/Shopify/toxiproxy
- Chrome DevTools Network conditions presets: https://developer.chrome.com/docs/devtools/network/reference/#throttling-profile
- k6 Browser module: https://k6.io/docs/using-k6-browser/
