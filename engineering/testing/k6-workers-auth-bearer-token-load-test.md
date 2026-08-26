# k6 Workers Authentication Bearer Token Load Test

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare Workers API protected by JWT bearer tokens needs load testing, but naive k6 scripts either hardcode a static token (which expires mid-test) or fetch a new token on every request (which skews latency measurements and hammers the auth endpoint). The goal is efficient, realistic bearer token management under load without polluting the Workers CPU metrics with token refresh overhead.

## Context

Cloudflare Workers enforce per-request CPU limits (10 ms on the free tier, 30 s on paid). An authentication middleware that verifies a JWT adds CPU cost to every request. Load tests that send expired or invalid tokens trigger 401 branches and never reach business logic. To get a realistic picture of Worker throughput, the token must be valid throughout the test. The strategies below cover: per-VU token acquisition in setup, shared token distribution via a k6 `SharedArray`, and token rotation when expiry is shorter than the test duration.

---

## Strategy 1 — Per-VU token acquisition in `setup()`

Acquire one token per VU before the load phase begins. This keeps auth latency out of request metrics.

```javascript
// k6/workers-auth-bearer.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

export const options = {
  scenarios: {
    authenticated_load: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 50 },
        { duration: '2m', target: 50 },
        { duration: '30s', target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<300'],
    http_req_failed: ['rate<0.01'],
  },
};

// Acquire a pool of tokens once before the test starts
const tokens = new SharedArray('auth_tokens', function () {
  const results = [];
  for (let i = 0; i < 100; i++) {
    const res = http.post(
      'https://auth.example.workers.dev/token',
      JSON.stringify({ client_id: `test-client-${i}`, client_secret: 'secret' }),
      { headers: { 'Content-Type': 'application/json' } }
    );
    if (res.status === 200) {
      results.push(JSON.parse(res.body).access_token);
    }
  }
  return results;
});

export default function () {
  // Each VU picks a token from the pool by its index
  const token = tokens[__VU % tokens.length];

  const res = http.get('https://api.example.workers.dev/protected/data', {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  check(res, {
    'status 200': (r) => r.status === 200,
    'has data field': (r) => JSON.parse(r.body).data !== undefined,
    'response time OK': (r) => r.timings.duration < 300,
  });

  sleep(0.5);
}
```

---

## Strategy 2 — Token rotation with expiry tracking per VU

When token TTL is shorter than the test duration, each VU refreshes its own token before it expires. Rotation calls are tagged separately so they do not pollute the main request SLO.

```javascript
// k6/workers-auth-rotation.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 20,
  duration: '10m',
  thresholds: {
    'http_req_duration{type:api}': ['p(95)<200'],
    'http_req_duration{type:auth}': ['p(99)<500'],
    http_req_failed: ['rate<0.005'],
  },
};

const AUTH_URL = 'https://auth.example.workers.dev/token';
const API_URL = 'https://api.example.workers.dev/protected';
// Refresh 30 seconds before actual expiry to avoid 401 under load
const REFRESH_BUFFER_MS = 30_000;

function acquireToken() {
  const res = http.post(
    AUTH_URL,
    JSON.stringify({
      grant_type: 'client_credentials',
      client_id: `vu-${__VU}`,
      client_secret: <redacted-secret>
    }),
    {
      headers: { 'Content-Type': 'application/json' },
      tags: { type: 'auth' },
    }
  );

  check(res, { 'token acquired': (r) => r.status === 200 });

  const body = JSON.parse(res.body);
  return {
    token: body.access_token,
    expiresAt: Date.now() + body.expires_in * 1000,
  };
}

export default function () {
  // Module-level state per VU (initialised lazily)
  if (!globalThis._auth || Date.now() >= globalThis._auth.expiresAt - REFRESH_BUFFER_MS) {
    globalThis._auth = acquireToken();
  }

  const res = http.get(API_URL, {
    headers: {
      Authorization: `Bearer ${globalThis._auth.token}`,
    },
    tags: { type: 'api' },
  });

  check(res, {
    'status 200': (r) => r.status === 200,
    'no auth error': (r) => r.status !== 401 && r.status !== 403,
  });

  sleep(1);
}
```

---

## Strategy 3 — Verifying the Worker's auth middleware under error conditions

Intentionally send invalid and expired tokens to confirm the Worker returns appropriate HTTP status codes without crashing or leaking data.

```javascript
// k6/workers-auth-negative.js
import http from 'k6/http';
import { check, group } from 'k6';

export const options = {
  vus: 5,
  iterations: 50,
};

const API_URL = 'https://api.example.workers.dev/protected';

export default function () {
  group('missing token', () => {
    const res = http.get(API_URL);
    check(res, { 'rejects with 401': (r) => r.status === 401 });
  });

  group('malformed token', () => {
    const res = http.get(API_URL, {
      headers: { Authorization: 'Bearer not.a.jwt' },
    });
    check(res, { 'rejects with 401': (r) => r.status === 401 });
  });

  group('wrong audience claim', () => {
    // A valid-signature token but wrong `aud` claim
    const wrongAudToken = __ENV.WRONG_AUD_TOKEN;
    const res = http.get(API_URL, {
      headers: { Authorization: `Bearer ${wrongAudToken}` },
    });
    check(res, { 'rejects with 403': (r) => r.status === 403 });
  });

  group('valid token', () => {
    const res = http.get(API_URL, {
      headers: { Authorization: `Bearer ${__ENV.VALID_TOKEN}` },
    });
    check(res, { 'accepts with 200': (r) => r.status === 200 });
  });
}
```

