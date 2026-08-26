# Workers Durable Object Pitfalls

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You adopt Durable Objects for stateful coordination and quickly ship to production. Weeks later you notice rising storage costs, alarms firing at wrong times, WebSocket connections dropping on reconnect, and `storage.list()` calls timing out under load. When you try to migrate DOs to a new class name, data silently disappears. These are not edge cases — they are the default failure modes of DOs when used without explicit safeguards.

---

## Context

Durable Objects provide a single-threaded, globally consistent execution environment with persistent storage. Each DO instance is identified by a name or ID and lives until its storage is deleted. The runtime never garbage-collects idle DO instances; only explicit deletion or eviction (after 30 days of no activity and no alarm) removes them. Storage is billed per GB-month, alarms are scheduled relative to wall-clock time, and WebSocket connections share the DO's single-threaded event loop.

Orchords runs ~40 DO classes across chat rooms, song collaboration sessions, and real-time presence — all lessons below were discovered in production.

---

## Solution

```typescript
// workers-durable-object-pitfalls.ts
// Demonstrates correct patterns for each pitfall category

import {
  DurableObject,
  DurableObjectState,
  DurableObjectStorage,
} from '@cloudflare/workers-types';

// ─────────────────────────────────────────────────────────────
// PITFALL 1: DO instance accumulation — never cleaned up
// ─────────────────────────────────────────────────────────────
//
// Anti-pattern: creating a unique DO per user-session with no
// cleanup logic. Each ID is permanent and billed for storage
// even after the session ends.
//
// Fix: track a TTL in storage and self-delete on expiry.

export class SessionRoom implements DurableObject {
  private state: DurableObjectState;
  private readonly TTL_MS = 24 * 60 * 60 * 1000; // 24 h

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/ping') {
      // Refresh last-seen on any real activity
      await this.state.storage.put('lastSeen', Date.now());
      await this.scheduleExpiry();
      return new Response('ok');
    }

    if (url.pathname === '/delete') {
      await this.selfDestruct();
      return new Response('deleted');
    }

    return new Response('unknown route', { status: 404 });
  }

  async alarm(): Promise<void> {
    const lastSeen = (await this.state.storage.get<number>('lastSeen')) ?? 0;
    const age = Date.now() - lastSeen;

    if (age >= this.TTL_MS) {
      await this.selfDestruct();
    } else {
      // Still active — push alarm forward
      await this.state.storage.setAlarm(lastSeen + this.TTL_MS);
    }
  }

  private async scheduleExpiry(): Promise<void> {
    const existing = await this.state.storage.getAlarm();
    if (!existing) {
      await this.state.storage.setAlarm(Date.now() + this.TTL_MS);
    }
  }

  private async selfDestruct(): Promise<void> {
    await this.state.storage.deleteAll();
    // After deleteAll(), the DO instance will be evicted by the runtime
    // once it becomes idle. No further action needed.
  }
}

// ─────────────────────────────────────────────────────────────
// PITFALL 2: storage.list() without cursor pagination → timeout
// ─────────────────────────────────────────────────────────────
//
// storage.list() with no options loads ALL keys into memory.
// On a DO with >10 000 keys this regularly exceeds the 30-second
// CPU limit and times out.

export class SongLibrary implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const cursor = url.searchParams.get('cursor') ?? undefined;
    const limit = Number(url.searchParams.get('limit') ?? '100');

    // WRONG — will timeout on large datasets:
    // const all = await this.state.storage.list();

    // CORRECT — paginate with cursor:
    const result = await this.state.storage.list<string>({
      prefix: 'song:',
      limit,
      cursor,
    });

    const entries = Array.from(result.entries());
    const lastKey = entries.at(-1)?.[0];

    return Response.json({
      songs: entries.map(([k, v]) => ({ key: k, value: v })),
      nextCursor: result.size === limit ? lastKey : null,
    });
  }
}

// ─────────────────────────────────────────────────────────────
// PITFALL 3: Alarm scheduling drift
// ─────────────────────────────────────────────────────────────
//
// Scheduling the next alarm from Date.now() inside alarm()
// accumulates drift over time. Use a fixed anchor instead.

export class PeriodicAggregator implements DurableObject {
  private state: DurableObjectState;
  private readonly INTERVAL_MS = 60 * 1000; // 1 min

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async alarm(): Promise<void> {
    const now = Date.now();
    await this.aggregate();

    // WRONG — drifts because alarm fires slightly after scheduled time:
    // await this.state.storage.setAlarm(Date.now() + this.INTERVAL_MS);

    // CORRECT — align to next interval boundary:
    const next = now - (now % this.INTERVAL_MS) + this.INTERVAL_MS;
    await this.state.storage.setAlarm(next);
  }

  private async aggregate(): Promise<void> {
    const count = (await this.state.storage.get<number>('count')) ?? 0;
    await this.state.storage.put('lastCount', count);
    await this.state.storage.put('count', 0);
  }

  async fetch(request: Request): Promise<Response> {
    const count = (await this.state.storage.get<number>('count')) ?? 0;
    await this.state.storage.put('count', count + 1);
    return new Response('counted');
  }
}

// ─────────────────────────────────────────────────────────────
// PITFALL 4: waitForOpen WebSocket race condition
// ─────────────────────────────────────────────────────────────
//
// When a DO accepts a WebSocket, the client may send messages
// before the DO's fetch() has returned. Using server.accept()
// and then waiting for messages without registering a handler
// first drops those early messages.

export class RealtimeSession implements DurableObject {
  private state: DurableObjectState;
  private sessions: Set<WebSocket> = new Set();

  constructor(state: DurableObjectState) {
    this.state = state;
    // Restore hibernated WebSockets after DO restart
    for (const ws of this.state.getWebSockets()) {
      this.sessions.add(ws);
    }
  }

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('Expected WebSocket', { status: 426 });
    }

    // Use hibernatable WebSockets API to avoid DO running continuously
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);

    // acceptWebSocket registers handlers BEFORE any message can arrive
    // this.state.acceptWebSocket(server); is the race-safe API
    this.state.acceptWebSocket(server);
    this.sessions.add(server);

    return new Response(null, { status: 101, webSocket: client });
  }

  webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): void {
    // Broadcast to all connected sessions
    const text = typeof message === 'string' ? message : new TextDecoder().decode(message);
    for (const session of this.sessions) {
      if (session !== ws && session.readyState === WebSocket.READY_STATE_OPEN) {
        session.send(text);
      }
    }
  }

  webSocketClose(ws: WebSocket): void {
    this.sessions.delete(ws);
  }

  webSocketError(ws: WebSocket, error: unknown): void {
    console.error('WebSocket error', error);
    this.sessions.delete(ws);
  }
}

// ─────────────────────────────────────────────────────────────
// PITFALL 5: Migrating DOs without data loss
// ─────────────────────────────────────────────────────────────
//
// Renaming a DO class in wrangler.toml and deploying causes ALL
// existing DO instances to become unreachable — their storage
// keys are tied to the old class name. Use the migrations block.

/*
# wrangler.toml snippet — REQUIRED when renaming a DO class

[[migrations]]
tag = "v1"          # must be unique and monotonically increasing
new_classes = ["CollaborationRoom"]

[[migrations]]
tag = "v2"
renamed_classes = [
  { from = "CollaborationRoom", to = "SongRoom" }
]

# If you delete an old class:
# deleted_classes = ["OldClassName"]
*/

export class SongRoom implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const data = await this.state.storage.get('roomData');
    return Response.json({ data });
  }
}
```

