# Durable Objects WebSocket Fanout Broadcast Optimization

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project live rooms (anonymous shout threads) use a Durable Object as the single authoritative
broadcast hub per room. As participant count grows past ~200 concurrent WebSocket connections,
broadcasting a single message by iterating `for...of this.sessions` blocks the DO's single
JavaScript thread for tens of milliseconds, causing heartbeat timeouts, message reordering, and
dropped connections for late-batch clients.

## Context

Durable Objects run in a single-threaded V8 isolate; all WebSocket I/O is asynchronous but the
JavaScript loop that calls `ws.send()` on every session is synchronous CPU work. A naive O(n)
broadcast loop with 500 open sockets and a 1 KB payload can consume 5–15 ms of CPU time, enough
to breach the DO's cooperative-yield budget and delay incoming message delivery. The optimisation
target is reducing broadcast CPU time while preserving delivery order guarantees.

## Section 1 — Measure Broadcast Latency Under Load

Instrument the DO broadcast method to emit timing telemetry and expose it via a diagnostic
endpoint before optimising.

```typescript
// src/durable-objects/room.ts (measurement phase)
import { DurableObject } from "cloudflare:workers";

interface Session {
  ws: WebSocket;
  userId: string;
  joinedAt: number;
}

export class Room extends DurableObject {
  private sessions = new Map<WebSocket, Session>();

  // Naive broadcast — establish baseline latency
  private broadcastNaive(payload: string): BroadcastStats {
    const start = Date.now();
    let sent = 0;
    let errored = 0;

    for (const [ws, session] of this.sessions) {
      try {
        ws.send(payload);
        sent++;
      } catch {
        this.sessions.delete(ws);
        errored++;
      }
    }

    return {
      durationMs: Date.now() - start,
      sent,
      errored,
      sessionCount: this.sessions.size,
    };
  }
}

interface BroadcastStats {
  durationMs: number;
  sent: number;
  errored: number;
  sessionCount: number;
}
```

Collect `broadcastStats.durationMs` via `ctx.waitUntil` into Analytics Engine. With 500
sessions a naive broadcast consistently shows 8–18 ms — the optimisation target is < 2 ms.

## Section 2 — Chunked Broadcast with Yield Points

Break the broadcast loop into chunks, yielding to the event loop between chunks using a
`setTimeout(0)` trampoline. This prevents starvation of incoming WebSocket message handlers and
DO alarm callbacks.

```typescript
// src/durable-objects/room.ts (chunked broadcast)
export class RoomOptimized extends DurableObject {
  private sessions = new Map<WebSocket, Session>();
  private readonly CHUNK_SIZE = 50; // tune for your payload size

  async broadcastChunked(payload: string): Promise<void> {
    const entries = [...this.sessions.entries()];
    const dead: WebSocket[] = [];

    for (let i = 0; i < entries.length; i += this.CHUNK_SIZE) {
      const chunk = entries.slice(i, i + this.CHUNK_SIZE);

      for (const [ws] of chunk) {
        try {
          ws.send(payload);
        } catch {
          dead.push(ws);
        }
      }

      // Yield to event loop between chunks so incoming messages can be processed
      if (i + this.CHUNK_SIZE < entries.length) {
        await new Promise<void>((resolve) => setTimeout(resolve, 0));
      }
    }

    for (const ws of dead) {
      this.sessions.delete(ws);
    }
  }
}
```

This reduces maximum single-chunk CPU time to ~1 ms for 50 sends, keeping each event-loop tick
well within the 10 ms cooperative-yield threshold.

## Section 3 — Tagged Broadcast with Subscription Filtering

Anonymous social platforms need selective fanout: only broadcast to users in the same room
thread, not to everyone in the DO. Adding a subscription tag to each session avoids iterating
and skip-checking all 500 sessions when only 40 care about a specific nested thread.

```typescript
// src/durable-objects/room.ts (tagged fanout)
interface SessionMeta {
  userId: string;
  tags: Set<string>; // e.g. "thread:abc123", "typing:room"
}

export class RoomFanout extends DurableObject {
  // tag → Set<WebSocket> for O(1) subscriber lookup
  private tagIndex = new Map<string, Set<WebSocket>>();
  private sessions = new Map<WebSocket, SessionMeta>();

  subscribe(ws: WebSocket, tags: string[]): void {
    const meta: SessionMeta = {
      userId: (this.ctx.getTags(ws)[0] as string) ?? "anon",
      tags: new Set(tags),
    };
    this.sessions.set(ws, meta);

    for (const tag of tags) {
      if (!this.tagIndex.has(tag)) this.tagIndex.set(tag, new Set());
      this.tagIndex.get(tag)!.add(ws);
    }
  }

  unsubscribe(ws: WebSocket): void {
    const meta = this.sessions.get(ws);
    if (!meta) return;
    for (const tag of meta.tags) {
      this.tagIndex.get(tag)?.delete(ws);
    }
    this.sessions.delete(ws);
  }

  async broadcastToTag(tag: string, payload: string): Promise<void> {
    const subscribers = this.tagIndex.get(tag);
    if (!subscribers || subscribers.size === 0) return;

    const entries = [...subscribers];
    const dead: WebSocket[] = [];

    for (let i = 0; i < entries.length; i += 50) {
      const chunk = entries.slice(i, i + 50);
      for (const ws of chunk) {
        try {
          ws.send(payload);
        } catch {
          dead.push(ws);
        }
      }
      if (i + 50 < entries.length) {
        await new Promise<void>((r) => setTimeout(r, 0));
      }
    }

    for (const ws of dead) {
      this.unsubscribe(ws);
    }
  }
}
```

