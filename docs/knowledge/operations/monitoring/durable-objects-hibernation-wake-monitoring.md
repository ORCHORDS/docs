# Durable Objects Hibernation Wake Monitoring

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project chat rooms and live feed aggregators are backed by Durable Objects that use the WebSocket Hibernation API to stay connected with zero-cost idle periods. When the DO wakes from hibernation to handle an incoming WebSocket message or alarm, the first operation latency spikes compared to warm resumption. Undetected wake latency bursts degrade perceived message delivery for users already in a room, and unexpectedly frequent wake cycles indicate a misconfigured alarm or a stuck client that prevents hibernation from taking effect.

## Context

Durable Objects enter hibernation when all WebSocket connections are in the "hibernated" state (accepted via `server.serveWebSocket()`) and no JavaScript is executing. The runtime evicts the DO's in-memory state and restores it on the next event. Cloudflare does not expose a first-class "hibernation wake" metric, so wake latency must be derived by timestamping at the start of the first event handler after hibernation and comparing against the event's own timestamp. Tail Workers attached to the DO's script receive `TraceItem` objects with `cpuTime` that spike on wake turns.

## Section 1 — Instrumentation: Wake Latency Tracking Inside the DO

Maintain an in-memory `lastActiveAt` timestamp. When the DO processes an event, compare `Date.now()` to the event's arrival time. A gap larger than a threshold indicates a hibernation cycle. Write the wake latency to Analytics Engine via a bound dataset.

```typescript
// durable-objects/src/ChatRoom.ts
import { Env } from "./types";

const HIBERNATION_THRESHOLD_MS = 2_000; // gaps > 2 s are hibernation wakes
const COLD_START_THRESHOLD_MS = 50;     // first event cpu > 50 ms = cold init

export class ChatRoom implements DurableObject {
  private lastActiveAt = 0;
  private wakeCount = 0;
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    return this.trackWake("fetch", async () => {
      const upgrade = request.headers.get("Upgrade");
      if (upgrade === "websocket") {
        const [client, server] = Object.values(new WebSocketPair());
        this.state.acceptWebSocket(server);
        return new Response(null, { status: 101, webSocket: client });
      }
      return new Response("Not a WebSocket upgrade", { status: 426 });
    });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    await this.trackWake("ws_message", async () => {
      // ... process message ...
    });
  }

  async alarm(): Promise<void> {
    await this.trackWake("alarm", async () => {
      // ... run scheduled maintenance ...
    });
  }

  private async trackWake<T>(
    eventType: string,
    handler: () => Promise<T>
  ): Promise<T> {
    const now = Date.now();
    const gapMs = this.lastActiveAt > 0 ? now - this.lastActiveAt : 0;
    const isWake = gapMs > HIBERNATION_THRESHOLD_MS;

    if (isWake) {
      this.wakeCount++;
      this.recordWakeEvent(eventType, gapMs, now);
    }

    const cpuStart = performance.now();
    const result = await handler();
    const cpuMs = performance.now() - cpuStart;

    this.lastActiveAt = Date.now();

    if (cpuMs > COLD_START_THRESHOLD_MS) {
      this.recordSlowWakeCpu(eventType, cpuMs, isWake);
    }

    return result;
  }

  private recordWakeEvent(eventType: string, gapMs: number, ts: number): void {
    const doId = this.state.id.toString().slice(0, 16);
    this.env.ANALYTICS_ENGINE.writeDataPoint({
      blobs: [
        "do_hibernation_wake",   // blob1: metric name
        eventType,               // blob2: what triggered the wake
        doId,                    // blob3: DO shard identifier (truncated)
        this.env.ENVIRONMENT,    // blob4: env
      ],
      doubles: [
        gapMs,                   // double1: hibernation gap ms
        this.wakeCount,          // double2: cumulative wake count this lifetime
        ts,                      // double3: wall timestamp
      ],
      indexes: [doId],
    });
  }

  private recordSlowWakeCpu(eventType: string, cpuMs: number, wasWake: boolean): void {
    this.env.ANALYTICS_ENGINE.writeDataPoint({
      blobs: [
        "do_wake_cpu_spike",
        eventType,
        wasWake ? "post_hibernate" : "warm",
        this.env.ENVIRONMENT,
      ],
      doubles: [cpuMs, wasWake ? 1 : 0],
      indexes: [this.state.id.toString().slice(0, 16)],
    });
  }
}
```

