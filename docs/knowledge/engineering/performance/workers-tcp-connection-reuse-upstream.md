# TCP Connection Reuse for Upstream Fetches in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker acting as an API gateway makes multiple `fetch()` calls to the same upstream service (e.g., an internal REST API, a third-party data provider, or a Cloudflare service endpoint) during a single request lifecycle. Profiling via `wrangler tail` shows that subrequest latency includes 20-80 ms of connection establishment overhead per call — TLS handshake + TCP setup — even though all calls go to the same host.

Goal: measure the connection overhead, understand how Workers handle connection pooling, and apply patterns that maximise connection reuse to reduce subrequest latency.

---

## Context

Cloudflare Workers run in a V8 isolate per data centre. Each isolate maintains its own connection pool to upstream hosts. The key facts:

- **Within a single request** (a single `fetch` event): the Workers runtime reuses open TCP/TLS connections to the same `(host, port, protocol)` tuple across multiple `fetch()` calls. No special options are needed.
- **Across requests / isolates**: connections are pooled at the data-centre level and shared across isolates serving traffic on the same Cloudflare PoP. The pool is managed by the runtime; workers cannot configure pool size.
- **Cold isolate**: when a Worker isolate starts for the first time (cold start), the first `fetch()` to an external host pays full TCP + TLS setup. Subsequent calls in the same request or the same isolate's lifetime reuse the connection.
- **`keepalive`** fetch option (available since compatibility date 2023-03-01): hints to the runtime to keep the connection alive beyond the current request, improving reuse probability for the *next* request handled by the same isolate.

---

## Measuring Connection Overhead

```typescript
// src/handlers/benchmark-upstream.ts
import type { Env } from '../types';

interface TimedFetch {
  url: string;
  status: number;
  durationMs: number;
  isWarm: boolean;
}

/**
 * Fetch the same upstream URL twice and compare latencies.
 * The first call may include connection setup; the second reuses the connection.
 */
export async function benchmarkUpstream(
  request: Request,
  env: Env,
): Promise<Response> {
  const upstreamUrl = env.UPSTREAM_API_URL; // e.g. https://api.internal.example.com/health

  const results: TimedFetch[] = [];

  for (let i = 0; i < 3; i++) {
    const t0 = performance.now();

    const res = await fetch(upstreamUrl, {
      method: 'GET',
      headers: { 'X-Benchmark-Call': String(i + 1) },
      // keepalive: true, // uncomment to compare warm-connection behaviour
    });

    // Drain body to allow connection return to pool
    await res.arrayBuffer();

    const durationMs = performance.now() - t0;
    results.push({ url: upstreamUrl, status: res.status, durationMs, isWarm: i > 0 });
  }

  return Response.json({
    note: 'Call 0 = cold, calls 1+ = warm (same request, connection reused)',
    results,
  });
}
```

Typical output on a Worker with a cold isolate:

```json
{
  "results": [
    { "durationMs": 87.4, "isWarm": false },
    { "durationMs": 12.1, "isWarm": true },
    { "durationMs": 11.8, "isWarm": true }
  ]
}
```

The first call pays ~75 ms of TCP + TLS overhead. Subsequent calls in the same request reuse the connection and cost ~12 ms (only the HTTP request/response exchange).

---

## Parallel Subrequests to Avoid Serial Connection Costs

If all upstream calls are independent, fire them in parallel with `Promise.all`. This amortises connection setup: the first call establishes the connection, and subsequent calls — if the pool is already warm — reuse it. But even if each gets its own connection, they run concurrently and total wall-clock time equals the slowest, not the sum.

```typescript
// src/handlers/parallel-upstream.ts
import type { Env } from '../types';

interface ApiData {
  user: unknown;
  catalog: unknown;
  flags: unknown;
}

/**
 * Fetch three independent upstream resources in parallel.
 * Total latency ≈ max(individual) rather than sum(individual).
 */
export async function fetchUpstreamInParallel(
  userId: string,
  env: Env,
): Promise<ApiData> {
  const base = env.UPSTREAM_API_URL;

  const commonHeaders = {
    Authorization: `Bearer ${env.UPSTREAM_API_TOKEN}`,
    'Content-Type': 'application/json',
  };

  const [userRes, catalogRes, flagsRes] = await Promise.all([
    fetch(`${base}/users/${userId}`, { headers: commonHeaders }),
    fetch(`${base}/catalog/featured`, { headers: commonHeaders }),
    fetch(`${base}/feature-flags`, { headers: commonHeaders }),
  ]);

  // Parse all responses in parallel as well
  const [user, catalog, flags] = await Promise.all([
    userRes.json(),
    catalogRes.json(),
    flagsRes.json(),
  ]);

  return { user, catalog, flags };
}
```

---

## Using `keepalive` to Warm the Next Request

```typescript
// src/middleware/keepalive-fetch.ts

/**
 * Drop-in replacement for fetch() that sets keepalive on all requests,
 * improving the chance that the TCP connection is reused by the next
 * request handled by the same isolate.
 *
 * Use this for high-frequency subrequests to a stable upstream host.
 */
export function keepaliveFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  return fetch(input, {
    ...init,
    // keepalive instructs the runtime to hold the connection open
    // after this request completes, ready for the next one.
    // @ts-expect-error — CF Workers extend the standard RequestInit
    keepalive: true,
  });
}

// Usage:
// import { keepaliveFetch } from '../middleware/keepalive-fetch';
// const res = await keepaliveFetch(env.UPSTREAM_API_URL + '/data');
```

---

## Connection Warmth Classification Helper

