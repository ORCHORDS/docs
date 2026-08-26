# WebSocket Chat Rooms with Durable Objects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need stateful, real-time WebSocket rooms where all clients in a room receive every message, the last N messages are persisted across reconnects, and idle rooms are automatically cleaned up — without running or scaling your own WebSocket server. Cloudflare Durable Objects give each room its own single-threaded JS instance with durable storage, and the hibernation WebSocket API keeps the DO alive only when messages are flowing.

---

## Context

A Durable Object (DO) is a globally unique, single-threaded actor. Each chat room is one DO instance identified by the room's slug. The hibernation API (`acceptWebSocket()` / `webSocketMessage()` / `webSocketClose()`) suspends the DO isolate between messages, eliminating per-connection billing for idle sockets while preserving all attached WebSocket objects. Broadcasting iterates `ctx.getWebSockets()` which returns all sockets the DO currently holds — even across hibernation cycles. The last 50 messages are persisted to `ctx.storage` (Durable Object Storage, a SQLite-backed KV) so late joiners see recent history. An alarm set on the first connection and reset on every message evicts rooms that have been empty for more than 10 minutes.

---

## Section 1 — Config / wrangler.toml

```toml
# wrangler.toml
name = "ws-rooms"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[durable_objects.bindings]]
name = "ROOMS"
class_name = "ChatRoom"

[[migrations]]
tag = "v1"
new_sqlite_classes = ["ChatRoom"]
```

---

## Section 2 — Durable Object: ChatRoom

```typescript
// src/chat-room.ts
import {
  DurableObject,
  DurableObjectState,
  WebSocket as CFWebSocket,
} from "cloudflare:workers";

const MAX_HISTORY = 50;
const IDLE_EVICT_MS = 10 * 60 * 1_000; // 10 minutes

interface Message {
  id: string;
  sender: string;
  text: string;
  ts: number;
}

interface SessionMeta {
  sender: string;
  joinedAt: number;
}

export class ChatRoom extends DurableObject {
  constructor(readonly ctx: DurableObjectState, readonly env: Record<string, unknown>) {
    super(ctx, env);
  }

  // --- WebSocket upgrade ---
  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }

    const url = new URL(request.url);
    const sender = url.searchParams.get("name") ?? "anonymous";

    const [client, server] = Object.values(new WebSocketPair()) as [WebSocket, WebSocket];

    // Attach metadata so we know who owns this socket during hibernation
    const meta: SessionMeta = { sender, joinedAt: Date.now() };
    this.ctx.acceptWebSocket(server, [JSON.stringify(meta)]);

    // Send last N messages to the new joiner
    const history = await this.getHistory();
    if (history.length > 0) {
      server.send(JSON.stringify({ type: "history", messages: history }));
    }

    // Broadcast join event to existing clients
    this.broadcast({ type: "join", sender, ts: Date.now() }, server);

    // Schedule eviction alarm if this is the first connection
    await this.rescheduleAlarm();

    return new Response(null, { status: 101, webSocket: client });
  }

  // --- Hibernation handlers ---
  async webSocketMessage(ws: WebSocket, raw: string | ArrayBuffer): Promise<void> {
    if (typeof raw !== "string") return; // ignore binary frames

    const meta = this.getSessionMeta(ws);
    let payload: { text: string };
    try {
      payload = JSON.parse(raw) as { text: string };
    } catch {
      ws.send(JSON.stringify({ type: "error", error: "Invalid JSON" }));
      return;
    }

    const msg: Message = {
      id: crypto.randomUUID(),
      sender: meta.sender,
      text: payload.text.slice(0, 2000), // max 2 KB per message
      ts: Date.now(),
    };

    // Persist to history
    await this.appendHistory(msg);

    // Broadcast to all sockets (including sender)
    this.broadcast({ type: "message", ...msg });

    // Reset idle alarm
    await this.rescheduleAlarm();
  }

  async webSocketClose(
    ws: WebSocket,
    code: number,
    reason: string,
    wasClean: boolean
  ): Promise<void> {
    const meta = this.getSessionMeta(ws);
    ws.close(code, "closing");
    this.broadcast({ type: "leave", sender: meta.sender, ts: Date.now() }, ws);

    // If the room is now empty, accelerate eviction to 30 s
    if (this.ctx.getWebSockets().length === 0) {
      await this.ctx.storage.setAlarm(Date.now() + 30_000);
    }
  }

  async webSocketError(ws: WebSocket, error: unknown): Promise<void> {
    console.error("WebSocket error:", error);
    ws.close(1011, "Internal error");
  }

  // --- Alarm: evict idle/empty rooms ---
  async alarm(): Promise<void> {
    const sockets = this.ctx.getWebSockets();
    if (sockets.length === 0) {
      // Clean up stored history for empty rooms
      await this.ctx.storage.delete("history");
      // The DO instance will be garbage-collected by the runtime
      return;
    }
    // Room still active — reschedule
    await this.rescheduleAlarm();
  }

  // --- Helpers ---
  private getSessionMeta(ws: WebSocket): SessionMeta {
    const tags = this.ctx.getTags(ws);
    try {
      return JSON.parse(tags[0] ?? "{\"sender\":\"unknown\",\"joinedAt\":0}") as SessionMeta;
    } catch {
      return { sender: "unknown", joinedAt: 0 };
    }
  }

  private broadcast(payload: unknown, exclude?: WebSocket): void {
    const data = JSON.stringify(payload);
    for (const ws of this.ctx.getWebSockets()) {
      if (ws === exclude) continue;
      try {
        ws.send(data);
      } catch {
        // Socket may have closed between getWebSockets() and send()
      }
    }
  }

  private async getHistory(): Promise<Message[]> {
    return (await this.ctx.storage.get<Message[]>("history")) ?? [];
  }

  private async appendHistory(msg: Message): Promise<void> {
    const history = await this.getHistory();
    history.push(msg);
    if (history.length > MAX_HISTORY) history.splice(0, history.length - MAX_HISTORY);
    await this.ctx.storage.put("history", history);
  }

  private async rescheduleAlarm(): Promise<void> {
    await this.ctx.storage.setAlarm(Date.now() + IDLE_EVICT_MS);
  }
}
```

