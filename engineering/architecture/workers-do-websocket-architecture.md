# workers-do-websocket-architecture

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

Real-time features (chat, live cursors, collaborative editing) on
Cloudflare Workers need stateful connection management. Naive Worker
handlers lose WebSocket state between requests. Mobile clients
background the app and silently drop TCP, causing ghost connections
that are never cleaned up.

## Context

A Cloudflare Worker is stateless and isolates per-request. Durable
Objects (DOs) provide a single-threaded, in-memory actor colocated
with persistent storage. Each DO instance is the correct unit for
owning a WebSocket "room" or user session. The hibernation API
introduced in 2023 lets DOs shed memory cost while keeping WebSocket
connections open in the Cloudflare infrastructure layer, critical for
mobile clients that background frequently.

## 1. Single-Thread DO Model

Each DO runs one event loop thread. Concurrent WebSocket messages
are processed one at a time—no locking needed for in-memory state.
Design your room DO around this guarantee.

```typescript
// Room DO — one instance per channel/room ID
export class RoomDO implements DurableObject {
  private sessions = new Map<WebSocket, SessionMeta>();
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
    // Restore sessions the hibernation API re-activates
    this.state.getWebSockets().forEach((ws) => {
      const meta = ws.deserializeAttachment() as SessionMeta;
      this.sessions.set(ws, meta);
    });
  }

  async fetch(request: Request): Promise<Response> {
    const upgrade = request.headers.get("Upgrade");
    if (upgrade !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    // Use acceptWebSocket, not accept(), to opt in to hibernation
    this.state.acceptWebSocket(server);
    const meta: SessionMeta = { userId: getUserId(request) };
    server.serializeAttachment(meta);
    this.sessions.set(server, meta);
    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, msg: string | ArrayBuffer) {
    const meta = this.sessions.get(ws)!;
    // broadcast to all active sessions
    for (const [peer] of this.sessions) {
      if (peer !== ws && peer.readyState === WebSocket.READY_STATE_OPEN) {
        peer.send(JSON.stringify({ from: meta.userId, msg }));
      }
    }
  }

  async webSocketClose(ws: WebSocket, code: number) {
    this.sessions.delete(ws);
  }

  async webSocketError(ws: WebSocket) {
    this.sessions.delete(ws);
  }
}
```

## 2. Hibernation API for Mobile Background Reconnect

When the DO has no active JS execution, Cloudflare can hibernate it
to save memory without closing the underlying TCP connections. Mobile
clients backgrounding for 30–120 s survive without reconnect.

```
WITHOUT hibernation:          WITH hibernation:
─────────────────────         ────────────────────────
Client ──WS──► Worker DO      Client ──WS──► CF infra ─► DO (sleeping)
30 s idle → DO evicted         30 s idle → DO hibernates, WS held
Client gets close frame        Client wakes → DO revived, state restored
Mobile must reconnect          Mobile wakes → seamless, no reconnect
```

Key rules for hibernation compatibility:
- Call `state.acceptWebSocket(ws)` NOT `ws.accept()`
- Implement `webSocketMessage`, `webSocketClose`, `webSocketError`
  as class methods (not inside `fetch`)
- Serialize per-socket state with `ws.serializeAttachment()`
  (max 2 048 bytes per socket)
- Do NOT store WebSocket refs in closures outside the class

## 3. Connection State Machine

Track connection lifecycle explicitly to handle mobile edge cases.

```
CONNECTING ──► OPEN ──► CLOSING ──► CLOSED
     │           │
     │    ┌──────┴─────────┐
     │    │   HIBERNATED   │  ← mobile background
     │    └──────┬─────────┘
     │           │ wake
     └───────────┘ (re-enters OPEN via revived DO)
```

Client-side state machine (TypeScript):