## Section 2 — Tail Worker: Correlate cpuTime Spikes with Wake Events

The DO's Tail Worker receives `TraceItem` objects. A sudden cpuTime spike on the first event after a quiet period is a proxy for hibernation wake cost at the script level.

```typescript
// tail-worker/src/do-wake-tail.ts
interface Env {
  ANALYTICS_ENGINE: AnalyticsEngineDataset;
}

// Track last-seen cpuTime per DO script to detect spikes
const lastCpuByScript = new Map<string, number>();

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const item of events) {
      const scriptName = (item as any).scriptName ?? "unknown";
      const cpuMs = item.cpuTime ?? 0;
      const prev = lastCpuByScript.get(scriptName) ?? cpuMs;
      const ratio = prev > 0 ? cpuMs / prev : 1;

      // A > 5× jump in cpu is a heuristic indicator of cold/wake overhead
      if (ratio > 5 && cpuMs > 20) {
        env.ANALYTICS_ENGINE.writeDataPoint({
          blobs: [
            "tail_do_cpu_jump",
            scriptName,
            item.outcome,
          ],
          doubles: [cpuMs, prev, ratio],
          indexes: [scriptName.slice(0, 32)],
        });
      }

      lastCpuByScript.set(scriptName, cpuMs);
    }
  },
} satisfies ExportedHandler<Env>;
```

## Section 3 — Alerting: PagerDuty via Cloudflare Notification Webhook

Create a Scheduled Worker that polls Analytics Engine for high wake-gap P99 and fires a PagerDuty event when the threshold is breached.

```typescript
// workers/src/do-wake-alert.ts
interface Env {
  CF_ACCOUNT_ID: string;
  CF_API_TOKEN: string;
  PD_ROUTING_KEY: string;
}

const WAKE_GAP_P99_ALERT_MS = 30_000; // alert if P99 gap > 30 s
const AE_QUERY = `
  SELECT
    QUANTILE(0.99, double1) AS p99_gap_ms,
    COUNT(*) AS wake_count
  FROM analytics_engine_dataset
  WHERE blob1 = 'do_hibernation_wake'
    AND timestamp > NOW() - INTERVAL '5' MINUTE
`;

export default {
  async scheduled(_: ScheduledEvent, env: Env): Promise<void> {
    const resp = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
        body: JSON.stringify({ query: AE_QUERY }),
      }
    );
    const { data } = await resp.json<{ data: { p99_gap_ms: number; wake_count: number }[] }>();
    const row = data?.[0];
    if (!row || row.wake_count < 5) return; // not enough samples

    if (row.p99_gap_ms > WAKE_GAP_P99_ALERT_MS) {
      await fetch("https://events.pagerduty.com/v2/enqueue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          routing_key: env.PD_ROUTING_KEY,
          event_action: "trigger",
          payload: {
            summary: `DO hibernation wake P99 gap ${Math.round(row.p99_gap_ms / 1000)}s > threshold`,
            severity: "warning",
            source: "cloudflare-workers",
            custom_details: { p99_gap_ms: row.p99_gap_ms, wake_count: row.wake_count },
          },
          dedup_key: "do-hibernation-wake-p99",
        }),
      });
    }
  },
};
```

## Section 4 — Dashboard Queries

