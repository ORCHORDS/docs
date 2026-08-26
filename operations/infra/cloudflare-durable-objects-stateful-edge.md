# Cloudflare Durable Objects: Stateful Edge Computing Patterns

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

## Symptom

A Cloudflare Worker serving a real-time feature — collaborative editing, live presence,
a rate limiter that must be consistent globally, a WebSocket chat room — hits the fundamental
limitation of stateless compute: each request is isolated, there is no shared memory, and
coordinating state via external databases introduces latency that destroys the real-time
experience. A KV write takes ~60ms and only achieves eventual consistency. A D1 query via
the SQLite remote protocol adds a round-trip. Latency SLOs of <10ms for real-time state
updates cannot be met with remote storage alone.

## Context

Durable Objects (DOs) solve exactly this problem. Each DO is a JavaScript/TypeScript class
instance that:
- Has a single-writer guarantee — only one instance of a given DO ID runs globally at a time
- Runs co-located with the requests that target it (Cloudflare routes to the nearest data
  centre running the object)
- Has access to a transactional key-value storage API (`this.ctx.storage`) that persists
  across DO hibernation
- Can hold WebSocket connections open indefinitely using the WebSocket Hibernation API
- Supports an Alarm API for scheduled work within the object

DOs are not caches and not databases. They are a coordination primitive — the right tool
when you need serialized, low-latency, stateful coordination between concurrent requests.

---

## Section 1: Object Model and Routing

A DO class is exported from a Worker and bound in `wrangler.toml`. Requests are routed to
an instance by a string ID or by name.

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[durable_objects.bindings]]
name = "CHAT_ROOM"
class_name = "ChatRoom"

[[migrations]]
tag = "v1"
new_classes = ["ChatRoom"]
```

```typescript
// src/index.ts
import { ChatRoom } from './ChatRoom';
export { ChatRoom };

export interface Env {
  CHAT_ROOM: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const roomId = url.searchParams.get('room');
    if (!roomId) {
      return new Response('Missing room', { status: 400 });
    }

    // Route to a named DO instance — all requests with roomId="general"
    // will hit the same instance globally
    const id = env.CHAT_ROOM.idFromName(roomId);
    const stub = env.CHAT_ROOM.get(id);

    return stub.fetch(request);
  },
};
```

ID strategies:

| Strategy | Method | Use case |
|---|---|---|
| Named (deterministic) | `idFromName("string")` | Chat rooms, user sessions, rate limiters |
| Random (unique) | `newUniqueId()` | Document instances, ephemeral game sessions |
| Parsed (from string) | `idFromString(hexStr)` | Restoring a serialized ID across requests |

Routing guarantee: `idFromName` is a SHA-256 hash of the name scoped to the DO class.
All callers using the same name hit the same shard globally.

---

## Section 2: Storage API and Transactional Patterns

`this.ctx.storage` is a key-value store that persists across hibernation. Reads and writes
are serialized — within a single DO instance, you cannot have concurrent storage mutations.

```typescript
export class RateLimiter implements DurableObject {
  private state: DurableObjectState;
  private readonly windowMs = 60_000; // 1 minute
  private readonly limit = 100;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const now = Date.now();
    const key = `window:${Math.floor(now / this.windowMs)}`;

    // storage.transaction() groups reads+writes into an atomic operation
    const allowed = await this.state.storage.transaction(async (txn) => {
      const current = (await txn.get<number>(key)) ?? 0;
      if (current >= this.limit) return false;
      await txn.put(key, current + 1);
      // Clean up old windows
      const oldKey = `window:${Math.floor(now / this.windowMs) - 2}`;
      await txn.delete(oldKey);
      return true;
    });

