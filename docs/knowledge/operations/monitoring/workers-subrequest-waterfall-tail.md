# Workers Subrequest Waterfall Analysis via Tail Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Workers request that fans out to multiple upstream APIs, KV reads, D1 queries, and R2 fetches has a slow tail that is impossible to diagnose from request-level p99 alone. You need a per-request waterfall showing which subrequest(s) dominated total latency, captured passively without modifying every call site.

## Context

Tail Workers receive a `TraceItem` for every completed Worker invocation. Each `TraceItem` includes a `fetchSubrequests` array with the URL, method, status, and timing for every `fetch()` made during the invocation. By parsing this in the Tail Worker and writing per-subrequest spans to Analytics Engine, you build a queryable waterfall without adding instrumentation to the Worker under observation.

## 1. Tail Worker Extracts Subrequest Spans

```typescript
// src/waterfall-tail.ts
export interface TailEnv {
  SUBREQUEST_SPANS: AnalyticsEngineDataset;
}

function classifyHost(url: string): string {
  try {
    const host = new URL(url).hostname;
    if (host.endsWith("workers.dev") || host.endsWith("cloudflare.com")) return "cloudflare";
    if (host.endsWith("amazonaws.com")) return "aws";
    return host.split(".").slice(-2).join(".");
  } catch {
    return "unknown";
  }
}

export default {
  async tail(events: TraceItem[], env: TailEnv): Promise<void> {
    for (const event of events) {
      const requestId =
        (event.event as FetchEventInfo | null)?.request?.headers?.["x-request-id"] ??
        crypto.randomUUID();

      const subrequests =
        (event as unknown as { fetchSubrequests?: SubrequestSample[] }).fetchSubrequests ?? [];

      for (const sub of subrequests) {
        const durationMs =
          sub.timing != null
            ? sub.timing.responseEnd - sub.timing.requestStart
            : -1;

        env.SUBREQUEST_SPANS.writeDataPoint({
          blobs: [
            requestId,
            sub.url ?? "unknown",
            classifyHost(sub.url ?? ""),
            String(sub.status ?? 0),
            sub.method ?? "GET",
          ],
          doubles: [durationMs, event.wallTimeMs ?? 0],
          indexes: [classifyHost(sub.url ?? "")],
        });
      }
    }
  },
} satisfies ExportedHandler<TailEnv>;

// Type helpers (not exported by @cloudflare/workers-types in all versions)
interface SubrequestSample {
  url?: string;
  method?: string;
  status?: number;
  timing?: { requestStart: number; responseEnd: number };
}

interface FetchEventInfo {
  request: { headers: Record<string, string> };
}
```

## 2. wrangler.toml for the Tail Worker

```toml
name = "subrequest-waterfall-tail"
main = "src/waterfall-tail.ts"
compatibility_date = "2024-09-23"

[[analytics_engine_datasets]]
binding = "SUBREQUEST_SPANS"
dataset = "subrequest_waterfall"

# In the observed Worker's wrangler.toml:
# [tail_consumers]
# service = "subrequest-waterfall-tail"
```

## 3. Propagate a Request ID from the Observed Worker

```typescript
// src/observed-worker.ts (add request-id header)
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const requestId = request.headers.get("x-request-id") ?? crypto.randomUUID();

    // All downstream fetches automatically appear in the Tail Worker's
    // fetchSubrequests array — no manual instrumentation needed
    const [apiResp, kvValue] = await Promise.all([
      fetch("https://api.example.com/data", {
        headers: { "x-request-id": requestId },
      }),
      env.MY_KV.get("config"),
    ]);

    return Response.json({ ok: true });
  },
} satisfies ExportedHandler<Env>;
```

## 4. Query Slowest Subrequests by Host Class