```sql
-- Hibernation wake frequency over 24 hours (bucketed by hour)
SELECT
  DATE_TRUNC('hour', timestamp) AS hour,
  COUNT(*) AS wake_events,
  AVG(double1) AS avg_gap_ms,
  QUANTILE(0.95, double1) AS p95_gap_ms
FROM analytics_engine_dataset
WHERE blob1 = 'do_hibernation_wake'
  AND timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY 1
ORDER BY 1;

-- Top DOs by wake count (potential misconfigured alarm loops)
SELECT
  blob3 AS do_shard,
  COUNT(*) AS total_wakes,
  AVG(double1) AS avg_gap_ms,
  MAX(double2) AS lifetime_wake_count
FROM analytics_engine_dataset
WHERE blob1 = 'do_hibernation_wake'
  AND timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20;

-- CPU spike events on wake vs warm turns
SELECT
  blob3 AS warm_or_wake,
  AVG(double1) AS avg_cpu_ms,
  QUANTILE(0.99, double1) AS p99_cpu_ms,
  COUNT(*) AS events
FROM analytics_engine_dataset
WHERE blob1 = 'do_wake_cpu_spike'
  AND timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY 1;
```

## Anti-patterns

- Polling `Date.now()` inside the DO constructor to detect wake — the constructor runs on every cold start AND every hibernation wake; the gap check must compare against a stored `lastActiveAt` value updated at the end of each handler.
- Using `state.storage.get("lastActiveAt")` for the gap check — storage reads are async and add a subrequest; use in-memory `this.lastActiveAt` which is reset to zero on each wake/cold start, which is exactly the signal you want.
- Alerting on every single wake event — hibernation wakes are normal; alert on the P99 gap exceeding a threshold or on wake frequency exceeding a rate that indicates a misbehaving alarm loop.
- Binding Analytics Engine to the DO class instead of to the parent Worker — DOs can use environment bindings directly; this is fine, but ensure the binding is declared in `wrangler.toml` under the correct DO class config.

## Gotchas

- `performance.now()` inside a DO returns cpu time, not wall time; use `Date.now()` for wall clock measurements.
- The Tail Worker for a DO receives events tagged with the DO's script name, not the DO ID — use the stub ID embedded in the trace if you need per-shard granularity.
- Hibernation does not evict `state.storage`; only in-memory (`this.`) properties are lost.
- An alarm scheduled while the DO is in JavaScript execution will keep the DO alive; only after the alarm handler completes can hibernation begin — a tight alarm loop prevents hibernation entirely.
- Analytics Engine `writeDataPoint` from inside a DO counts toward the DO's subrequest limit (1 000 per request); batch or throttle if the DO emits many events per turn.

## Verification

1. Deploy the ChatRoom DO with the tracking instrumentation.
2. Connect a WebSocket, send one message, then disconnect and wait 10 seconds.
3. Reconnect and send another message; verify `isWake = true` and a `do_hibernation_wake` data point appears in Analytics Engine within 60 seconds.
4. Query: `SELECT COUNT(*) FROM ae WHERE blob1 = 'do_hibernation_wake' AND timestamp > NOW() - INTERVAL '5' MINUTE` — expect at least 1.
5. Trigger the alert Worker manually with a lowered `WAKE_GAP_P99_ALERT_MS = 100` and confirm a PagerDuty incident appears.

## Related

- `/documentation/docs/policies/monitoring/durable-objects-alarm-heartbeat-monitoring.md`
- `/documentation/docs/policies/monitoring/durable-objects-alarm-miss-rate-monitoring.md`
- `/documentation/docs/policies/monitoring/durable-objects-memory-tail-workers.md`
- `/documentation/docs/policies/monitoring/durable-objects-storage-growth-forecasting-analytics-engine.md`
- `/documentation/docs/policies/monitoring/tail-worker-structured-log-sampling-strategies.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/websockets/#websocket-hibernation
- https://developers.cloudflare.com/durable-objects/observability/tail-workers/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/durable-objects/api/alarms/