---

## Implementation Details

**Instance accumulation** is invisible in the Cloudflare dashboard until your storage bill arrives. Each named DO occupies a row in distributed SQLite; there is no TTL at the platform level. The only safe strategy is an explicit `alarm()` that calls `storage.deleteAll()` after the instance becomes idle. After `deleteAll()`, the runtime evicts the instance within minutes of the next idle period.

**Storage cost from unbounded lists** compounds quickly: if every write appends a new key with a timestamp suffix and no key is ever deleted, storage grows linearly with traffic. Always implement a retention policy: either bounded ring-buffer semantics (keep last N entries with numeric suffixes and wrap around) or a `storage.delete()` sweep inside `alarm()`.

**Cursor pagination for `storage.list()`** is mandatory for any DO that accumulates more than a few thousand keys. The `limit` option returns at most that many keys; the cursor for the next page is the last key returned. Reconstruct the cursor on the client side by storing the last key in the response.

**Alarm drift** compounds over long uptimes. A minutely alarm that starts 2 ms late will be 2 minutes late after 60 000 firings (roughly 6 weeks). Use modular arithmetic against wall-clock epoch millis to pin each alarm to a deterministic boundary.

**Hibernatable WebSockets** (`state.acceptWebSocket`) suspend the DO between messages, dramatically reducing billable duration. The older `server.accept()` pattern keeps the DO active continuously. Migrate to the hibernatable API when any WebSocket DO sees more than a few concurrent connections.

