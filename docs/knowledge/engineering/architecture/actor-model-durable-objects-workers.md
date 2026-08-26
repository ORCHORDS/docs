# Actor Model with Durable Objects and Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need to model independent stateful entities—game rooms, user sessions, IoT devices, per-tenant rate limiters—that receive messages, mutate local state, and send messages to other actors without shared-memory contention. Coordinating this with a central database creates lock contention and latency spikes that erode real-time guarantees.

## Context

The actor model treats each stateful unit as an isolated process with a private mailbox. Cloudflare Durable Objects map naturally onto actors: each object has a single-threaded execution context, persistent storage, and a stable identity addressable by name or ID. Workers serve as the thin routing layer that locates the correct actor and forwards requests. This gives you per-entity consistency without a global lock, and Cloudflare's infrastructure handles placement, failover, and colocation transparently.

## Defining the Actor Interface

Every actor in this pattern exposes a `receive` method that handles typed messages. The Durable Object enforces single-threaded execution, so handlers run serially—no mutex needed.

```typescript
// src/actors/game-room.ts
export interface RoomMessage {
  type: "join" | "leave" | "move" | "chat";
  playerId: string;
  payload?: unknown;
}

export class GameRoomActor implements DurableObject {
  private state: DurableObjectState;
  private players: Map<string, WebSocket> = new Map();
  private history: RoomMessage[] = [];

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const msg: RoomMessage = await request.json();
    return this.receive(msg);
  }

  private async receive(msg: RoomMessage): Promise<Response> {
    switch (msg.type) {
      case "join":
        await this.state.storage.put(`player:${msg.playerId}`, { joinedAt: Date.now() });
        this.broadcast({ type: "join", playerId: msg.playerId });
        break;
      case "leave":
        await this.state.storage.delete(`player:${msg.playerId}`);
        this.players.delete(msg.playerId);
        this.broadcast({ type: "leave", playerId: msg.playerId });
        break;
      case "move":
        this.history.push(msg);
        await this.state.storage.put("history", this.history.slice(-100));
        this.broadcast(msg);
        break;
    }
    return new Response(JSON.stringify({ ok: true }));
  }

  private broadcast(msg: RoomMessage): void {
    const encoded = JSON.stringify(msg);
    for (const [id, ws] of this.players) {
      try {
        ws.send(encoded);
      } catch {
        this.players.delete(id);
      }
    }
  }
}
```

## Routing Workers as Actor Supervisors

The Worker acts as a lightweight supervisor: it resolves actor identity, forwards messages, and handles failures by retrying or spawning new actors. Name-based addressing ensures the same logical entity always maps to the same Durable Object instance.

```typescript
// src/worker.ts
interface Env {
  GAME_ROOM: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const roomId = url.searchParams.get("roomId");
    if (!roomId) {
      return new Response("Missing roomId", { status: 400 });
    }

    // Name-based addressing: same roomId → same actor instance
    const id = env.GAME_ROOM.idFromName(roomId);
    const stub = env.GAME_ROOM.get(id);

    // Forward with location hint for colocation
    return stub.fetch(request);
  },
} satisfies ExportedHandler<Env>;
```

## Actor-to-Actor Messaging via Service Bindings

Actors can send messages to other actors by obtaining their stub and calling fetch. Use fire-and-forget for non-critical notifications and await for state-affecting calls that require confirmation.

```typescript
// Inside an actor that needs to notify another actor
async function notifyLeaderboard(
  env: Env,
  playerId: string,
  score: number
): Promise<void> {
  const lbId = env.LEADERBOARD.idFromName("global");
  const lb = env.LEADERBOARD.get(lbId);

  // Awaited: we need confirmation before updating local state
  const res = await lb.fetch(
    new Request("https://internal/score", {
      method: "POST",
      body: JSON.stringify({ playerId, score }),
    })
  );

  if (!res.ok) {
    throw new Error(`Leaderboard rejected score: ${res.status}`);
  }
}
```

## Anti-patterns

- Using a single Durable Object as a global message broker defeats the actor model's isolation guarantee and creates a hot partition.
- Storing actor references as serialised strings—always resolve them via `idFromName` or `idFromString` to maintain location transparency.
- Blocking an actor's event loop with synchronous CPU-heavy computation; offload to a Worker or use `ctx.waitUntil` for background work.

## Gotchas

- Durable Object hibernation flushes in-memory state; always persist critical fields to `state.storage` before returning from `fetch`.
- `idFromName` hashes the string—two different strings that look the same to your code (e.g., different encodings) produce different actors; normalise keys before resolution.

## Verification

```bash
# Send a join message to a named room actor
curl -X POST "https://your-worker.workers.dev/?roomId=room-42" \
  -H "Content-Type: application/json" \
  -d '{"type":"join","playerId":"alice"}'

# Confirm player was persisted in the actor's storage
# (use wrangler tail to inspect logs)
wrangler tail --format pretty
```

## Related

- `architecture/competing-consumers-durable-objects.md`
- `architecture/workers-do-websocket-architecture.md`
- `architecture/durable-object-alarm-api-scheduled-retry.md`
- `architecture/multi-region-active-active-durable-objects.md`

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-from-a-worker/
- https://en.wikipedia.org/wiki/Actor_model
