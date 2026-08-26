# Durable Objects Hibernation Wake Latency Optimization

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

WebSocket connections to a Durable Object are being dropped or experiencing 1–3 second reconnect delays after a period of inactivity. RUM data shows a burst of high-latency messages after chat or collaboration rooms go quiet for 30+ seconds. The Durable Object is hibernating correctly to save costs, but the wake-up path is slower than acceptable.

## Context

Cloudflare Durable Objects support the Hibernation API (`this.ctx.acceptWebSocket(ws)`) which allows the DO to be evicted from memory between WebSocket messages. Hibernation eliminates the steady-state CPU cost of idle connections but introduces a wake latency of 50–300 ms (p50) when the first message arrives for a hibernated object. The wake path involves deserialising the DO's JS heap from a checkpoint, re-running any initialization that was not persisted to `storage`, and re-establishing the connection context. Optimising the constructor and `webSocketMessage` handler shortens this path.

## Adopting the Hibernation API Correctly

```typescript
import { DurableObject } from "cloudflare:workers";

interface Env {
  ROOM: DurableObjectNamespace;
}

interface RoomState {
  topic: string;
  memberCount: number;
}

export class ChatRoom extends DurableObject {
  // State loaded lazily from storage — never from constructor params
  private state: RoomState | null = null;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    // GOOD: keep the constructor near-empty.
    // Expensive setup here runs on EVERY wake, adding latency.
    // Defer to a lazy-init pattern instead.
  }

  // Lazy initialisation: runs once on first use after a wake
  private async ensureState(): Promise<RoomState> {
    if (this.state) return this.state;
    this.state = (await this.ctx.storage.get<RoomState>("room")) ?? {
      topic: "general",
      memberCount: 0,
    };
    return this.state;
  }

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") === "websocket") {
      const pair = new WebSocketPair();
      // Hibernation API: pass the server socket to ctx.acceptWebSocket
      // The DO may be evicted between messages; this.state will be null on wake
      this.ctx.acceptWebSocket(pair[1]);
      return new Response(null, { status: 101, webSocket: pair[0] });
    }
    return new Response("Expected WebSocket", { status: 426 });
  }

  // Called by the runtime after waking from hibernation
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const state = await this.ensureState(); // fast: hits in-memory cache after first call
    const data = typeof message === "string" ? JSON.parse(message) : null;
    if (!data) return;

    if (data.type === "ping") {
      ws.send(JSON.stringify({ type: "pong", memberCount: state.memberCount }));
    }
  }

  async webSocketClose(ws: WebSocket, code: number, reason: string): Promise<void> {
    ws.close(code, reason);
  }
}
```

## Minimising Work on the Wake Path

```typescript
export class OptimisedRoom extends DurableObject {
  // Pre-serialised snapshot stored in storage as a single key
  // avoids multiple storage.get() round-trips during wake.
  private snapshot: RoomSnapshot | null = null;

  private async getSnapshot(): Promise<RoomSnapshot> {
    if (this.snapshot) return this.snapshot;
    // Single read vs. multiple individual keys = fewer round-trips
    const raw = await this.ctx.storage.get<RoomSnapshot>("snap");
    this.snapshot = raw ?? defaultSnapshot();
    return this.snapshot;
  }

  private async persistSnapshot(): Promise<void> {
    if (!this.snapshot) return;
    // Batch write — storage.put is asynchronous; use ctx.waitUntil to avoid
    // blocking the message handler on the write confirmation.
    this.ctx.waitUntil(this.ctx.storage.put("snap", this.snapshot));
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const snap = await this.getSnapshot();

    // Mutate in-memory snapshot, persist asynchronously
    if (typeof message === "string") {
      const msg = JSON.parse(message);
      snap.lastActivity = Date.now();
      snap.messageCount += 1;
      await this.persistSnapshot();
      this.broadcast(JSON.stringify({ type: "message", payload: msg }));
    }
  }

  private broadcast(data: string): void {
    for (const ws of this.ctx.getWebSockets()) {
      try { ws.send(data); } catch { /* socket already closed */ }
    }
  }
}

interface RoomSnapshot {
  lastActivity: number;
  messageCount: number;
  members: string[];
}

function defaultSnapshot(): RoomSnapshot {
  return { lastActivity: Date.now(), messageCount: 0, members: [] };
}
```

