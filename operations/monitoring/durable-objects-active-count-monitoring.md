# Durable Objects Active Count Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You cannot tell how many Durable Object instances are alive at any moment — the Cloudflare dashboard
shows request counts but not active instance cardinality. When DO instance sprawl causes unexpected
billing spikes or eviction storms, you need a live count with per-namespace granularity.

## Context
Cloudflare Durable Objects are evicted from memory after ~10 seconds of inactivity, so "active" means
receiving at least one request within that window. A Tail Worker attached to your DO namespace captures
every request/response event and its `scriptName` and `entrypoint` fields identify the namespace.
By emitting a heartbeat data point to Analytics Engine on each DO invocation, you can approximate
active instance counts using a sliding-window distinct-count query.

---

## Section 1 — Tail Worker: Capturing DO Invocations

Wire a Tail Worker to the same script that hosts your Durable Object class. The Tail Worker
receives `TaildEvent` objects that include `event.request.url` and the DO's stub ID if you
forward it as a header from the calling Worker.

```typescript
// tail-worker.ts
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

// Emit one data point per DO invocation to track active instances
export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      // Only process Durable Object fetch events
      if (event.scriptName !== "my-durable-object-worker") continue;

      for (const log of event.logs) {
        // Expect the DO stub handler to emit a structured log line
        // e.g. console.log(JSON.stringify({ doId, namespace, action }))
        try {
          const entry = JSON.parse(log.message[0] as string) as {
            doId?: string;
            namespace?: string;
            action?: string;
          };

          if (!entry.doId || !entry.namespace) continue;

          env.ANALYTICS.writeDataPoint({
            blobs: [
              entry.namespace,                      // blob1: DO namespace/class name
              entry.doId,                           // blob2: unique DO instance ID
              entry.action ?? "request",            // blob3: what triggered this invocation
              event.outcome,                        // blob4: "ok" | "exception" | "exceeded-cpu"
            ],
            doubles: [
              event.cpuTime ?? 0,                   // double1: CPU time in ms for this invocation
              event.wallTime ?? 0,                  // double2: wall time in ms
            ],
            indexes: [entry.namespace],             // index: partition by namespace
          });
        } catch {
          // Non-JSON log line from a different source — ignore
        }
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 2 — DO Handler: Emitting Structured Log Lines

The DO class must emit a structured log that the Tail Worker can parse. Keep the log compact
because Tail Workers receive the full log payload and large logs consume the 128KB Tail event budget.

```typescript
// durable-object.ts
export interface Env {
  MY_DO: DurableObjectNamespace;
}

export class MyDurableObject implements DurableObject {
  private readonly id: string;
  private readonly namespace = "MyDurableObject";

  constructor(state: DurableObjectState, _env: Env) {
    this.id = state.id.toString();
  }