```typescript
type ConnState = "connecting" | "open" | "closing" | "closed";

class ManagedSocket {
  private ws: WebSocket | null = null;
  private state: ConnState = "closed";
  private retryMs = 500;

  connect(url: string) {
    this.state = "connecting";
    this.ws = new WebSocket(url);
    this.ws.onopen = () => {
      this.state = "open";
      this.retryMs = 500; // reset backoff
    };
    this.ws.onclose = (ev) => {
      this.state = "closed";
      // 4xxx codes are app-level hard closes — don't retry
      if (ev.code < 4000) this.scheduleRetry(url);
    };
    this.ws.onerror = () => { /* handled by onclose */ };
  }

  private scheduleRetry(url: string) {
    setTimeout(() => this.connect(url), this.retryMs);
    this.retryMs = Math.min(this.retryMs * 2, 30_000);
  }
}
```

## 4. Geographic DO Placement

DOs are created in the data center that receives the first request,
then pinned there. For globally distributed users, choose the
jurisdiction explicitly.

| Strategy              | Use case                      | How                         |
|-----------------------|-------------------------------|-----------------------------|
| Default auto          | Single-region product         | First request wins          |
| `locationHint`        | Latency-sensitive rooms       | Pass hint on stub creation  |
| `jurisdiction: "eu"`  | GDPR-scoped data              | DO namespace binding config |
| ID-based sharding     | Large rooms → sub-room splits | Hash userId into sub-room   |

```typescript
// Worker routing — hint DO toward user's region
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const roomId = new URL(req.url).searchParams.get("room") ?? "default";
    // Deterministic stub — same ID always routes to same DO
    const id = env.ROOM.idFromName(roomId);
    const stub = env.ROOM.get(id, {
      locationHint: req.cf?.continent as string,
    });
    return stub.fetch(req);
  },
};
```

## 5. Scaling Considerations

```
Max sockets per DO instance   : no hard cap, ~1 000 practical
Max message size              : 1 MB
DO storage per instance       : 128 MB (keys), unlimited via R2
Hibernation wake latency      : ~5 ms p99
Serialized attachment limit   : 2 048 bytes per socket
```

For rooms exceeding ~500 concurrent users, shard into sub-rooms
keyed by `${roomId}:${shardIndex}` and relay between shards in the
root DO. This avoids serialization bottlenecks inside one event loop.

## Anti-Patterns

- **Using `ws.accept()` instead of `state.acceptWebSocket(ws)`** —
  disables hibernation; DO stays resident and billed even when idle.
- **Storing user counts in Worker KV** — KV is eventually consistent;
  use DO in-memory state for real-time presence counts.
- **Global WebSocket broadcast from a Worker** — Workers are stateless;
  you cannot share sockets across isolates without a DO hub.
- **Reconnect on every `visibilitychange` event** — causes thundering
  herd when millions of mobile clients return from background
  simultaneously; use jitter.

## Gotchas

- `ws.serializeAttachment()` is synchronous and overwrites any prior
  value; call it once with the complete meta object.
- Hibernation does not persist in-memory Map state; rebuild it in the
  constructor from `state.getWebSockets()`.
- The `webSocketMessage` handler must return a Promise or be async;
  throwing synchronously crashes the DO without calling `webSocketError`.
- DO alarm() can be used to prune stale sessions but fires after the DO
  wakes from hibernation, adding latency to the first message.
- `locationHint` is advisory — Cloudflare may ignore it if the region
  lacks capacity.

## Verification

```bash
# Confirm hibernation is active (no DO listed as active between msgs)
wrangler tail --format pretty | grep "DurableObject"

# End-to-end WebSocket smoke test
wscat -c wss://your-worker.example.com/ws?room=test
> {"type":"ping"}
< {"type":"pong"}

# Check socket count in DO storage
wrangler d1 execute ... # or use DO alarm to log session count
```

## Related

- `documentation/categories/architecture/chat-system-design.md`
- `documentation/categories/architecture/rate-limiting-architecture-workers.md`
- `documentation/categories/architecture/feature-flag-cloudflare-workers-kv.md`
- `documentation/categories/architecture/function-as-a-service-patterns.md`
- `documentation/categories/architecture/crdt-conflict-free-data-types.md`

## Source URLs

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/durable-objects/api/websockets/
- https://developers.cloudflare.com/durable-objects/reference/hibernatable-websocket-api/
- https://developers.cloudflare.com/workers/runtime-apis/websockets/
