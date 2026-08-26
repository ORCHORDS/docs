# durable-objects-patterns

**Issue:** Use DOs for stateful, coordinated, real-time apps
**Date:** 2026-08-09
**Status:** documented

## Symptom
You need a chat feature. Users send messages; other users
see them in real time. You try D1 + polling; the polling
load is huge. You try WebSockets from your origin; the
connection count explodes. You need a stateful,
coordinated solution.

## Root cause
**Some apps are stateful and need coordination.** A chat
room, a multiplayer game, a rate limiter — they need a
single source of truth that's fast.

**Source:** CF Durable Objects:
https://developers.cloudflare.com/durable-objects/

> "Durable Objects are a scalable, coordinated compute
> primitive that enables strong consistency for stateful
> applications."

## The "DO is a single thread" model

A DO is a single-threaded actor:
- One DO instance per "name" (e.g. one per chat room)
- All requests to that name go to the same instance
- The instance has its own state (in-memory + SQLite
  storage)
- No locking needed (single-threaded)

This is the same model as Erlang processes or Akka actors.

## The "chat room" pattern

```ts
// In a Worker
async function getChatRoom(roomId: string, env: Env): Promise<DurableObjectStub> {
  const id = env.CHAT_ROOM.idFromName(roomId);
  return env.CHAT_ROOM.get(id);
}

// The DO
export class ChatRoom implements DurableObject {
  private sessions = new Map<string, WebSocket>();
  private storage: DurableObjectStorage;

  constructor(state: DurableObjectState) {
    this.storage = state.storage;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/ws') {
      // WebSocket upgrade
      const pair = new WebSocketPair();
      const [client, server] = Object.values(pair) as [WebSocket, WebSocket];

      this.handleSession(server);
      return new Response(null, { status: 101, webSocket: client });
    }

    if (url.pathname === '/history') {
      const messages = await this.storage.list({ prefix: 'msg:' });
      return new Response(JSON.stringify(Array.from(messages.values())));
    }

    return new Response('Not found', { status: 404 });
  }

  async handleSession(ws: WebSocket) {
    const sessionId = crypto.randomUUID();
    this.sessions.set(sessionId, ws);

    ws.addEventListener('message', async (event) => {
      const message = JSON.parse(event.data as string);
      const messageId = crypto.randomUUID();
      const timestamp = new Date().toISOString();

      // Store
      await this.storage.put(`msg:${messageId}`, { messageId, sessionId, timestamp, ...message });

      // Broadcast
      const broadcast = JSON.stringify({ messageId, sessionId, timestamp, ...message });
      for (const [id, session] of this.sessions) {
        try {
          session.send(broadcast);
        } catch (err) {
          this.sessions.delete(id);
        }
      }
    });

    ws.addEventListener('close', () => {
      this.sessions.delete(sessionId);
    });
  }
}
```

The DO holds all chat room state; the Worker is the HTTP
edge.

## The "rate limiter" pattern

```ts
export class RateLimiter implements DurableObject {
  private requests = new Map<string, number[]>();
  private storage: DurableObjectStorage;

  constructor(state: DurableObjectState) {
    this.storage = state.storage;
  }

  async fetch(request: Request): Promise<Response> {
    const { userId, limit, windowMs } = await request.json() as any;

    const now = Date.now();
    const windowStart = now - windowMs;

    // Load from storage (on first request after eviction)
    if (this.requests.size === 0) {
      const stored = await this.storage.get<Record<string, number[]>>('state');
      if (stored) this.requests = new Map(Object.entries(stored));
    }

    // Get user's recent requests
    const userRequests = (this.requests.get(userId) ?? []).filter(t => t > windowStart);

    if (userRequests.length >= limit) {
      return new Response(JSON.stringify({ allowed: false, remaining: 0 }), { status: 429 });
    }

    userRequests.push(now);
    this.requests.set(userId, userRequests);

    // Persist (best-effort)
    this.storage.put('state', Object.fromEntries(this.requests));

    return new Response(JSON.stringify({ allowed: true, remaining: limit - userRequests.length }));
  }
}
```

The DO is the per-user rate limit; no DB needed.

## The "DO storage" pattern