    if (!allowed) {
      return new Response('Rate limited', { status: 429 });
    }
    return new Response('OK');
  }
}
```

Storage operation costs (as of 2026):
- **List**: 1 unit per 1000 keys listed
- **Get/Put/Delete**: 1 unit each (counted at 1M operations per month on the paid tier)
- Storage at rest: $0.20/GB-month (Durable Objects plan)

Transactional guarantees:
- Within a single DO: serialized, consistent
- Across multiple DOs: no cross-object transactions exist — use application-level sagas or
  idempotency keys

---

## Section 3: WebSocket Hibernation API

The WebSocket Hibernation API allows a DO to accept WebSocket connections and sleep between
messages — only waking when a message arrives. This is critical for cost: a hibernating DO
costs nothing, while an active DO costs CPU time.

```typescript
export class ChatRoom implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const upgradeHeader = request.headers.get('Upgrade');
    if (upgradeHeader !== 'websocket') {
      return new Response('Expected WebSocket', { status: 426 });
    }

    // Create a WebSocket pair
    const [client, server] = Object.values(new WebSocketPair());

    // Accept using the hibernation API — DO can sleep between messages
    this.state.acceptWebSocket(server);

    // Attach metadata to the socket for identification
    server.serializeAttachment({ userId: new URL(request.url).searchParams.get('user') });

    return new Response(null, { status: 101, webSocket: client });
  }

  // Called by the runtime when a message arrives on any accepted WebSocket
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const { userId } = ws.deserializeAttachment() as { userId: string };
    const text = typeof message === 'string' ? message : new TextDecoder().decode(message);

    const payload = JSON.stringify({ from: userId, text, ts: Date.now() });

    // Broadcast to all active connections in this room
    const sockets = this.state.getWebSockets();
    for (const socket of sockets) {
      try {
        socket.send(payload);
      } catch {
        // Socket already closed — the runtime cleans it up
      }
    }

    // Persist last 100 messages to storage
    await this.state.storage.transaction(async (txn) => {
      const history: string[] = (await txn.get('history')) ?? [];
      history.push(payload);
      if (history.length > 100) history.shift();
      await txn.put('history', history);
    });
  }

  async webSocketClose(ws: WebSocket, code: number, reason: string): Promise<void> {
    ws.close(code, 'Closing');
  }

  async webSocketError(ws: WebSocket, error: unknown): Promise<void> {
    ws.close(1011, 'Internal error');
  }
}
```

Key hibernation behaviour:
- When no WebSocket messages are in flight and no alarms are pending, the DO hibernates
- Runtime serialises in-flight state automatically
- `this.state.getWebSockets()` returns connections that survived hibernation — the client
  does not need to reconnect
- Maximum 32,000 concurrent WebSocket connections per DO instance

---

## Section 4: Alarm API for Scheduled Work

DOs can schedule their own work using the Alarm API. This replaces the need for an external
scheduler for per-object housekeeping.

```typescript
export class SessionTracker implements DurableObject {
  private state: DurableObjectState;
  private readonly TTL = 30 * 60 * 1000; // 30 minutes

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const body = await request.json<{ userId: string; action: string }>();

    await this.state.storage.put(`session:${body.userId}`, {
      action: body.action,
      ts: Date.now(),
    });

    // Extend the cleanup alarm on every activity
    await this.state.storage.setAlarm(Date.now() + this.TTL);

    return new Response('OK');
  }

  // Called when the alarm fires
  async alarm(): Promise<void> {
    const now = Date.now();
    const cutoff = now - this.TTL;

    // Scan all sessions and delete stale ones
    const sessions = await this.state.storage.list<{ ts: number }>({ prefix: 'session:' });
    const toDelete: string[] = [];

    for (const [key, value] of sessions) {
      if (value.ts < cutoff) {
        toDelete.push(key);
      }
    }

    if (toDelete.length > 0) {
      await this.state.storage.delete(toDelete);
    }

    // If sessions remain, reschedule the alarm
    const remaining = await this.state.storage.list({ prefix: 'session:', limit: 1 });
    if (remaining.size > 0) {
      await this.state.storage.setAlarm(Date.now() + this.TTL);
    }
  }
}
```

Alarm constraints:
- One alarm per DO instance at a time; calling `setAlarm` replaces the pending alarm
- Minimum alarm delay: 0ms (fires as soon as possible after setting)
- Alarm fires are durable — if the DO crashes, the alarm will fire on next activation
- Use `this.state.storage.getAlarm()` to inspect the current scheduled time

---

## Section 5: DO Naming Strategies and Sharding

A single DO instance is the serialization bottleneck. For high-throughput counters or
aggregators, shard across multiple named instances.

```typescript
// Sharded counter: N shards, each handles 1/N of the write load
export interface Env {
  COUNTER: DurableObjectNamespace;
  SHARD_COUNT: string; // from env var, e.g. "16"
}

async function increment(env: Env, metric: string): Promise<void> {
  const shardCount = parseInt(env.SHARD_COUNT, 10);
  // Distribute writes across shards using a random shard
  const shardIndex = Math.floor(Math.random() * shardCount);
  const id = env.COUNTER.idFromName(`${metric}:shard:${shardIndex}`);
  const stub = env.COUNTER.get(id);
  await stub.fetch(new Request('https://do/increment'), { method: 'POST' });
}