```typescript
// src/waterfall-query.ts
const ACCOUNT_ID = "<ACCOUNT_ID>";
const API_TOKEN = "<CF_API_TOKEN>";

export async function fetchWaterfallSummary(): Promise<void> {
  const sql = `
    SELECT
      blob3 AS host_class,
      blob5 AS method,
      quantileWeighted(0.99)(double1, 1) AS p99_ms,
      quantileWeighted(0.50)(double1, 1) AS p50_ms,
      countIf(double1 > 1000) AS slow_count,
      count() AS total
    FROM subrequest_waterfall
    WHERE timestamp > now() - INTERVAL '1' HOUR
      AND double1 >= 0
    GROUP BY host_class, method
    ORDER BY p99_ms DESC
    LIMIT 20
  `;

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );
  console.log(JSON.stringify(await resp.json(), null, 2));
}
```

## 5. Alert on Subrequest Latency Regression

```typescript
// src/waterfall-alert.ts
const HOST_SLO_MS: Record<string, number> = {
  "example.com": 200,
  "cloudflare": 50,
  "amazonaws.com": 300,
};

export async function alertOnSubrequestRegression(
  webhookUrl: string,
  rows: Array<{ host_class: string; p99_ms: number }>
): Promise<void> {
  const breaches = rows.filter(
    (r) => r.p99_ms > (HOST_SLO_MS[r.host_class] ?? Infinity)
  );
  if (breaches.length === 0) return;

  const lines = breaches.map(
    (r) => `${r.host_class}: p99=${r.p99_ms}ms > SLO=${HOST_SLO_MS[r.host_class]}ms`
  );

  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: `Subrequest latency breach:\n${lines.join("\n")}` }),
  });
}
```

## 6. Per-Request Waterfall Drill-Down Query

```sql
-- Look up all subrequests for a single slow request
SELECT
  blob2 AS url,
  blob3 AS host_class,
  blob4 AS status,
  double1 AS duration_ms
FROM subrequest_waterfall
WHERE blob1 = '<REQUEST_ID>'
ORDER BY double1 DESC
```

## Anti-patterns

- **Adding `console.time()` around every fetch**: manual instrumentation duplicates what the Tail Worker already captures passively; prefer the Tail approach to keep the observed Worker clean.
- **Storing full URLs as Analytics Engine indexes**: full URLs with query strings create unbounded cardinality; store the classified host or path prefix only.
- **Parsing timing when `sub.timing` is null**: some subrequest types (KV, DO RPC) may not expose timing; guard with a null check and emit `-1` as a sentinel.
- **Ignoring parallel vs sequential structure**: the waterfall table records individual span durations; parallel subrequests overlap and the sum exceeds wall time; do not sum durations to estimate total request latency.

## Gotchas

- Tail Workers see `fetchSubrequests` only for subrequests made with `fetch()`; Durable Object RPCs, KV bindings, and R2 operations appear as subrequests only if the runtime version supports it (check compatibility date).
- The `fetchSubrequests` field name and shape vary between `@cloudflare/workers-types` versions; cast to `unknown` first and defensively access fields.
- Tail Workers have a separate CPU time limit (10 ms); for very high-traffic Workers, sample the Tail payload rather than processing every event.
- The `x-request-id` header must be set by the observed Worker; it is not injected automatically.

## Verification

1. Deploy both Workers, make 20 requests that call at least 3 distinct upstream hosts.
2. Confirm Analytics Engine receives rows with `blob3` containing each host class.
3. Query the drill-down SQL with a known `REQUEST_ID` and verify all subrequests appear.
4. Introduce an artificial `await new Promise(r => setTimeout(r, 500))` before one fetch, confirm p99 for that host increases in the summary query.

## Related

- `workers-tail-real-time-log-streaming.md`
- `tail-worker-otel-span-export.md`
- `workers-tail-worker-sampling-high-traffic.md`
- `distributed-tracing-workers-d1-durable-objects-otel.md`
- `apm-transaction-tracing.md`

## Sources

- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/workers/observability/tail-workers/trace-workers/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
