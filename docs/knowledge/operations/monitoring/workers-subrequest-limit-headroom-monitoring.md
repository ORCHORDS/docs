# Workers Subrequest Limit Headroom Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Cloudflare Worker on the paid plan can make up to 1 000 subrequests per invocation
(50 on the free plan). Workers that fan out to many upstream services, perform parallel
KV reads, or issue multiple D1 queries per request can silently approach this ceiling.
When the limit is hit, subsequent `fetch()` / KV / D1 calls throw, but there is no
native metric showing how close individual requests came. Without headroom monitoring
you only learn about the ceiling when requests start failing in production.

## Context

Every outbound `fetch()`, KV read/write, R2 operation, D1 query, and Queue send counts
as a subrequest. The limit is per-invocation (not per-Worker-instance). A request that
fires 40 parallel KV reads, 10 D1 queries, and 5 downstream API calls is at 55
subrequests — comfortably under 1 000 but already over the free-plan limit.

Because the runtime does not expose a subrequest counter directly, the pattern is to
wrap your fetch/storage calls in a lightweight counter that you read at request end and
write to Analytics Engine. This turns an invisible runtime limit into a trackable SLI.

## Subrequest Counter Wrapper

```typescript
// subrequest-counter.ts
export class SubrequestCounter {
  private count = 0;
  private readonly limit: number;

  constructor(limit = 1_000) {
    this.limit = limit;
  }

  track<T>(promise: Promise<T>): Promise<T> {
    this.count++;
    return promise;
  }

  get current(): number {
    return this.count;
  }

  get headroom(): number {
    return this.limit - this.count;
  }

  get utilizationRate(): number {
    return this.count / this.limit;
  }
}

// Usage: attach one counter per request invocation
export function makeCounter(plan: "free" | "paid" = "paid"): SubrequestCounter {
  return new SubrequestCounter(plan === "free" ? 50 : 1_000);
}
```

## Integrating the Counter into Request Context

```typescript
// worker.ts
interface RequestContext {
  counter: SubrequestCounter;
  requestId: string;
  route: string;
}

async function handleRequest(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const counter = makeCounter("paid");
  const requestId = crypto.randomUUID();
  const route = new URL(request.url).pathname;

  const rctx: RequestContext = { counter, requestId, route };

  let response: Response;
  try {
    response = await routeRequest(request, env, rctx);
  } finally {
    // Always emit — even on error — so we capture worst-case paths
    ctx.waitUntil(
      emitSubrequestMetric(env, {
        requestId,
        route,
        subrequestCount: counter.current,
        utilizationRate: counter.utilizationRate,
        headroom: counter.headroom,
      })
    );
  }

  return response;
}
```

## Emitting Metrics to Analytics Engine

```typescript
// subrequest-metrics.ts
interface SubrequestMetric {
  requestId: string;
  route: string;
  subrequestCount: number;
  utilizationRate: number;
  headroom: number;
}

export async function emitSubrequestMetric(
  env: Env,
  metric: SubrequestMetric
): Promise<void> {
  env.ANALYTICS.writeDataPoint({
    blobs: [metric.requestId, metric.route, "subrequest_usage", ""],
    doubles: [
      metric.subrequestCount,
      metric.utilizationRate,
      metric.headroom,
    ],
    indexes: [metric.route],
  });
}
```

## Wrapped KV and D1 Helpers

```typescript
// tracked-storage.ts
export function kvGet(
  kv: KVNamespace,
  counter: SubrequestCounter,
  key: string,
  options?: KVNamespaceGetOptions<undefined>
): Promise<string | null> {
  return counter.track(kv.get(key, options));
}

export function kvPut(
  kv: KVNamespace,
  counter: SubrequestCounter,
  key: string,
  value: string,
  options?: KVNamespacePutOptions
): Promise<void> {
  return counter.track(kv.put(key, value, options));
}

export function d1Run(
  db: D1Database,
  counter: SubrequestCounter,
  stmt: D1PreparedStatement
): Promise<D1Result> {
  return counter.track(stmt.run());
}

export function d1Query<T = unknown>(
  db: D1Database,
  counter: SubrequestCounter,
  stmt: D1PreparedStatement
): Promise<D1Result<T>> {
  return counter.track(stmt.all<T>());
}

export function trackedFetch(
  counter: SubrequestCounter,
  input: RequestInfo,
  init?: RequestInit
): Promise<Response> {
  return counter.track(fetch(input, init));
}
```

