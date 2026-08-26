# Mediator Pattern: Durable Objects + Workers Coordination

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Multiple independent Workers need to communicate and share transient state — e.g., a collaborative whiteboard, a live auction, or a multi-player game room — but direct Worker-to-Worker coupling makes the topology fragile and hard to reason about. You need a single, authoritative coordination hub that receives all participant messages, enforces ordering, and fans out state updates without any participant knowing about the others.

## Context

The Mediator pattern removes direct dependencies between components (colleagues) by routing all interactions through a central mediator. In Cloudflare's model, a Durable Object is a perfect fit: it has a single-threaded execution model, persistent storage, built-in WebSocket hibernation support, and a stable, addressable identity derived from a room or session key. Each participant Worker opens a WebSocket connection to the Durable Object; the DO acts as the mediator, processing events from one participant and broadcasting the result to all others. No participant holds a reference to any other.

## Durable Object Mediator

```typescript
// durable-objects/RoomMediator.ts
import { DurableObject } from "cloudflare:workers";

interface Participant {
  socket: WebSocket;
  userId: string;
  joinedAt: number;
}

interface RoomEvent {
  type: "JOIN" | "LEAVE" | "ACTION" | "SYNC_REQUEST";
  userId: string;
  payload?: unknown;
}

interface RoomState {
  items: Record<string, unknown>;
  version: number;
}

export class RoomMediator extends DurableObject {
  private participants = new Map<string, Participant>();
  private state: RoomState = { items: {}, version: 0 };

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    // Restore durable state on cold start
    this.ctx.blockConcurrencyWhile(async () => {
      this.state = (await this.ctx.storage.get<RoomState>("roomState")) ?? {
        items: {},
        version: 0,
      };
    });
  }

  async fetch(request: Request): Promise<Response> {
    const upgrade = request.headers.get("Upgrade");
    if (upgrade !== "websocket") {
      return new Response("Expected WebSocket upgrade", { status: 426 });
    }

    const url = new URL(request.url);
    const userId = url.searchParams.get("userId");
    if (!userId) return new Response("Missing userId", { status: 400 });

    const [client, server] = Object.values(new WebSocketPair()) as [WebSocket, WebSocket];
    this.ctx.acceptWebSocket(server, [userId]);

    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const tags = this.ctx.getTags(ws);
    const userId = tags[0];

    let event: RoomEvent;
    try {
      event = JSON.parse(message as string) as RoomEvent;
    } catch {
      ws.send(JSON.stringify({ error: "Invalid JSON" }));
      return;
    }

    await this.handleEvent(userId, event, ws);
  }

  async webSocketClose(ws: WebSocket, code: number): Promise<void> {
    const tags = this.ctx.getTags(ws);
    const userId = tags[0];
    this.participants.delete(userId);
    this.broadcast({ type: "LEAVE", userId }, userId);
  }

  private async handleEvent(
    userId: string,
    event: RoomEvent,
    ws: WebSocket
  ): Promise<void> {
    switch (event.type) {
      case "JOIN": {
        this.participants.set(userId, { socket: ws, userId, joinedAt: Date.now() });
        // Send current state snapshot to the new joiner
        ws.send(JSON.stringify({ type: "SNAPSHOT", state: this.state }));
        this.broadcast({ type: "JOIN", userId }, userId);
        break;
      }

      case "ACTION": {
        // Mediator applies the action and increments version
        this.state = {
          items: { ...this.state.items, ...(event.payload as Record<string, unknown>) },
          version: this.state.version + 1,
        };
        await this.ctx.storage.put("roomState", this.state);
        // Broadcast enriched event with new version to ALL participants including sender
        this.broadcast({ type: "ACTION", userId, payload: { ...event.payload, version: this.state.version } });
        break;
      }

      case "SYNC_REQUEST": {
        ws.send(JSON.stringify({ type: "SNAPSHOT", state: this.state }));
        break;
      }
    }
  }

  private broadcast(event: unknown, excludeUserId?: string): void {
    const message = JSON.stringify(event);
    for (const [uid, participant] of this.participants) {
      if (uid === excludeUserId) continue;
      try {
        participant.socket.send(message);
      } catch {
        this.participants.delete(uid);
      }
    }
  }
}
```

## Gateway Worker

```typescript
// worker.ts — routes clients to the correct RoomMediator instance
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const roomId = url.pathname.split("/")[2]; // /rooms/:roomId/ws

    if (!roomId) return new Response("Missing room id", { status: 400 });

    // All participants for the same roomId land on the same DO instance
    const id = env.ROOM_MEDIATOR.idFromName(roomId);
    const stub = env.ROOM_MEDIATOR.get(id);

    return stub.fetch(request);
  },
};
```

## Alarm-Based Idle Cleanup

```typescript
// Inside RoomMediator — evict empty rooms after 30 minutes of inactivity
async webSocketClose(): Promise<void> {
  if (this.participants.size === 0) {
    await this.ctx.storage.setAlarm(Date.now() + 30 * 60 * 1000);
  }
}

async alarm(): Promise<void> {
  if (this.participants.size === 0) {
    await this.ctx.storage.deleteAll();
  }
}
```

## Anti-patterns

- Letting participants call each other's DO stubs directly — this reintroduces coupling and bypasses the mediator's ordering guarantee.
- Storing unbounded participant history in DO storage; prefer append-only event logs with a projection to the current state snapshot.
- Performing expensive I/O (e.g., calling an external API) inside `webSocketMessage` without `ctx.waitUntil`; it blocks all other messages to that DO.

## Gotchas

- Durable Object WebSocket hibernation (`acceptWebSocket`) survives DO eviction; the `webSocketMessage` handler is re-invoked on the next message. In-memory `participants` map is rebuilt lazily — you must re-register participant metadata on the first message after a cold wake.
- `getTags` on a hibernated socket only returns the tags set at `acceptWebSocket` time; do not rely on in-memory maps for identity across hibernation boundaries.

## Verification

```bash
# Connect two clients and verify broadcast
wscat -c "wss://api.example.com/rooms/room-42/ws?userId=alice"
# In a second terminal
wscat -c "wss://api.example.com/rooms/room-42/ws?userId=bob"

# Alice sends JOIN, verify bob receives the event
# Check DO storage
wrangler durable-objects inspect --name ROOM_MEDIATOR
```

## Related

- `architecture/pubsub-durable-objects-websocket-broadcast.md`
- `architecture/actor-model-durable-objects-workers.md`
- `architecture/competing-consumers-durable-objects.md`
- `architecture/workers-do-websocket-architecture.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/websockets/
- https://refactoring.guru/design-patterns/mediator
- https://developers.cloudflare.com/durable-objects/api/alarms/
