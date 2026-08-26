# chaos-engineering-cloudflare-workers

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

The example project Workers API passes all unit and integration tests but
occasionally degrades in production when upstream KV reads slow down,
D1 becomes temporarily unavailable, or Cloudflare edge routes a request
to a region where a binding is cold. Mobile clients on 3G networks
compound the problem: a single 500 ms latency spike on the Worker
causes the client-side timeout to trip, leaving the user staring at a
spinner. There is no systematic process for verifying that the Workers
handle these failure modes gracefully before they reach users.

## Context

Chaos engineering for Cloudflare Workers differs from Kubernetes-based
chaos because Workers run in a sandboxed V8 isolate without a writable
filesystem, network-level proxies, or sidecar containers. Fault
injection must happen at the application layer — either inside the
Worker code as a configurable middleware, or via a thin chaos proxy
Worker that sits in front of the real Worker during test runs.

Three fault categories matter for Workers:

| Category | Examples | Injection point |
|----------|----------|-----------------|
| Latency | Slow KV reads, D1 round-trips, upstream fetch | Middleware / proxy Worker |
| Errors | 500 responses, binding throws, JSON parse failures | Middleware / binding mock |
| Dropped requests | Timeout before response, connection abort | Proxy Worker with `waitUntil` race |

The chaos configuration is stored in a KV namespace
(`CHAOS_CONFIG`) that the middleware reads on every request.
A GitHub Actions job toggles faults on and off around a
k6 load test to validate the system's resilience posture.

## Project Structure

```
workers/
  api/
    src/
      middleware/
        chaos.ts          # fault-injection middleware
      index.ts
  chaos-proxy/
    src/
      index.ts            # standalone chaos proxy Worker
scripts/
  k6/
    chaos-resilience.js   # k6 scenario that runs during faults
.github/
  workflows/
    chaos.yml             # GitHub Actions chaos experiment
```

## Fault Injection Middleware

The middleware reads a chaos config from KV, then applies the
configured fault before passing the request to the next handler.
The KV key is `chaos:config` and holds a JSON document.

```ts
// workers/api/src/middleware/chaos.ts

export interface ChaosConfig {
  enabled: boolean;
  latencyMs?: number;          // artificial delay added to every request
  errorRate?: number;          // 0–1 fraction of requests that return 500
  dropRate?: number;           // 0–1 fraction that never respond (timeout sim)
  errorBody?: string;          // custom error body for injected errors
}

const DEFAULT: ChaosConfig = { enabled: false };

async function readChaosConfig(
  kv: KVNamespace
): Promise<ChaosConfig> {
  try {
    const raw = await kv.get('chaos:config');
    if (!raw) return DEFAULT;
    return JSON.parse(raw) as ChaosConfig;
  } catch {
    return DEFAULT;
  }
}

export function chaosMiddleware(kv: KVNamespace) {
  return async (
    request: Request,
    next: () => Promise<Response>
  ): Promise<Response> => {
    const cfg = await readChaosConfig(kv);

    if (!cfg.enabled) return next();

    // Latency injection
    if (cfg.latencyMs && cfg.latencyMs > 0) {
      await new Promise((r) => setTimeout(r, cfg.latencyMs));
    }

    // Dropped-request simulation: race the real handler against
    // a never-resolving promise; we resolve the race after 30 s
    // to avoid Workers CPU limit exhaustion.
    if (cfg.dropRate && Math.random() < cfg.dropRate) {
      await new Promise((r) => setTimeout(r, 30_000));
      return new Response('Gateway Timeout', { status: 504 });
    }

    // Error injection
    if (cfg.errorRate && Math.random() < cfg.errorRate) {
      return new Response(
        cfg.errorBody ?? JSON.stringify({ error: 'chaos injected fault' }),
        {
          status: 500,
          headers: { 'content-type': 'application/json',
                     'x-chaos-fault': 'injected' },
        }
      );
    }

    return next();
  };
}
```

Wire the middleware in the main handler:

```ts
// workers/api/src/index.ts (excerpt)
import { chaosMiddleware } from './middleware/chaos.js';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const chaos = chaosMiddleware(env.CHAOS_CONFIG);
    return chaos(request, () => router.handle(request, env));
  },
};
```