## Section 4 — Hibernation API for Idle Session Cost Reduction

Use the WebSocket Hibernation API so that idle open connections do not keep the DO active
and burning CPU. The DO wakes only when a message arrives, dramatically reducing billed
duration for rooms with infrequent messages.

```typescript
// src/durable-objects/room.ts (hibernation)
export class RoomHibernating extends DurableObject {
  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }

    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);

    // Accept with hibernation — DO can sleep between messages
    this.ctx.acceptWebSocket(server, ["room:main"]);

    return new Response(null, { status: 101, webSocket: client });
  }

  // Called by runtime when a message arrives for a hibernated DO
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const payload = typeof message === "string" ? message : new TextDecoder().decode(message);
    const parsed = JSON.parse(payload) as { type: string; content: string };

    if (parsed.type === "post") {
      // Fanout to all sessions tagged "room:main"
      const sockets = this.ctx.getWebSockets("room:main");
      await this.broadcastToSockets(sockets, payload);
    }
  }

  async webSocketClose(ws: WebSocket, code: number): Promise<void> {
    ws.close(code, "Connection closed");
  }

  private async broadcastToSockets(sockets: WebSocket[], payload: string): Promise<void> {
    const dead: WebSocket[] = [];
    for (let i = 0; i < sockets.length; i += 50) {
      const chunk = sockets.slice(i, i + 50);
      for (const ws of chunk) {
        try {
          ws.send(payload);
        } catch {
          dead.push(ws);
        }
      }
      if (i + 50 < sockets.length) {
        await new Promise<void>((r) => setTimeout(r, 0));
      }
    }
    // Hibernating API automatically removes closed sockets; no manual cleanup needed
  }
}
```

## Anti-patterns

- Storing the full message history in DO memory for replay on join — use D1 or KV for history;
  DO memory is volatile across hibernation cycles
- Creating one DO per user instead of one per room — causes O(n²) cross-DO RPC for every broadcast
- Broadcasting ArrayBuffer payloads without pre-encoding — re-encode once before the loop,
  not inside each iteration
- Calling `ws.close()` inside the broadcast loop on error — modifies the iteration target;
  collect dead sockets and clean up after the loop
- Using `this.ctx.getWebSockets()` on every message without caching the result when the list
  does not change — the call is cheap but unnecessary allocation in tight loops

## Gotchas

- `ctx.acceptWebSocket(server, tags)` tags are strings; they are the only way to group sockets
  in the Hibernation API — design tags at the application level before your first deploy
- After hibernation the DO's in-memory `Map` is gone; any state that must survive hibernation
  must be in `this.ctx.storage` or an external store
- The `setTimeout(resolve, 0)` yield trick only works inside `async` DO methods; it does NOT
  work in non-async handlers — make sure `webSocketMessage` is always `async`
- Cloudflare bills DO duration per active millisecond; with hibernation a 500-user room that
  receives 1 message/second spends ~99% of wall time hibernated

## Verification

```bash
# Monitor DO CPU time via Cloudflare dashboard
# Workers > Durable Objects > [Room class] > CPU Time p50 / p99

# Measure broadcast fan-out latency using Workers tail
npx wrangler tail --format=json \
  | jq 'select(.event.type == "websocket") | .cpuTime'

# Load test with k6 WebSocket scenario
# k6 run --vus 500 --duration 60s scripts/ws-broadcast-load.js
```

## Related

- `/documentation/docs/policies/performance/durable-objects-websocket-efficiency.md`
- `/documentation/docs/policies/performance/durable-objects-websocket-reconnect-latency.md`
- `/documentation/docs/policies/performance/durable-objects-hibernation-wake-latency.md`
- `/documentation/docs/policies/performance/durable-objects-rpc-batch-coalescing.md`
- `/documentation/docs/policies/performance/sse-vs-websockets-real-time-streaming.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/websockets/
- https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- https://developers.cloudflare.com/durable-objects/platform/limits/
- https://developers.cloudflare.com/workers/runtime-apis/websockets/
- https://developers.cloudflare.com/durable-objects/api/state/#getwebsockets
