# Cloudflare Durable Objects WebSocket Connection Sharding and Per-Instance Limits

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A real-time collaboration feature routes all connections for a "room" to a single Durable
Object. After launch, large rooms (conference calls, live events) exceed ~32,000 concurrent
WebSocket connections per DO instance and connections start being refused. The team needs
a sharding strategy that preserves room-level message fan-out without hitting per-instance
limits.

## Context

A Cloudflare Durable Object instance is a single-threaded V8 isolate. While DO supports
WebSocket Hibernation (connections survive across sleeps), there are practical upper bounds
per instance:

| Resource | Limit |
|---|---|
| Active WebSocket connections | ~32,000 (practical; no hard-coded cap but memory-bound) |
| Memory per instance | 128 MB |
| Hibernated connections | ~100,000+ (serialized metadata only; socket handled by CF infra) |
| Concurrent `fetch()` invocations | No concurrency — requests queue serially |

For rooms expecting > ~5,000 simultaneous viewers, a single DO becomes a bottleneck.
Sharding splits connections across multiple DO instances while a **coordinator DO**
maintains authoritative room state.

---

## Sharding Architecture

```
Client → Worker → ShardRouter (Worker logic) → Shard-DO-{roomId}-{shardN}
                                          ↕
                                  Coordinator-DO-{roomId}
```

- **Shard DOs** hold WebSocket connections; they fan out messages to local sockets and
  forward broadcasts to the Coordinator.
- **Coordinator DO** holds authoritative state (participant list, room metadata) and
  relays broadcasts to all shards.

---

## Worker: Routing to Shards

```ts
interface Env {
  SHARD: DurableObjectNamespace;
  COORDINATOR: DurableObjectNamespace;
}

function shardId(roomId: string, connectionCount: number): string {
  // Assign shard based on connection count ranges
  // Each shard holds up to SHARD_CAPACITY connections
  const SHARD_CAPACITY = 4_000;
  const shardIndex = Math.floor(connectionCount / SHARD_CAPACITY);
  return `${roomId}-shard-${shardIndex}`;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const roomId = url.searchParams.get('room');
    if (!roomId) return new Response('Missing room', { status: 400 });

    if (req.headers.get('Upgrade') !== 'websocket') {
      return new Response('WebSocket required', { status: 426 });
    }

    // Ask the coordinator how many connections the room currently has
    const coordStub = env.COORDINATOR.get(
      env.COORDINATOR.idFromName(roomId)
    );
    const countRes = await coordStub.fetch(
      new Request(`https://do/connection-count`)
    );
    const { count } = await countRes.json<{ count: number }>();

    // Route to the appropriate shard
    const sid = shardId(roomId, count);
    const shardStub = env.SHARD.get(env.SHARD.idFromName(sid));
    return shardStub.fetch(req);
  },
};
```

---

## Shard Durable Object

```ts
import { DurableObject } from 'cloudflare:workers';

export class ShardDO extends DurableObject {
  private sessions = new Map<string, WebSocket>();

  async fetch(req: Request): Promise<Response> {
    const { 0: client, 1: server } = new WebSocketPair();
    this.ctx.acceptWebSocket(server);

    const sessionId = crypto.randomUUID();
    this.ctx.setWebSocketAutoResponse(
      new WebSocketRequestResponsePair('ping', 'pong')
    );
    server.serializeAttachment({ sessionId });

    return new Response(null, {
      status: 101,
      webSocket: client,
    });
  }

  webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): void {
    // Broadcast to all local connections on this shard
    for (const [, socket] of this.sessions) {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(message);
      }
    }
  }

  webSocketClose(ws: WebSocket, code: number): void {
    const { sessionId } = ws.deserializeAttachment() as { sessionId: string };
    this.sessions.delete(sessionId);
  }

  // Called by Coordinator to broadcast a message to all shard connections
  async broadcast(msg: string): Promise<void> {
    for (const ws of this.ctx.getWebSockets()) {
      if (ws.readyState === WebSocket.OPEN) ws.send(msg);
    }
  }
}
```

---

## Coordinator Durable Object

```ts
import { DurableObject } from 'cloudflare:workers';

