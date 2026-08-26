# Tail Worker Cold Start Attribution Monitoring

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Latency spikes appear intermittently in p99 dashboards but average (p50) looks healthy. Cold starts
in the isolate lifecycle are the usual culprit, yet standard Workers analytics aggregate wall-clock
time without distinguishing cold-start overhead from real business logic duration. You need to
attribute cold-start cost per script, per colo, and over time without relying on Cloudflare's
built-in starter metrics alone.

## Context

Every Workers invocation goes through one of two paths: a warm isolate reuse (microseconds of
overhead) or a fresh isolate boot (tens to hundreds of milliseconds). Tail Workers receive a
`TailItem` for each completed request that includes `event.wallTime`, `event.cpuTime`,
`event.scriptVersion`, and whether `event.coldStart` was true. Combining these fields with
Analytics Engine lets you build percentile dashboards segmented by cold/warm path, script name,
and Cloudflare colo — giving ops teams the precision they need to tune `minInstances`, placement
policies, and bundle sizes.

## Setting Up the Tail Worker

Create a dedicated Tail Worker that consumes events from your primary Workers and writes cold-start
attribution rows to Analytics Engine.

```typescript
// tail-attribution-worker/src/index.ts
export interface Env {
  ATTRIBUTION: AnalyticsEngineDataset;
}

interface TailItem {
  scriptName: string;
  event: {
    wallTime: number;   // ms total wall-clock
    cpuTime: number;    // ms CPU
    coldStart: boolean;
  };
  exceptions: Array<{ message: string }>;
  outcome: string; // "ok" | "exception" | "canceled" | "exceededCpu" | "exceededMemory" | "killed"
  eventTimestamp: number; // epoch ms
}

export default {
  async tail(events: TailItem[], env: Env): Promise<void> {
    for (const item of events) {
      env.ATTRIBUTION.writeDataPoint({
        blobs: [
          item.scriptName ?? "unknown",
          item.outcome,
          item.event.coldStart ? "cold" : "warm",
        ],
        doubles: [
          item.event.wallTime,
          item.event.cpuTime,
          item.event.wallTime - item.event.cpuTime, // idle / network wait
        ],
        indexes: [item.scriptName ?? "unknown"],
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

## Wrangler Configuration

```toml
# wrangler.toml for the Tail Worker
name = "tail-attribution-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[tail_consumers]]
service = "your-primary-worker"

[[analytics_engine_datasets]]
binding = "ATTRIBUTION"
dataset = "worker_cold_start_attribution"
```

Tail Workers must be deployed in the same account. One Tail Worker can tail multiple services by
adding multiple `[[tail_consumers]]` blocks.

## Querying Cold Start Rate per Script

Use the Analytics Engine SQL API to calculate the cold-start fraction per script over a rolling
window:

```typescript
// src/query-cold-start-rate.ts
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;

async function coldStartRate(scriptName: string, hours = 1): Promise<void> {
  const sql = `
    SELECT
      blob1 AS script_name,
      countIf(blob3 = 'cold')  AS cold_invocations,
      count()                  AS total_invocations,
      countIf(blob3 = 'cold') / count() * 100 AS cold_start_pct,
      quantileWeighted(0.99)(double1, 1) AS p99_wall_ms,
      quantileWeightedIf(0.99)(double1, 1, blob3 = 'cold')  AS p99_cold_ms,
      quantileWeightedIf(0.99)(double1, 1, blob3 = 'warm')  AS p99_warm_ms
    FROM worker_cold_start_attribution
    WHERE
      timestamp > NOW() - INTERVAL '${hours}' HOUR
      AND blob1 = '${scriptName}'
    GROUP BY blob1
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: sql }),
    }
  );

  const data = await res.json();
  console.table(data.data);
}
```

## Alerting on Elevated Cold Start Rate

Wire an alert when cold-start fraction crosses a threshold using a scheduled Worker:

```typescript
// src/cold-start-alert.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const rate = await fetchColdStartRate(env, "my-api-worker", 5); // last 5 min
    if (rate > 0.15) {
      // More than 15 % cold in a 5-minute window → alert
      await env.ALERT_QUEUE.send({
        severity: "warning",
        title: `Cold start rate elevated: ${(rate * 100).toFixed(1)}%`,
        script: "my-api-worker",
        runbook: "https://wiki.example.com/runbooks/cold-starts",
      });
    }
  },
} satisfies ExportedHandler<Env>;
```

## Colo-Level Attribution

Add `request.cf.colo` from the original Worker via a custom header or the Tail Worker's `event`
metadata (if forwarded):

```typescript
// In your primary Worker — attach colo so Tail Worker can read it
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const colo = request.cf?.colo ?? "unknown";
    const res = await handleRequest(request, env);
    // Forward colo via response header for tail attribution
    const out = new Response(res.body, res);
    out.headers.set("X-Colo", colo);
    return out;
  },
};
```

Then in the Tail Worker, read `item.logs` or `item.event.response.headers` if you expose the
header, and include it as a fourth blob for per-colo segmentation.

## Anti-patterns

- **Tailing the Tail Worker itself.** Circular tail chains are blocked by Cloudflare but attempting
  them wastes deployment time. Always tail only primary-serving Workers.
- **Writing one row per exception field.** Tail Workers receive batched `events[]`; iterating
  per-exception instead of per-event inflates Analytics Engine row counts needlessly.
- **Treating `cpuTime = 0` as warm.** During genuine cold starts the isolate setup time sometimes
  appears as zero CPU because it occurs outside the billable CPU window. Use `coldStart` boolean
  directly, not derived heuristics.
- **Ignoring `outcome != "ok"`.** Crashed invocations still have cold-start overhead. Excluding
  non-ok outcomes skews your warm-path p99 upward and makes the problem look worse than it is.

## Gotchas

- Tail Workers have their own 10 ms CPU budget per batch; heavy JSON parsing of large log fields
  can exhaust it. Keep the Tail Worker logic minimal.
- Analytics Engine free tier caps at 100k rows/day per dataset. High-traffic workers should sample
  (e.g., write 1-in-10 warm invocations, all cold invocations) to stay within limits.
- `event.coldStart` is `undefined` for Durable Object stubs routed through a Worker; only the
  outer fetch handler exposes it reliably.
- There is a ~15-second delivery delay from invocation to Tail Worker receipt; real-time alerting
  requires accepting this lag or supplementing with Runtime Logs streaming.

## Verification

1. Deploy the Tail Worker and primary Worker with `wrangler deploy`.
2. Trigger 20 requests in quick succession (warm), then wait >30 seconds idle before sending
   another (likely cold).
3. Query Analytics Engine within 5 minutes:
   ```sql
   SELECT blob3, count() FROM worker_cold_start_attribution
   WHERE timestamp > NOW() - INTERVAL '10' MINUTE
   GROUP BY blob3
   ```
   Expect both `cold` and `warm` rows.
4. Confirm `double1` (wallTime) for cold rows is larger than warm rows.
5. Verify alert fires when you artificially set the threshold to 0.01 (1 %).

## Related

- `cold-start-latency-monitoring.md`
- `workers-tail-real-time-log-streaming.md`
- `workers-tail-worker-sampling-high-traffic.md`
- `workers-cpu-time-percentile-analytics-engine.md`
- `cloudflare-analytics-engine-custom-metrics.md`

## Sources

- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/runtime-apis/handlers/tail/
- https://developers.cloudflare.com/workers/configuration/smart-placement/
