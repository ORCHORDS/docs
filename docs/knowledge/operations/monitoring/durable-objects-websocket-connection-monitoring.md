# Monitoring Active WebSocket Connections in Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application uses Durable Objects to manage WebSocket sessions (e.g. a real-time chat, collaborative document, or live dashboard). You need to know how many active connections each DO instance holds, detect when a DO exceeds a connection ceiling, and aggregate connection counts across all instances over time.

## Context

Durable Objects hold WebSocket connections for the lifetime of the DO instance. The DO's `state.storage` persists counts across hibernation. A `/metrics` HTTP endpoint on the DO lets external monitors query the current state. A Cron Worker iterates known DO IDs, fetches metrics from each, writes aggregates to Analytics Engine, and posts a Slack alert when any instance exceeds the configured ceiling.

---

## Durable Object: Tracking Connection Count in Storage

```typescript
// src/room.ts
import { DurableObject } from 'cloudflare:workers';

export interface Env {
  ROOM: DurableObjectNamespace;
  ANALYTICS: AnalyticsEngineDataset;
}

export class Room extends DurableObject {
  private startedAt: number;

  constructor(state: DurableObjectState, env: Env) {
    super(state, env);
    this.startedAt = Date.now();
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    // --- WebSocket upgrade ---
    if (url.pathname === '/ws') {
      if (request.headers.get('Upgrade') !== 'websocket') {
        return new Response('Expected WebSocket', { status: 426 });
      }

      const [client, server] = Object.values(new WebSocketPair()) as [WebSocket, WebSocket];
      this.ctx.acceptWebSocket(server);

      const current = ((await this.ctx.storage.get<number>('connections')) ?? 0) + 1;
      await this.ctx.storage.put('connections', current);

      return new Response(null, { status: 101, webSocket: client });
    }

    // --- Metrics endpoint ---
    if (url.pathname === '/metrics') {
      const connections = (await this.ctx.storage.get<number>('connections')) ?? 0;
      const uptimeSeconds = Math.round((Date.now() - this.startedAt) / 1000);
      return Response.json({ connections, uptimeSeconds, id: this.ctx.id.toString() });
    }

    return new Response('Not found', { status: 404 });
  }

  async webSocketClose(ws: WebSocket, _code: number, _reason: string): Promise<void> {
    const current = (await this.ctx.storage.get<number>('connections')) ?? 0;
    await this.ctx.storage.put('connections', Math.max(0, current - 1));
  }

  async webSocketError(ws: WebSocket, _error: unknown): Promise<void> {
    // Treat an errored socket as closed
    await this.webSocketClose(ws, 1011, 'error');
  }
}
```

---

## Main Worker: Routing to the Durable Object

```typescript
// src/index.ts
export { Room } from './room';
export { default as CronAggregator } from './cron-aggregator';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Derive DO name from URL: /room/<room-id>/ws  or  /room/<room-id>/metrics
    const match = url.pathname.match(/^\/room\/([^/]+)(\/.*)?$/);
    if (!match) return new Response('Not found', { status: 404 });

    const [, roomId, rest] = match;
    const id = env.ROOM.idFromName(roomId);
    const stub = env.ROOM.get(id);

    // Forward the request with the sub-path
    const doUrl = new URL(rest ?? '/', request.url);
    return stub.fetch(new Request(doUrl.toString(), request));
  },
};
```

---

## Cron Worker: Aggregate Connection Counts to Analytics Engine