## Querying High-Utilization Routes

```typescript
// headroom-query.ts
export async function fetchHighUtilizationRoutes(
  env: Env,
  thresholdRate = 0.5,
  windowHours = 24
): Promise<Array<{ route: string; p95Utilization: number; maxCount: number }>> {
  const query = `
    SELECT
      blob2 AS route,
      quantileExact(0.95)(double2) AS p95_utilization,
      MAX(double1) AS max_count
    FROM subrequest_metrics
    WHERE timestamp > NOW() - INTERVAL '${windowHours}' HOUR
      AND blob3 = 'subrequest_usage'
    GROUP BY route
    HAVING p95_utilization > ${thresholdRate}
    ORDER BY p95_utilization DESC
    LIMIT 20
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    }
  );

  const { data } = await resp.json<{
    data: Array<{ route: string; p95_utilization: number; max_count: number }>;
  }>();

  return data.map((r) => ({
    route: r.route,
    p95Utilization: r.p95_utilization,
    maxCount: r.max_count,
  }));
}
```

## Anti-patterns

- Counting subrequests only on the happy path — error branches often include retry
  fetches that push the total higher; always emit in a `finally` block.
- Tracking only `fetch()` calls and ignoring KV, R2, D1, and Queue operations — every
  binding call counts against the limit; omitting them gives a false low reading.
- Using the counter to enforce a soft limit inside the Worker — throwing early to
  "save" headroom adds latency on every call; use the counter only for observability
  and redesign the request fan-out architecture instead.
- Emitting a metric per subrequest rather than per request — this floods Analytics
  Engine; emit once per invocation with the final total.

## Gotchas

- `ctx.waitUntil` is required for metric emission — if you `await` it inside the
  request handler it adds to wall-clock latency, and if you forget it entirely the
  metric may be dropped when the Worker isolate is evicted.
- The runtime does not throw a descriptive error when the limit is hit — the `fetch()`
  or KV call simply rejects with a generic `Too many subrequests` error; the counter
  lets you know in advance.
- `cache.match()` and `cache.put()` also count as subrequests; if you use the Cache
  API extensively, include wrapper functions for those too.
- `quantileExact` in Analytics Engine SQL is an approximation function with ClickHouse
  semantics; for very low-traffic routes the p95 may not be statistically meaningful —
  filter by a minimum request count.

## Verification

```bash
# Routes with highest p95 subrequest utilization in the last 24 hours
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"query":"SELECT blob2 AS route, quantileExact(0.95)(double2) AS p95_util, MAX(double1) AS max_count FROM subrequest_metrics WHERE timestamp > NOW() - INTERVAL 24 HOUR GROUP BY route ORDER BY p95_util DESC LIMIT 10"}' \
  | jq '.data'

# Any requests that hit over 800 subrequests (80% of paid limit)
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"query":"SELECT blob2 AS route, blob1 AS request_id, double1 AS count FROM subrequest_metrics WHERE double1 > 800 AND timestamp > NOW() - INTERVAL 24 HOUR ORDER BY count DESC LIMIT 20"}' \
  | jq '.data'
```

## Related

- `workers-cpu-time-percentile-analytics-engine.md`
- `worker-cpu-monitoring.md`
- `cloudflare-queues-async-tracing.md`
- `distributed-tracing-workers-d1-requests.md`
- `workers-subrequest-waterfall-tail.md`

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#subrequests
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