async function getTotal(env: Env, metric: string): Promise<number> {
  const shardCount = parseInt(env.SHARD_COUNT, 10);
  const requests = Array.from({ length: shardCount }, (_, i) => {
    const id = env.COUNTER.idFromName(`${metric}:shard:${i}`);
    return env.COUNTER.get(id).fetch(new Request('https://do/count'));
  });
  const responses = await Promise.all(requests);
  const counts = await Promise.all(responses.map((r) => r.json<{ count: number }>()));
  return counts.reduce((sum, { count }) => sum + count, 0);
}
```

Jurisdiction hints: for data-residency compliance, constrain where the DO runs:

```typescript
// Force the DO to run in the EU
const id = env.ROOM.idFromName('eu-room-1');
const stub = env.ROOM.get(id, { locationHint: 'eeur' }); // Eastern Europe hint
```

Location hints: `wnam` (Western N. America), `enam` (Eastern N. America), `sam` (S. America),
`weur` (Western Europe), `eeur` (Eastern Europe), `apac` (Asia Pacific), `oc` (Oceania).

---

## Section 6: Testing Durable Objects Locally

```bash
# wrangler dev starts a local miniflare-based environment with DO support
npx wrangler dev src/index.ts --local

# With persistence across dev restarts
npx wrangler dev src/index.ts --local --persist-to ./dev-state
```

```typescript
// vitest + @cloudflare/vitest-pool-workers for unit testing DO logic
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
      },
    },
  },
});
```

```typescript
// src/ChatRoom.test.ts
import { env, createExecutionContext, waitOnExecutionContext } from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';
import { ChatRoom } from './ChatRoom';

describe('ChatRoom DO', () => {
  it('stores and retrieves message history', async () => {
    const id = env.CHAT_ROOM.idFromName('test-room');
    const stub = env.CHAT_ROOM.get(id);

    // Simulate a fetch to the DO
    const res = await stub.fetch(new Request('https://do/history'));
    const history = await res.json<string[]>();
    expect(Array.isArray(history)).toBe(true);
  });
});
```

---

## Anti-Patterns

- **Using a DO as a database** — DOs are coordination primitives. For bulk queries, use D1.
  A DO with 100k keys in storage has slow list operations and is expensive.
- **One DO per user for all user data** — creates unbounded object sprawl and forces reads
  of DO state (expensive). Store user data in D1; use DOs only for active sessions.
- **Not using the Hibernation API** — a DO that holds open WebSockets without hibernation
  bills CPU for every idle second. Always use `acceptWebSocket` (Hibernation API) instead
  of the legacy `ws.accept()`.
- **Cross-DO transactions** — there are none. Attempting eventual consistency by writing
  to two DOs in sequence creates split-brain risk. Design for single-DO ownership of each
  resource.
- **Large `fetch()` responses between Worker and DO** — the Worker-to-DO call is a local
  in-process call on the same isolate when the DO is co-located, but serializes over the
  network otherwise. Keep payloads small; pass IDs and keys, not blobs.

---

## Gotchas

- DOs run migrations: any new `class_name` in `wrangler.toml` must be declared in a
  `[[migrations]]` block. Missing this causes "class not found" errors on first deploy.
- `idFromName` is not reversible — you cannot list all DO instances from a namespace. If
  you need to enumerate live instances, track IDs in a KV namespace or D1 table.
- DO CPU time limit per request is 30 seconds on the Workers Paid plan. Long-running
  housekeeping should be offloaded to alarms, not blocking fetch handlers.
- WebSocket connections dropped by the client do not immediately trigger `webSocketClose`
  in all cases. Use heartbeats and evict sockets that do not respond.
- Storage `list()` with no `limit` can time out on large datasets. Always paginate with
  `limit` and `cursor`.

---

## Verification

```bash
# Deploy and smoke-test a WebSocket room
wrangler deploy

# Connect two WebSocket clients
wscat -c "wss://my-worker.workers.dev?room=test&user=alice" &
wscat -c "wss://my-worker.workers.dev?room=test&user=bob"

# Send a message from alice's terminal; verify bob receives it

# Check DO storage via wrangler tail
wrangler tail --format json | jq 'select(.event.request.url | contains("room=test"))'

# Check alarm scheduling
wrangler tail --format json | jq 'select(.event.type == "alarm")'
```

---

## Related Articles

- `cloudflare-workers-limits-resource-planning.md` — DO CPU and storage quotas
- `keda-cloudflare-queue-consumers.md` — async patterns that complement DOs
- `wrangler-toml-multi-environment-config.md` — per-environment DO binding config
- `cloudflare-workers-cost-optimization-scale.md` — cost implications of DO hibernation
- `workerd-local-dev-setup.md` — local development environment

---

## Sources

- Cloudflare Durable Objects documentation: https://developers.cloudflare.com/durable-objects/
- WebSocket Hibernation API: https://developers.cloudflare.com/durable-objects/api/websockets/
- DO Storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- DO Alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- Vitest pool workers: https://developers.cloudflare.com/workers/testing/vitest-integration/