---

## Anti-patterns

- Creating DO instances from `DurableObjectId.newUniqueId()` inside loops with no cleanup (every ID is permanent).
- Calling `storage.list()` with no `limit` or `cursor` inside a hot path.
- Scheduling next alarm as `Date.now() + interval` from inside `alarm()` handler.
- Using `server.accept()` instead of `state.acceptWebSocket()` for WebSocket DOs that need hibernation.
- Renaming a DO class in `wrangler.toml` without a `migrations` block — all existing instance data becomes unreachable.
- Storing arrays by serialising them to a single storage key — the 128 KB per-value limit will bite you silently by truncating.

---

## Gotchas

- `storage.deleteAll()` is not synchronous in effect — the DO instance remains accessible until the runtime decides to evict it. Do not rely on the instance being gone immediately after `deleteAll()`.
- `state.storage.getAlarm()` returns `null` if no alarm is set, not `0`. Always guard with `?? 0` or an explicit null check before arithmetic.
- The migrations `tag` field must be a string that sorts lexicographically in the order you want migrations applied. Using `v1`, `v2`, `v3` works; using arbitrary strings does not.
- WebSocket `readyState` values on the server side are `READY_STATE_OPEN`, `READY_STATE_CLOSING`, `READY_STATE_CLOSED` — not the browser numeric constants 0/1/2/3.
- A DO's alarm does not fire if the DO has been evicted and `deleteAll()` was called — the alarm is deleted along with storage.

---

## Verification

```typescript
// Verify alarm drift correction in unit tests
const INTERVAL = 60_000;
const now = 1_700_000_001_500; // 1.5 s into a minute
const next = now - (now % INTERVAL) + INTERVAL;
console.assert(next === 1_700_000_060_000, 'next alarm must be on the minute boundary');

// Verify DO storage list pagination in integration tests
async function exhaustList(stub: DurableObjectStub, prefix: string): Promise<string[]> {
  const all: string[] = [];
  let cursor: string | null = null;
  do {
    const url = new URL('https://do/list');
    url.searchParams.set('prefix', prefix);
    url.searchParams.set('limit', '100');
    if (cursor) url.searchParams.set('cursor', cursor);
    const res = await stub.fetch(url.toString());
    const body = await res.json<{ songs: { key: string }[]; nextCursor: string | null }>();
    all.push(...body.songs.map((s) => s.key));
    cursor = body.nextCursor;
  } while (cursor !== null);
  return all;
}
```

---

## Related

- `documentation/docs/policies/lessons/memory-leak-detection.md`
- `documentation/docs/policies/lessons/cpu-time-limit-patterns.md`
- Cloudflare Durable Objects documentation: Storage API, Alarms API, Hibernatable WebSockets

---

## Sources

- Cloudflare Workers Durable Objects docs (2025)
- Orchords production incident log #DO-014 (DO accumulation), #DO-022 (list timeout), #DO-031 (alarm drift)
- Cloudflare Community: "Durable Object migration data loss" thread
