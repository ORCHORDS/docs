# Durable Objects Memory Usage Monitoring via Tail Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Durable Objects that accumulate in-memory state (caches, session maps, WebSocket connection registries) silently grow until they hit the 128 MB memory limit and start throwing `Error: Durable Object exceeded memory limit`. You need continuous visibility into per-object and per-class memory trends before the limit is hit.

## Context

Durable Objects do not expose a native memory-usage API. Memory can be approximated by serialising the in-object state to a known schema and measuring the byte length, then emitting that measurement on a periodic alarm or on every significant state mutation. A Tail Worker receives the `TailEvent` for every DO invocation and can forward these self-reported metrics to Analytics Engine without adding latency to the DO itself.

## 1. Self-Report Memory from the Durable Object

```typescript
// src/my-durable-object.ts
import { DurableObject } from "cloudflare:workers";

export interface Env {
  MY_DO: DurableObjectNamespace;
}

export class MyDurableObject extends DurableObject {
  private sessionMap: Map<string, unknown> = new Map();

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/__memory") {
      return Response.json({ memory_bytes: this.estimateMemory() });
    }

    // normal handling ...
    this.sessionMap.set(crypto.randomUUID(), { ts: Date.now() });
    return new Response("ok");
  }

  async alarm(): Promise<void> {
    // Re-arm the alarm every 60 s so Tail Workers can collect the report
    await this.ctx.storage.setAlarm(Date.now() + 60_000);
    // Emit memory estimate into console so Tail Worker can capture it
    console.log(
      JSON.stringify({
        type: "memory_report",
        class: "MyDurableObject",
        id: this.ctx.id.toString(),
        memory_bytes: this.estimateMemory(),
        session_count: this.sessionMap.size,
      })
    );
  }

  private estimateMemory(): number {
    try {
      return new TextEncoder().encode(JSON.stringify([...this.sessionMap])).length;
    } catch {
      return -1;
    }
  }
}
```

## 2. Tail Worker Captures Memory Reports

```typescript
// src/tail-worker.ts
export interface TailEnv {
  DO_MEMORY_METRICS: AnalyticsEngineDataset;
}

interface MemoryReport {
  type: string;
  class: string;
  id: string;
  memory_bytes: number;
  session_count: number;
}

export default {
  async tail(events: TraceItem[], env: TailEnv): Promise<void> {
    for (const event of events) {
      for (const log of event.logs ?? []) {
        if (log.level !== "log") continue;
        let report: MemoryReport;
        try {
          const msg = typeof log.message[0] === "string" ? log.message[0] : "";
          report = JSON.parse(msg);
        } catch {
          continue;
        }

        if (report.type !== "memory_report") continue;

        env.DO_MEMORY_METRICS.writeDataPoint({
          blobs: [report.class, report.id],
          doubles: [report.memory_bytes, report.session_count],
          indexes: [report.class],
        });
      }
    }
  },
} satisfies ExportedHandler<TailEnv>;
```

## 3. wrangler.toml Wiring

```toml
# Main Worker / DO configuration
[[durable_objects.bindings]]
name = "MY_DO"
class_name = "MyDurableObject"

# Tail Worker
[tail_consumers]
service = "do-memory-tail-worker"

# In the tail worker's wrangler.toml:
[[analytics_engine_datasets]]
binding = "DO_MEMORY_METRICS"
dataset = "do_memory_usage"
```

## 4. Query Memory Trends

```typescript
// src/memory-query.ts
const ACCOUNT_ID = "<ACCOUNT_ID>";
const API_TOKEN = "<CF_API_TOKEN>";

export async function fetchDoMemoryTrends(): Promise<void> {
  const sql = `
    SELECT
      blob1 AS do_class,
      max(double1) AS max_memory_bytes,
      avg(double1) AS avg_memory_bytes,
      count() AS samples
    FROM do_memory_usage
    WHERE timestamp > now() - INTERVAL '1' HOUR
    GROUP BY do_class
    ORDER BY max_memory_bytes DESC
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
  console.log(await resp.json());
}
```

## 5. Alert When Memory Exceeds Warning Threshold

```typescript
// src/memory-alert.ts
const MEMORY_WARN_BYTES = 80 * 1024 * 1024; // 80 MB (62.5 % of 128 MB limit)
const MEMORY_CRIT_BYTES = 110 * 1024 * 1024; // 110 MB

export async function alertOnMemory(
  webhookUrl: string,
  rows: Array<{ do_class: string; max_memory_bytes: number }>
): Promise<void> {
  const criticals = rows.filter((r) => r.max_memory_bytes > MEMORY_CRIT_BYTES);
  const warnings = rows.filter(
    (r) => r.max_memory_bytes > MEMORY_WARN_BYTES && r.max_memory_bytes <= MEMORY_CRIT_BYTES
  );

  if (criticals.length === 0 && warnings.length === 0) return;

  const lines = [
    ...criticals.map(
      (r) => `CRITICAL: ${r.do_class} max=${(r.max_memory_bytes / 1_048_576).toFixed(1)} MB`
    ),
    ...warnings.map(
      (r) => `WARNING:  ${r.do_class} max=${(r.max_memory_bytes / 1_048_576).toFixed(1)} MB`
    ),
  ];

  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: `DO memory alert:\n${lines.join("\n")}` }),
  });
}
```

## Anti-patterns

- **Serialising the entire state on every request**: call `estimateMemory()` only in alarm handlers or sampling 1 % of requests to avoid serialisation overhead on hot paths.
- **Using `JSON.stringify` on circular object graphs**: Durable Objects that cache response objects can cause circular-reference errors; use a custom serialiser or a size proxy.
- **Trusting the estimate as the actual V8 heap**: the byte-length of the JSON representation underestimates memory; treat it as a floor, not the ceiling.
- **Not re-arming the alarm**: a DO whose alarm handler throws will not reschedule itself; wrap alarm logic in try/catch and always re-arm.

## Gotchas

- Tail Workers receive events for DO invocations but have a separate 10 ms CPU budget; keep parsing lightweight.
- A Durable Object that has no active connections and no alarm will be evicted; memory reports stop until a new request wakes it.
- The `id` field of a Durable Object can be either a named ID (human-readable) or a random hex string; normalise it for grouping in Analytics Engine.
- Analytics Engine blob fields are capped at 1024 bytes; truncate long DO IDs before writing.

## Verification

1. Deploy the DO and Tail Worker, invoke the DO 200 times to grow `sessionMap`.
2. Wait for the alarm to fire (up to 60 s), confirm a `memory_report` log appears in the Tail Worker stream.
3. Query Analytics Engine and confirm `double1 > 0` for the DO class.
4. Manually set `MEMORY_WARN_BYTES = 1` and trigger the alert cron; confirm the webhook fires.

## Related

- `durable-objects-alarm-heartbeat-monitoring.md`
- `durable-objects-capacity-planning.md`
- `workers-tail-real-time-log-streaming.md`
- `tail-worker-otel-span-export.md`
- `cloudflare-analytics-engine-custom-metrics.md`

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/durable-objects/api/alarms/