## Alarm-Based Keepalive to Avoid Cold Wakes

```typescript
// If wake latency is unacceptable and the room is expected to stay active,
// use a storage alarm to ping the DO before the hibernation window expires.
// Trade-off: costs ~1 CPU-ms per alarm fire vs. full wake latency on first message.

export class KeepaliveRoom extends DurableObject {
  private readonly KEEPALIVE_MS = 25_000; // slightly under 30s idle threshold

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") === "websocket") {
      const pair = new WebSocketPair();
      this.ctx.acceptWebSocket(pair[1]);
      await this.scheduleKeepalive();
      return new Response(null, { status: 101, webSocket: pair[0] });
    }
    return new Response("Expected WebSocket", { status: 426 });
  }

  private async scheduleKeepalive(): Promise<void> {
    const existing = await this.ctx.storage.getAlarm();
    if (existing == null) {
      await this.ctx.storage.setAlarm(Date.now() + this.KEEPALIVE_MS);
    }
  }

  async alarm(): Promise<void> {
    const sockets = this.ctx.getWebSockets();
    if (sockets.length === 0) {
      // No connected clients — let the DO hibernate for real
      return;
    }
    // Re-arm the alarm to prevent hibernation
    await this.ctx.storage.setAlarm(Date.now() + this.KEEPALIVE_MS);
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    ws.send(message); // echo for demo
  }

  async webSocketClose(ws: WebSocket, code: number, reason: string): Promise<void> {
    ws.close(code, reason);
    if (this.ctx.getWebSockets().length === 0) {
      // Last client disconnected — cancel keepalive and let DO hibernate
      await this.ctx.storage.deleteAlarm();
    }
  }
}
```

## Anti-patterns

- Putting expensive async initialization (external API calls, large `storage.list()`) in the DO constructor — this runs on every wake and blocks the first message handler.
- Using the legacy `state.blockConcurrencyWhile()` pattern for initialization in a hibernating DO — it prevents the runtime from delivering queued messages until the initializer completes, amplifying wake latency.
- Storing per-socket state in class properties rather than in `storage` or as WebSocket attachment data — class properties are lost on hibernation, causing state desync after wake.

## Gotchas

- `this.ctx.getWebSockets()` returns all sockets accepted via `acceptWebSocket()` even after hibernation — you do not need to re-accept them on wake.
- WebSocket `attachment` data passed to `acceptWebSocket(ws, attachment)` is serialised and persisted across hibernation automatically; keep attachments small (< 2 KB) to avoid serialisation overhead on every wake.

## Verification

```bash
# Observe wake latency by sending a message after a 60s idle window
# and measuring the time until the server response arrives
wscat -c "wss://example.com/room/test" -x '{"type":"ping"}' --wait 60 \
  && wscat -c "wss://example.com/room/test" -x '{"type":"ping"}' --timing

# Check DO request logs for hibernation events
wrangler tail --format pretty MyWorker | grep -i "hibernat\|wake\|alarm"

# Confirm alarm is registered
curl -X GET "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/durable-objects/namespaces/$NS_ID/objects" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | .id'
```

## Related

- `performance/durable-objects-low-latency-stateful.md`
- `performance/durable-objects-websocket-efficiency.md`
- `performance/durable-objects-memory-optimization.md`
- `performance/workers-cold-start-optimization.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/websockets/#hibernation-api
- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://developers.cloudflare.com/durable-objects/best-practices/create-durable-object-stubs-and-send-requests/