DOs have built-in SQLite-like storage:
```ts
// Put
await this.storage.put('user:123', { name: 'Alice', email: 'a@x.test' });

// Get
const user = await this.storage.get('user:123');

// List
const list = await this.storage.list({ prefix: 'user:' });

// Delete
await this.storage.delete('user:123');

// Transaction
await this.storage.transaction(async (txn) => {
  await txn.put('user:123', { ...user, name: 'Bob' });
  await txn.put('audit:123', { action: 'updated', userId: '123' });
});
```

The storage is fast (in-memory) and persistent (writes to
disk).

## The "DO + WebSocket" pattern

For real-time, DO is the ideal host:
- WebSocket connections stay open
- The DO processes messages and broadcasts
- No external pub/sub needed

```ts
async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
  // Process the message
  const data = JSON.parse(message as string);

  // Broadcast to all connected clients
  for (const client of this.sessions.values()) {
    client.send(JSON.stringify({ from: 'server', data }));
  }
}
```

## The "DO alarm" pattern

For scheduled work, use the DO alarm:
```ts
async alarm(): Promise<void> {
  // Do work
  await this.cleanupOldMessages();

  // Re-schedule
  await this.storage.setAlarm(Date.now() + 60_000);  // 1 min
}
```

The DO wakes up at the alarm time, runs the work, and can
re-schedule.

## The "DO input gate" pattern

For consistency, use input gates (CF feature):
```ts
async fetch(request: Request): Promise<Response> {
  // Apply the update atomically
  await this.storage.sync();

  // Now read the consistent state
  const state = await this.storage.get('state');
  return new Response(JSON.stringify(state));
}
```

The `sync()` ensures all pending writes are visible.

## The "DO eviction" gotcha

DOs are evicted after a period of inactivity. The state is
loaded from storage on the next request. For latency-
sensitive apps, this is a cold start.

To minimize:
- Use the storage proactively (load state on every request)
- Use a "warmup" cron that pings the DO
- Keep state small (faster to load)

## The "DO + R2" pattern

For large files, store in R2; the DO holds the metadata:
```ts
async storeFile(filename: string, content: ArrayBuffer, env: Env): Promise<string> {
  const key = `files/${crypto.randomUUID()}/${filename}`;
  await env.R2!.put(key, content);

  await this.storage.put(`file:${key}`, { filename, size: content.byteLength, uploadedAt: new Date().toISOString() });
  return key;
}
```

## The "DO + D1" pattern

For shared data, use D1; the DO is the cache:
```ts
async getUser(userId: string, env: Env): Promise<User | null> {
  // Try in-memory cache
  if (this.cache.has(userId)) return this.cache.get(userId)!;

  // Fall back to D1
  const user = await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(userId).first<User>();
  if (user) this.cache.set(userId, user);
  return user;
}
```

## The "DO limits" pattern

DOs have limits:
- **In-memory:** 128 MB
- **Storage:** 10 GB
- **CPU per request:** 30s (Bundled); 5 min (Unbound)
- **WebSocket connections:** ~32k per DO

For 1M users, you'd need 1M DOs (one per user, e.g. for
rate limiting). The cost adds up.

## The "DO cost" pattern

DOs cost:
- **Requests:** $0.15 per million
- **Duration:** $12.50 per million GB-seconds

For high-traffic apps, the cost is non-trivial. Use DOs only
for stateful work that needs coordination.

## Verification
- **Test:** `test/chat.test.ts > chat message is broadcast
  to all clients` — passes
- **Live:** DO count + memory is monitored
- **Audit:** Quarterly review of DO usage

## Gotchas
- **The "DO is single-threaded" gotcha.** A slow operation
  blocks all others. Don't do CPU-heavy work in a DO.
- **The "DO is per-name" gotcha.** One DO per name. If you
  want "sharding," use different names.
- **The "DO has a cold start" gotcha.** First request after
  eviction is slow. Use alarm + warmup.
- **The "DO state is local to the DO" gotcha.** Two DOs
  with different names don't share state. Use D1 for
  shared state.
- **The "WebSocket is in-memory" gotcha.** If the DO is
  evicted, the WebSocket is closed. Clients must
  reconnect.

## Related
- `cloudflare/audit-chain-durable-object.md`
- `cloudflare/per-tenant-durable-object.md`
- `patterns/per-tenant-durable-object.md`
- `patterns/leader-election.md`
- `patterns/connection-pooling.md`
- CF DOs: https://developers.cloudflare.com/durable-objects/