---

## Strategy 4 — Grafana Cloud k6 environment variable passing for secrets

Never hard-code tokens in k6 scripts. Pass them as environment variables at runtime.

```bash
# Local run — export secret before invoking k6
export CLIENT_SECRET="$(op read 'op://vault/workers-test/client-secret')"
export VALID_TOKEN="$(node scripts/mint-test-token.js)"
export WRONG_AUD_TOKEN="$(node scripts/mint-wrong-aud-token.js)"

k6 run \
  --env CLIENT_SECRET="$CLIENT_SECRET" \
  --env VALID_TOKEN="$VALID_TOKEN" \
  --env WRONG_AUD_TOKEN="$WRONG_AUD_TOKEN" \
  k6/workers-auth-bearer.js

# CI (GitHub Actions)
# Add CLIENT_SECRET to repository secrets, then:
# k6 run --env CLIENT_SECRET=${{ secrets.K6_CLIENT_SECRET }} ...
```

---

## Strategy 5 — Correlating auth cost with Workers Analytics Engine

Tag token refresh requests separately and query Cloudflare Analytics Engine to confirm auth middleware CPU usage.

```typescript
// workers/src/auth-middleware.ts — instrument with Analytics Engine
export async function verifyBearerToken(
  request: Request,
  env: Env
): Promise<{ valid: boolean; sub?: string }> {
  const start = Date.now();
  const authHeader = request.headers.get('Authorization');

  if (!authHeader?.startsWith('Bearer ')) {
    env.ANALYTICS.writeDataPoint({
      blobs: ['auth', 'missing_token'],
      doubles: [0],
      indexes: ['auth_result'],
    });
    return { valid: false };
  }

  const token = authHeader.slice(7);
  try {
    const payload = await verifyJWT(token, env.JWT_PUBLIC_KEY);
    env.ANALYTICS.writeDataPoint({
      blobs: ['auth', 'success', payload.sub],
      doubles: [Date.now() - start],
      indexes: ['auth_result'],
    });
    return { valid: true, sub: payload.sub };
  } catch {
    env.ANALYTICS.writeDataPoint({
      blobs: ['auth', 'invalid_token'],
      doubles: [Date.now() - start],
      indexes: ['auth_result'],
    });
    return { valid: false };
  }
}
```

---

## Anti-patterns

- Using a single hardcoded token shared across all VUs — if it expires during the test, 100% of requests fail at once, producing a misleading cliff in the latency graph.
- Acquiring a new token on every request iteration — inflates request count metrics and introduces auth latency into p95/p99 API measurements.
- Setting `thresholds` only on `http_req_duration` without tagging — auth calls and API calls get averaged together, hiding regressions in either.
- Running negative tests (invalid token scenarios) with the same VU pool as the happy-path load — skews failure rate thresholds.
- Storing the client secret in the k6 script source — secrets in version control expose credentials to all repo contributors.

---

## Gotchas

- `SharedArray` is evaluated in the init context (once, before VUs start). HTTP calls inside it count against the total test setup time but do not appear in scenario metrics. Monitor token pool build time separately.
- `globalThis` in k6 is per-VU; data stored there does not leak between VUs. It is the correct place for per-VU token state.
- Cloudflare Workers may rate-limit requests to the `/token` endpoint itself. Pre-warm the token pool with delays if you hit 429s during setup.
- k6 does not automatically retry on 401. If a token expires unexpectedly and the Worker returns 401, the check fails silently unless `http_req_failed` is tracked.
- The `tags` option on `http.get` / `http.post` must be set at the call site — you cannot add tags after the fact. Structure scripts with tagging from the start.

---

## Verification

```bash
# Confirm no 401s appear in a 1-minute smoke test
k6 run --vus 2 --duration 1m \
  --env CLIENT_SECRET="$CLIENT_SECRET" \
  --summary-trend-stats='avg,p(95),p(99)' \
  k6/workers-auth-bearer.js

# Check that auth calls are correctly tagged in the output
# Look for http_req_duration{type:auth} and http_req_duration{type:api} in summary

# Negative test pass — all checks should report 100%
k6 run --vus 1 --iterations 20 \
  --env VALID_TOKEN="$VALID_TOKEN" \
  --env WRONG_AUD_TOKEN="$WRONG_AUD_TOKEN" \
  k6/workers-auth-negative.js
```

---

## Related

- `k6-load-testing-cloudflare-workers-api.md` — general Workers API load testing
- `k6-performance-regression-testing.md` — integrating k6 into CI gates
- `auth-flow-testing-strategy.md` — authentication testing strategy overview
- `rate-limit-testing-strategies.md` — testing the rate limiter that protects the auth endpoint
- `grafana-k6-cloud-workers-stress-test.md` — running k6 at scale on Grafana Cloud

---

## Sources

- https://k6.io/docs/javascript-api/k6-data/sharedarray/
- https://k6.io/docs/using-k6/tags-and-groups/
- https://k6.io/docs/using-k6/environment-variables/
- https://developers.cloudflare.com/workers/runtime-apis/handlers/fetch/
- https://developers.cloudflare.com/analytics/analytics-engine/
