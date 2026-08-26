# Durable Objects — Real-Time State and Multiplayer Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your real-time application (collaborative editor, multiplayer game, live
dashboard) needs to coordinate state across multiple connected clients.
Traditional approaches require a centralized server, a database for
persistence, and a pub/sub system for broadcasting — three infrastructure
layers that add latency, cost, and operational complexity. You need
exactly-once state mutations with no race conditions, but distributed
locks and consensus algorithms are hard to implement correctly.

## Context

Cloudflare Durable Objects (DOs) provide a globally unique, single-
threaded, stateful compute primitive at the edge. Each Durable Object
has a unique ID, runs in exactly one location at a time (singleton
guarantee), and has its own embedded SQLite storage that survives
crashes, deployments, and migrations. In 2026, Durable Objects power
real-time applications through the Agents SDK (built on DOs),
WebSocket hibernation for cost-efficient connections, and automatic
SQLite-backed persistence. Cloudflare's acquisition of PartyKit brought
multiplayer-first abstractions (rooms, presence, CRDT sync) into the
platform.

## Durable Objects architecture

```
Client A ──WebSocket──►┐
Client B ──WebSocket──►├─► Durable Object (singleton)
Client C ──WebSocket──►┘      │
                              ├── In-memory state (single-threaded)
                              ├── SQLite storage (persistent)
                              └── Alarm (scheduled wake-up)

Key guarantees:
  • Exactly one instance per unique ID (no race conditions)
  • Single-threaded execution (no concurrent mutations)
  • Automatic placement near first requester
  • Storage survives crashes and redeployments
```

## Basic Durable Object

```typescript
export class ChatRoom {
  private sessions: Map<WebSocket, { name: string }> = new Map();
  private sql: SqlStorage;

  constructor(private state: DurableObjectState, env: Env) {
    this.sql = state.storage.sql;
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp INTEGER NOT NULL
      )
    `);
  }

  async fetch(request: Request): Promise<Response> {
    const { 0: client, 1: server } = new WebSocketPair();

    this.state.acceptWebSocket(server);
    const name = new URL(request.url).searchParams.get("name") ?? "anon";
    server.serializeAttachment({ name });

    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, message: string) {
    const { name } = ws.deserializeAttachment();
    const data = JSON.parse(message);

    this.sql.exec(
      "INSERT INTO messages (sender, content, timestamp) VALUES (?, ?, ?)",
      name, data.content, Date.now()
    );

    for (const socket of this.state.getWebSockets()) {
      socket.send(JSON.stringify({
        sender: name,
        content: data.content,
      }));
    }
  }

  async webSocketClose(ws: WebSocket) {
    ws.close();
  }
}
```

## WebSocket Hibernation

```typescript
export class EfficientRoom {
  constructor(private state: DurableObjectState) {}

  async fetch(request: Request): Promise<Response> {
    const { 0: client, 1: server } = new WebSocketPair();
    this.state.acceptWebSocket(server);
    return new Response(null, { status: 101, webSocket: client });
  }

  // Called only when a message arrives — DO sleeps between messages
  async webSocketMessage(ws: WebSocket, message: string) {
    // Process message, broadcast to others
    for (const socket of this.state.getWebSockets()) {
      if (socket !== ws) {
        socket.send(message);
      }
    }
  }

  async webSocketClose(ws: WebSocket) {
    ws.close();
  }
}
// With hibernation, you pay only for active processing time,
// not for idle WebSocket connections.
```

## Patterns

### Room-based multiplayer

```
Each room = one Durable Object
  → Room ID derived from game/document/channel ID
  → All clients in a room connect to the same DO
  → Single-threaded: no race conditions on state mutations
  → SQLite: persistent game state / document history
```

### Presence tracking

```typescript
async webSocketMessage(ws: WebSocket, message: string) {
  const data = JSON.parse(message);

  if (data.type === "cursor") {
    // Broadcast cursor position to all other clients
    for (const socket of this.state.getWebSockets()) {
      if (socket !== ws) {
        socket.send(JSON.stringify({
          type: "cursor",
          userId: ws.deserializeAttachment().userId,
          x: data.x,
          y: data.y,
        }));
      }
    }
  }
}
```

### Scheduled alarms

```typescript
export class GameLobby {
  async alarm() {
    // Called at the scheduled time — even if no clients are connected
    const state = await this.state.storage.get("gameState");
    if (state === "waiting" && this.state.getWebSockets().length >= 2) {
      this.startGame();
    }
  }

  async startCountdown() {
    // Schedule alarm 30 seconds from now
    await this.state.storage.setAlarm(Date.now() + 30_000);
  }
}
```

## Anti-patterns

- **One DO per user** — creating a Durable Object for every connected
  user. DOs are designed for shared state (rooms, documents, games).
  Use a single DO per logical group and fan out connections to it.
- **Storing large blobs in DO storage** — Durable Object storage is
  optimized for small, frequent reads/writes (state, metadata). Store
  large files in R2 and keep references in DO storage.
- **Polling instead of WebSockets** — using HTTP polling to check for
  updates from a DO. Use WebSockets with hibernation for real-time
  updates at minimal cost.
- **Unbounded connection growth** — allowing unlimited clients per DO
  without backpressure. A single DO runs single-threaded; too many
  connections degrade broadcast performance. Shard rooms at ~1,000
  concurrent connections.

## Gotchas

- **Single-region execution** — a DO runs in one Cloudflare location.
  Clients far from that location experience higher latency. DOs
  automatically place near the first requester, but subsequent
  clients may be distant. Use DO location hints for predictable
  placement.
- **Cold start after hibernation** — a hibernated DO must reload
  state from storage when it wakes up. Keep critical state in SQLite
  and rebuild in-memory caches in the constructor.
- **Storage limits** — DO SQLite storage has a 1GB limit per object.
  For applications that grow beyond this, shard state across multiple
  DOs by partition key.
- **No inter-DO communication** — Durable Objects cannot directly
  communicate with each other. Use a Worker as an intermediary to
  coordinate between DOs (e.g., matchmaking across game lobbies).

## Verification

- Each logical room/channel/document maps to exactly one DO.
- WebSocket hibernation is enabled for cost efficiency.
- SQLite storage persists critical state across restarts.
- Broadcast fan-out handles 1,000+ concurrent connections per DO.
- Alarms are used for scheduled tasks instead of external cron.
- DO placement is tested for latency-sensitive use cases.

## Related

- `documentation/docs/policies/cloudflare/workers-ai-edge-inference.md`
- `documentation/docs/policies/cloudflare/pages-deployment-patterns.md`
- `documentation/docs/policies/architecture/event-sourcing-cqrs-patterns.md`

## Source URLs (verified 2026-08-16)

- Stateful AI Agents with Cloudflare Durable Objects — https://multiwaresolutions.com/blog/cloudflare-agents-durable-objects-2026
- Durable Objects Architecture Guide — https://architectingoncloudflare.com/chapter-06/
- What are Durable Objects (Cloudflare docs) — https://developers.cloudflare.com/durable-objects/concepts/what-are-durable-objects/
- Cloudflare acquires PartyKit — https://blog.cloudflare.com/cloudflare-acquires-partykit