interface Env {
  SHARD: DurableObjectNamespace;
}

export class CoordinatorDO extends DurableObject {
  private shards = new Set<string>();
  private totalConnections = 0;

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === '/connection-count') {
      return Response.json({ count: this.totalConnections });
    }

    if (url.pathname === '/register-shard') {
      const { shardName } = await req.json<{ shardName: string }>();
      this.shards.add(shardName);
      this.totalConnections++;
      return Response.json({ ok: true });
    }

    if (url.pathname === '/broadcast') {
      const msg = await req.text();
      // Fan-out to all shards in parallel
      await Promise.allSettled(
        [...this.shards].map((shardName) => {
          const stub = (this.env as Env).SHARD.get(
            (this.env as Env).SHARD.idFromName(shardName)
          );
          return stub.fetch(
            new Request('https://do/broadcast', {
              method: 'POST',
              body: msg,
            })
          );
        })
      );
      return Response.json({ ok: true });
    }

    return new Response('Not found', { status: 404 });
  }
}
```

---

## Hibernation and Memory Management

Always use Hibernation API (`ctx.acceptWebSocket`) instead of keeping an explicit
`sessions: Map` in memory across hibernation cycles. The map is lost on hibernation; use
`ws.serializeAttachment()` to persist per-connection metadata:

```ts
// Store metadata that survives hibernation
server.serializeAttachment({
  userId: req.headers.get('x-user-id'),
  joinedAt: Date.now(),
  shardName: sid,
});

// Recover on re-activation
webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): void {
  const meta = ws.deserializeAttachment<{ userId: string; shardName: string }>();
  console.log(`Message from ${meta.userId} on shard ${meta.shardName}`);
}
```

---

## Anti-patterns

- Storing all connections in a `Map<string, WebSocket>` in the DO class body — the map
  is lost when the DO hibernates; use `ctx.getWebSockets()` to enumerate live sockets.
- Using sequential shard assignment (round-robin per connection) instead of capacity-based
  — round-robin may fill multiple shards unevenly; capacity-based packing minimises
  shard count.
- Broadcasting by iterating `this.sessions` inside `webSocketMessage` — this blocks the
  DO's single thread; for large fan-outs, use `ctx.getWebSockets()` with `ws.send()` in
  a tight loop (no async await inside the loop).
- Creating one shard per client — DO cold starts are ~2-5 ms but creating thousands of
  DOs adds name-resolution overhead; target 500–4000 connections per shard.

---

## Gotchas

- `ctx.getWebSockets()` returns all hibernated **and** active sockets; check
  `ws.readyState === WebSocket.OPEN` before sending.
- A DO instance is pinned to a single Cloudflare data centre; shards for the same room
  may end up in different data centres if name-based routing hashes differently — this
  adds cross-region RPC latency on coordinator fan-out.
- `serializeAttachment` data is limited to 2 KB; don't store large payloads (e.g. full
  JWT) — store only the session ID and look up the rest in KV.
- Shard DOs that receive no new connections (room is draining) will eventually hibernate
  and lose the ability to initiate broadcasts; the Coordinator must drive all fan-out.
- WebSocket messages received during hibernation are queued and delivered after
  re-activation; large backlogs can spike CPU on the first request after hibernation.

---

## Verification

```bash
# Count active WebSockets per shard DO via a custom /stats endpoint
for SHARD in 0 1 2 3; do
  curl -s "https://api.example.com/admin/shard/${SHARD}/stats" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" | jq '{shard: "'"$SHARD"'", connections: .count}'
done

# Verify coordinator shard registry is consistent
curl -s "https://api.example.com/admin/coordinator/room123/shards" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" | jq '.'
```

---

## Related

- `durable-objects-websocket-hibernation.md`
- `durable-objects-websocket-mobile-reconnect.md`
- `durable-objects-best-practices.md`
- `durable-objects-real-time-state.md`
- `workers-rpc-service-binding-patterns.md`

---

## Sources

- https://developers.cloudflare.com/durable-objects/api/websockets/
- https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- https://developers.cloudflare.com/durable-objects/reference/limits/
- https://blog.cloudflare.com/durable-objects-easy-fast-correct/