```typescript
// src/cron-aggregator.ts
// wrangler.toml: [[triggers]] crons = ["*/5 * * * *"]

const KNOWN_ROOM_IDS = [
  'general', 'engineering', 'product', 'support',
  // Extend this list or load from KV / D1 dynamically
];

const CONNECTION_CEILING = 50;

interface MetricsPayload {
  connections: number;
  uptimeSeconds: number;
  id: string;
}

export interface CronEnv extends Env {
  SLACK_WEBHOOK: string;
  WORKER_BASE_URL: string;  // e.g. "https://my-app.example.com"
}

export default {
  async scheduled(_event: ScheduledEvent, env: CronEnv): Promise<void> {
    const results: Array<{ roomId: string; metrics: MetricsPayload }> = [];
    const alerts: string[] = [];

    await Promise.allSettled(
      KNOWN_ROOM_IDS.map(async (roomId) => {
        const resp = await fetch(
          `${env.WORKER_BASE_URL}/room/${roomId}/metrics`,
          { headers: { 'X-Internal-Auth': 'cron' } }
        );
        if (!resp.ok) return;
        const metrics = await resp.json() as MetricsPayload;
        results.push({ roomId, metrics });

        // Write to Analytics Engine
        env.ANALYTICS.writeDataPoint({
          blobs: [roomId],                     // blob1 — room identifier
          doubles: [
            metrics.connections,               // double1 — active connections
            metrics.uptimeSeconds,             // double2 — DO uptime
          ],
          indexes: [roomId],
        });

        // Check ceiling
        if (metrics.connections > CONNECTION_CEILING) {
          alerts.push(
            `Room \`${roomId}\` has ${metrics.connections} connections (ceiling: ${CONNECTION_CEILING})`
          );
        }
      })
    );

    if (alerts.length > 0) {
      await fetch(env.SLACK_WEBHOOK, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: `:warning: *DO connection ceiling breached*\n${alerts.join('\n')}`,
        }),
      });
    }

    console.log(
      `[cron] Aggregated ${results.length} rooms; ${alerts.length} ceiling alerts`
    );
  },
};
```

---

## Querying Aggregate Trends in Analytics Engine

```sql
-- Average and max active connections per room over the last 24 hours
SELECT
  blob1                           AS room_id,
  ROUND(AVG(double1), 1)          AS avg_connections,
  MAX(double1)                    AS peak_connections,
  COUNT(*)                        AS samples
FROM do_ws_connections
WHERE timestamp >= NOW() - INTERVAL '24' HOUR
GROUP BY blob1
ORDER BY peak_connections DESC;
```

---

## wrangler.toml

```toml
name = "ws-app"

[[durable_objects.bindings]]
name       = "ROOM"
class_name = "Room"

[[migrations]]
tag = "v1"
new_classes = ["Room"]

[[triggers]]
crons = ["*/5 * * * *"]

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "do_ws_connections"
```

---

## Anti-patterns

- **Storing connection count only in memory (`this.connections`)** — Durable Objects can hibernate when idle; in-memory state is lost on hibernation. Always persist to `this.ctx.storage`.
- **Not decrementing on close/error** — if `webSocketClose` and `webSocketError` are not implemented, the counter drifts upward indefinitely.
- **Polling the DO from the Cron Worker via internal DO-to-DO calls** — use HTTP fetch through the Worker's public URL (or a private internal service binding) rather than trying to share the DO namespace stub across Workers directly.
- **Using `idFromString` with an untrusted room ID from the URL** — always sanitise or whitelist room IDs before passing them to `idFromName` to prevent arbitrary DO creation.

## Gotchas

- `WebSocketPair` returns an object, not an array; destructure with `Object.values()` or use the `[client, server]` tuple via `new WebSocketPair()` as a cast.
- The `/metrics` endpoint on the DO is publicly reachable via your Worker; gate it with a shared secret header (`X-Internal-Auth`) or Cloudflare Access to prevent external enumeration.
- Analytics Engine data points for DO metrics will reflect the state at the time of the Cron poll, not a real-time stream; spikes shorter than the cron interval (5 min) will be missed.
- `this.startedAt` is reset every time the DO is evicted and re-instantiated; for long-term uptime tracking, persist the initial start time to `storage` in the constructor.

## Verification

1. Connect two WebSocket clients to `/room/general/ws`.
2. Fetch `/room/general/metrics` and confirm `connections: 2`.
3. Close one client; fetch metrics again and confirm `connections: 1`.
4. Trigger the Cron Worker manually: `wrangler trigger --cron`
5. Wait 90 seconds and query Analytics Engine: `SELECT * FROM do_ws_connections WHERE blob1 = 'general' ORDER BY timestamp DESC LIMIT 5`.

## Related

- `workers-analytics-engine-funnel-analysis.md`
- `workers-latency-percentile-tracking-analytics-engine.md`
- `cloudflare-synthetic-monitoring-cron-workers.md`

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/durable-objects/api/websockets/
- https://developers.cloudflare.com/durable-objects/api/state/
- https://developers.cloudflare.com/analytics/analytics-engine/