```typescript
// src/lib/connection-timing.ts

export interface ConnectionTiming {
  totalMs: number;
  /** Heuristic: if < 20 ms, the connection was almost certainly reused */
  likelyCold: boolean;
  likelyWarm: boolean;
}

/**
 * Time a fetch call and classify whether the connection was likely warm.
 *
 * Cloudflare Workers do not expose the Fetch Timing API (connectTime, tlsTime,
 * etc.) directly. This heuristic uses total response time as a proxy:
 *   - < 20 ms  → warm (connection reused, no TCP/TLS overhead)
 *   - 20-50 ms → ambiguous (could be fast cold or slow warm)
 *   - > 50 ms  → cold (connection establishment overhead visible)
 */
export async function timedFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<{ response: Response; timing: ConnectionTiming }> {
  const t0 = performance.now();
  const response = await fetch(input, init);
  const totalMs = performance.now() - t0;

  return {
    response,
    timing: {
      totalMs,
      likelyCold: totalMs > 50,
      likelyWarm: totalMs < 20,
    },
  };
}

// Example usage in a handler:
// const { response, timing } = await timedFetch(env.UPSTREAM_URL + '/api/data');
// console.log(`Upstream fetch: ${timing.totalMs.toFixed(1)} ms, likely warm: ${timing.likelyWarm}`);
```

---

## Logging Connection Metrics

```typescript
// src/middleware/connection-metrics.ts
import { timedFetch } from '../lib/connection-timing';
import type { Env } from '../types';

/**
 * Wrap the main upstream call with timing metrics pushed to Analytics Engine.
 */
export async function fetchWithMetrics(
  url: string,
  env: Env,
  label: string,
): Promise<Response> {
  const { response, timing } = await timedFetch(url, {
    headers: { Authorization: `Bearer ${env.UPSTREAM_API_TOKEN}` },
  });

  // Non-blocking telemetry
  env.ANALYTICS.writeDataPoint({
    blobs: [label, timing.likelyWarm ? 'warm' : 'cold', url],
    doubles: [timing.totalMs, response.status],
    indexes: [label],
  });

  return response;
}
```

---

## wrangler.toml

```toml
name = "api-gateway"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "upstream_connection_metrics"

[vars]
UPSTREAM_API_URL = "https://api.internal.example.com"

# UPSTREAM_API_TOKEN — set via: npx wrangler secret put UPSTREAM_API_TOKEN
```

---

## Anti-patterns

- **Sequential independent fetches**: `await fetch(a); await fetch(b)` serialises what could be parallel. Always use `Promise.all` for independent subrequests.
- **Not draining the response body**: if you call `fetch()` but do not consume the body (`.json()`, `.text()`, `.arrayBuffer()`), the connection cannot be returned to the pool. Always consume or cancel (`response.body?.cancel()`) the body.
- **Assuming keepalive crosses isolate boundaries**: `keepalive` improves reuse within the *same isolate*. If a request lands on a different isolate (e.g., after a code deploy), the connection pool starts fresh.
- **Creating a new `Request` object per call with `cache: 'no-store'`**: this bypasses Cloudflare's edge cache but also prevents connection reuse optimisations at the HTTP/2 layer. Use the URL string directly for simple GETs.
- **Measuring latency without draining the body first**: `performance.now()` after `await fetch(url)` only measures time to first byte (TTFB), not total transfer. Await body consumption before stopping the timer if you want end-to-end latency.

---

## Gotchas

- Workers have a **subrequest limit** of 1000 per request on the paid plan (50 on free). Batching and parallel strategies both count toward this limit; they reduce *latency*, not *count*.
- **HTTP/2 multiplexing**: if the upstream supports HTTP/2, multiple parallel `fetch()` calls to the same host share a single TCP connection automatically via multiplexing — no special configuration needed.
- `performance.now()` in Workers is not high-resolution by default (clamped to 0.5 ms on some isolate versions). For submillisecond benchmarking, use `Date.now()` difference or the Tail Workers API.
- The Workers runtime does not expose raw TCP socket APIs. Connection reuse is entirely managed by the runtime; you cannot force a new connection or inspect socket state.
- **Egress from R2 to Workers is free** within the same Cloudflare account; egress from Workers to external upstreams incurs standard egress fees on high-volume deployments.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Hit the benchmark endpoint
curl -s "https://my-worker.workers.dev/benchmark-upstream" | jq '.results[] | {durationMs, isWarm}'

# Watch real-time timing in Wrangler tail
npx wrangler tail --format pretty | grep -E 'Upstream fetch|warm'

# Query Analytics Engine for warm vs cold ratio
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT blob2 AS connection_state, count() AS n, avg(double1) AS avg_ms FROM upstream_connection_metrics WHERE timestamp >= now() - INTERVAL 10 MINUTE GROUP BY blob2"
  }'
```

---

## Related

- `workers-d1-query-batch-reduce-roundtrips.md` — reducing D1 subrequest count
- `workers-speculative-prefetch-kv.md` — avoiding upstream calls entirely for hot data
- [Cloudflare Workers Subrequests](https://developers.cloudflare.com/workers/platform/limits/#subrequests)
- [Workers Fetch API](https://developers.cloudflare.com/workers/runtime-apis/fetch/)

---

## Sources

- Workers Fetch API — https://developers.cloudflare.com/workers/runtime-apis/fetch/
- Workers Platform Limits — https://developers.cloudflare.com/workers/platform/limits/
- TCP keepalive in Workers — https://developers.cloudflare.com/workers/runtime-apis/fetch/#requestinit
- Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