## Standalone Chaos Proxy Worker

For environments where modifying the Worker under test is undesirable
(e.g., a third-party or separately deployed Worker), deploy a thin
proxy in front of the real Worker:

```ts
// workers/chaos-proxy/src/index.ts

const UPSTREAM = 'https://api.example project.workers.dev';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const raw  = await env.CHAOS_CONFIG.get('chaos:config');
    const cfg  = raw ? JSON.parse(raw) : { enabled: false };

    if (!cfg.enabled) {
      return fetch(new Request(
        request.url.replace(new URL(request.url).origin, UPSTREAM),
        request
      ));
    }

    if (cfg.latencyMs) {
      await new Promise((r) => setTimeout(r, cfg.latencyMs));
    }

    if (cfg.errorRate && Math.random() < cfg.errorRate) {
      return new Response(
        JSON.stringify({ error: 'proxy chaos fault' }),
        { status: 500, headers: { 'content-type': 'application/json' } }
      );
    }

    const upstream = new Request(
      request.url.replace(new URL(request.url).origin, UPSTREAM),
      request
    );
    return fetch(upstream);
  },
};
```

## Chaos Config Management

Toggle faults on and off via `wrangler kv key put`:

```bash
# Enable 200 ms latency for all requests (10% error rate)
wrangler kv key put \
  --namespace-id "$CHAOS_KV_ID" \
  chaos:config \
  '{"enabled":true,"latencyMs":200,"errorRate":0.10}'

# Enable drop/timeout simulation (5% of requests)
wrangler kv key put \
  --namespace-id "$CHAOS_KV_ID" \
  chaos:config \
  '{"enabled":true,"dropRate":0.05}'

# Disable all chaos
wrangler kv key put \
  --namespace-id "$CHAOS_KV_ID" \
  chaos:config \
  '{"enabled":false}'
```

## Mobile Resilience Validation

Mobile clients are especially sensitive to latency spikes.
The k6 chaos scenario runs while faults are active and
asserts that the mobile error rate stays within budget:

```js
// scripts/k6/chaos-resilience.js
import http             from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend }  from 'k6/metrics';

const mobileErrors   = new Rate('mobile_errors');
const mobileDuration = new Trend('mobile_p99', true);
const BASE = __ENV.WORKER_URL || 'https://staging.example project.workers.dev';

export const options = {
  scenarios: {
    mobile_chaos: {
      executor: 'constant-vus',
      vus:      20,
      duration: '2m',
      env: { DEVICE: 'mobile' },
    },
  },
  thresholds: {
    // Mobile must tolerate up to 200ms injected latency
    // and still stay under a 1 s p99 budget
    mobile_p99:    ['p(99)<1000'],
    mobile_errors: ['rate<0.15'],   // up to 10% injected + 5% budget
  },
};

export default function () {
  const ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) '
           + 'AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1';

  const res = http.get(`${BASE}/api/events`, {
    headers: { 'User-Agent': ua },
    timeout: '5s',              // strict mobile timeout
  });

  mobileErrors.add(res.status >= 500);
  mobileDuration.add(res.timings.duration);

  check(res, {
    'acceptable status': (r) => r.status === 200 || r.status === 429,
    'not chaos-injected error': (r) =>
      r.headers['x-chaos-fault'] === undefined || r.status === 200,
  });

  sleep(0.5);
}
```

## GitHub Actions Chaos Experiment