  async fetch(request: Request): Promise<Response> {
    const action = new URL(request.url).pathname.replace(/^\//, "") || "root";

    // Emit structured log — consumed by the Tail Worker
    console.log(
      JSON.stringify({
        doId: this.id,
        namespace: this.namespace,
        action,
      })
    );

    // ... business logic ...

    return new Response(JSON.stringify({ id: this.id, action }), {
      headers: { "Content-Type": "application/json" },
    });
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const name = url.searchParams.get("id") ?? "default";
    const stub = env.MY_DO.get(env.MY_DO.idFromName(name));
    return stub.fetch(request);
  },
} satisfies ExportedHandler<Env>;
```

---

## Section 3 — Analytics Engine SQL: Active Instance Count Queries

Approximate distinct active DO instances using a sliding window. Analytics Engine's `uniq()`
function applies HyperLogLog with ~2% error for large cardinalities.

```sql
-- Approximate distinct active DO instances per namespace in the last 60 seconds
SELECT
  blob1                  AS namespace,
  uniq(blob2)            AS approx_active_instances,
  count()                AS total_invocations
FROM workers_analytics.do_activity          -- dataset name from wrangler.toml
WHERE timestamp > now() - INTERVAL '60' SECOND
GROUP BY blob1
ORDER BY approx_active_instances DESC;
```

```sql
-- Active instance trend: 5-minute buckets over the last 6 hours
SELECT
  toStartOfFiveMinutes(timestamp)   AS bucket,
  blob1                             AS namespace,
  uniq(blob2)                       AS active_instances,
  countIf(blob4 != 'ok')            AS error_invocations
FROM workers_analytics.do_activity
WHERE timestamp > now() - INTERVAL '6' HOUR
GROUP BY bucket, blob1
ORDER BY bucket ASC, namespace ASC;
```

```sql
-- Top 20 most active DO instances by invocation count (last hour)
SELECT
  blob1                  AS namespace,
  blob2                  AS do_instance_id,
  count()                AS invocations,
  avg(double1)           AS avg_cpu_ms,
  max(double1)           AS max_cpu_ms
FROM workers_analytics.do_activity
WHERE timestamp > now() - INTERVAL '1' HOUR
GROUP BY namespace, do_instance_id
ORDER BY invocations DESC
LIMIT 20;
```

Schedule a cron Worker to run the first query every minute and fire a Cloudflare Notification
(or Slack webhook) when `approx_active_instances` exceeds your expected ceiling.

---

## Anti-patterns
- Trying to count active DOs from the Cloudflare dashboard — it reports request volume, not
  instance cardinality, and has no sub-minute resolution.
- Using `state.id.toString()` as a log field at DO construction time without caching it — the
  constructor runs once per isolate lifetime, so the ID is always available without per-request
  overhead.
- Logging the full request body inside the DO just to get routing context — log only the minimal
  fields (`doId`, `namespace`, `action`) to stay within the 128KB Tail event payload budget.
- Attaching the Tail Worker to every Worker in the account instead of only the DO-hosting script —
  unrelated events add noise and inflate Analytics Engine write costs.

## Gotchas
- A DO that uses Hibernation API (WebSocket hibernation) wakes on socket messages but does NOT
  emit a `fetch` Tail event — wire a separate log in the `webSocketMessage` handler.
- `uniq()` in Analytics Engine SQL uses HyperLogLog; expect ±2% error above ~1,000 distinct
  instances. For exact counts at low cardinality, store IDs in a D1 table updated by the Tail Worker.
- Tail Workers are triggered asynchronously after the original request completes — the DO may be
  evicted by the time the Tail Worker writes to Analytics Engine, so counts lag by seconds.
- The Cloudflare limit of 25 `writeDataPoint` calls per Analytics Engine dataset per request also
  applies to Tail Workers — batch carefully if a single Tail event contains many log lines.

## Verification
```bash
# Watch Tail Worker output in real time to confirm it parses DO log lines
wrangler tail my-durable-object-worker --format json | jq '.logs[].message'

# Confirm data is flowing to Analytics Engine
curl "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  --data-urlencode "query=SELECT uniq(blob2) AS active FROM workers_analytics.do_activity WHERE timestamp > now() - INTERVAL '5' MINUTE"

# Count distinct DO IDs seen in the last 5 minutes
wrangler d1 execute <db> --command \
  "SELECT COUNT(DISTINCT do_id) FROM do_heartbeats WHERE seen_at > unixepoch() - 300"
```

## Related
- `durable-objects-alarm-heartbeat-monitoring.md`
- `durable-objects-capacity-planning.md`
- `durable-objects-memory-tail-workers.md`
- `durable-objects-request-queue-depth-monitoring.md`
- `tail-worker-structured-error-classification-d1.md`
- `analytics-engine-cardinality-management-multi-dimension.md`

## Sources
- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/durable-objects/api/state/
- https://developers.cloudflare.com/durable-objects/reference/hibernatable-websockets-api/