---

## Section 3 — Gateway Worker routing to room DO

```typescript
// src/index.ts
import { ChatRoom } from "./chat-room";
export { ChatRoom };

export interface Env {
  ROOMS: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Expected path: /room/<slug>
    const match = url.pathname.match(/^\/room\/([a-z0-9_-]{1,64})$/i);
    if (!match) {
      return new Response(
        JSON.stringify({ error: "Path must be /room/<slug>" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    const slug = match[1].toLowerCase();
    const roomId = env.ROOMS.idFromName(slug);
    const room = env.ROOMS.get(roomId);

    // Forward the WebSocket upgrade request to the DO
    return room.fetch(request);
  },
};
```

---

## Anti-patterns

- **Using the legacy `handleWebSocket` pattern instead of hibernation** — Without `acceptWebSocket()`, the DO isolate stays alive (and billed) for the lifetime of every open connection; hibernation reduces cost to message-event CPU only.
- **Storing messages as individual KV keys per message** — Using `ctx.storage.put(msg.id, msg)` for each message makes history retrieval an unbounded list operation; a single `"history"` key with a capped array is simpler and cheaper.
- **Routing all rooms to a single DO instance** — Using a fixed DO name like `idFromName("global")` makes the entire chat system single-threaded; each room must be its own DO instance.
- **Not catching errors in `broadcast()`** — A closed socket throws on `send()`; failing to catch it kills the broadcast loop and silently drops messages to all remaining clients.

---

## Gotchas

- `ctx.acceptWebSocket()` can only be called once per server-side WebSocket; calling it a second time throws. Use `ctx.getWebSockets()` to check if a socket is already accepted.
- The `tags` array passed to `acceptWebSocket()` is serialised and survives hibernation; keep tag data small (< 2 KB total across all tags for the DO).
- `setAlarm()` replaces the existing alarm — there is only one alarm slot per DO. To reset the idle timer, call `setAlarm` with the new absolute timestamp.
- WebSocket messages received during hibernation wake the isolate; the first call to `webSocketMessage` after a long idle may take ~5 ms to warm up.
- `new WebSocketPair()` returns a plain object, not an array; use `Object.values()` to destructure the pair as shown above.
- D1 is not available inside Durable Object `fetch()` in the free plan; use Durable Object Storage (`ctx.storage`) for all persistence within a room.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Connect two WebSocket clients to the same room
# Terminal 1
wscat -c 'wss://ws-rooms.example.workers.dev/room/test-room?name=alice'

# Terminal 2
wscat -c 'wss://ws-rooms.example.workers.dev/room/test-room?name=bob'

# In Terminal 1, send a message
{"text": "hello from alice"}
# Terminal 2 should receive: {"type":"message","sender":"alice","text":"hello from alice",...}

# Reconnect Terminal 1 after closing — should receive history
wscat -c 'wss://ws-rooms.example.workers.dev/room/test-room?name=alice'
# Expected: {"type":"history","messages":[...]}

# Inspect DO storage via wrangler (local dev)
npx wrangler durable-object storage get --namespace ROOMS --id <room-id>
```

---

## Related

- `workers-service-bindings-internal-api.md`
- `cloudflare-d1-time-series-analytics.md`

---

## Sources

- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Durable Objects WebSocket Hibernation API — https://developers.cloudflare.com/durable-objects/api/websockets/
- Durable Objects Alarms — https://developers.cloudflare.com/durable-objects/api/alarms/