```yaml
# .github/workflows/chaos.yml
name: Chaos experiment — Workers latency + error fault
on:
  schedule:
    - cron: '0 3 * * 2'   # every Tuesday at 03:00 UTC
  workflow_dispatch:

jobs:
  chaos:
    runs-on: ubuntu-latest
    env:
      CHAOS_KV_ID: ${{ vars.CHAOS_KV_NAMESPACE_ID }}
      WORKER_URL:  ${{ vars.STAGING_WORKER_URL }}
      CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      CF_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}

    steps:
      - uses: actions/checkout@v4

      - name: Install k6
        run: |
          sudo gpg --dearmor -o /usr/share/keyrings/k6.gpg \
            < <(curl -sfL https://dl.k6.io/key.gpg)
          echo "deb [signed-by=/usr/share/keyrings/k6.gpg] \
            https://dl.k6.io/deb stable main" \
            | sudo tee /etc/apt/sources.list.d/k6.list
          sudo apt-get update && sudo apt-get install -y k6

      - name: Install wrangler
        run: npm install -g wrangler

      - name: Baseline (no fault)
        run: |
          k6 run --summary-export=results/baseline.json \
            scripts/k6/chaos-resilience.js

      - name: Inject latency + error fault
        run: |
          wrangler kv key put \
            --namespace-id "$CHAOS_KV_ID" \
            chaos:config \
            '{"enabled":true,"latencyMs":200,"errorRate":0.10}'

      - name: Run k6 under fault
        run: |
          k6 run --summary-export=results/under-fault.json \
            --env WORKER_URL="$WORKER_URL" \
            scripts/k6/chaos-resilience.js

      - name: Disable fault
        if: always()
        run: |
          wrangler kv key put \
            --namespace-id "$CHAOS_KV_ID" \
            chaos:config \
            '{"enabled":false}'

      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: chaos-results-${{ github.sha }}
          path: results/
```

## Fault Scenario Reference

| Scenario | Config | Mobile budget | Desktop budget |
|----------|--------|---------------|----------------|
| Baseline | `enabled:false` | p99 < 400 ms | p99 < 150 ms |
| Latency +200 ms | `latencyMs:200` | p99 < 1000 ms | p99 < 500 ms |
| 10% error injection | `errorRate:0.10` | error rate < 15% | error rate < 12% |
| 5% drop/timeout | `dropRate:0.05` | error rate < 10% | error rate < 8% |
| Combined stress | `latencyMs:150,errorRate:0.05` | p99 < 800 ms | p99 < 350 ms |

## Anti-patterns

- Reading `chaos:config` inside a `waitUntil` callback — the chaos
  check must happen synchronously in the request path to be effective.
- Using a fixed `Math.random() < rate` check without seeding — the
  rate is stochastic across requests, not guaranteed per test run. Use
  a counter in Durable Objects when deterministic fault-per-N behavior
  is required.
- Leaving chaos enabled after a test run — a stale KV value will
  cause real user traffic to receive injected errors. Always disable
  in a CI `if: always()` step.
- Injecting a 30-second sleep to simulate a dropped request — Workers
  have a 30-second CPU time limit; a genuine timeout simulation must
  use `waitUntil` carefully and is better tested at the proxy layer.
- Running chaos experiments against the production KV namespace —
  always use a separate `CHAOS_CONFIG` namespace bound only to staging
  Workers.

## Gotchas

- Workers CPU time is paused during `await` — a `setTimeout` for
  latency injection consumes wall-clock time but not CPU time. The
  Worker will not be killed by the CPU limit during the sleep, but it
  will be killed by the 30-second wall-clock request timeout.
- KV reads add ~5–10 ms of real latency in addition to the injected
  latency. Account for this in threshold budgets.
- The `x-chaos-fault: injected` response header makes it possible for
  the k6 script and the mobile client to distinguish injected errors
  from real Worker failures during experiment analysis.
- Mobile clients that implement retry-with-backoff may mask injected
  error rates in the k6 output — measure at the individual request
  level, not the retry attempt level.

## Verification

```bash
# Confirm chaos config is active
wrangler kv key get \
  --namespace-id "$CHAOS_KV_ID" \
  chaos:config

# Spot-check that injected header appears
curl -si https://staging.example project.workers.dev/api/events \
  | grep -i 'x-chaos'

# Confirm p99 from results
jq '.metrics.mobile_p99.values["p(99)"]' results/under-fault.json
```

## Related

- `testing/chaos-engineering-fault-injection.md`
- `testing/k6-load-testing-cloudflare-workers-api.md`
- `testing/k6-performance-regression-testing.md`
- `testing/kv-testing-miniflare.md`
- `testing/resilience-circuit-breaker-testing.md`

## Source URLs (verified 2026-08-22)

- https://developers.cloudflare.com/workers/runtime-apis/bindings/kv/
- https://developers.cloudflare.com/workers/configuration/limits/
- https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-vus/
- https://principlesofchaos.org/
