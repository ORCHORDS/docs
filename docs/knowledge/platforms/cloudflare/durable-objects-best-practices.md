# durable-objects-best-practices

**Issue:** DOs — single-threaded, coordination, storage
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a chat app. User A in Tokyo and User B in
Berlin send messages. The messages are out of order.
You use a DB. The DB is the bottleneck.

## Root cause
**Coordination is hard.** Use DOs for stateful,
coordinated workloads.

**Source:** CF DO docs.

## The "DO" concept

A Durable Object (DO) is:
- **Single-threaded:** Per object
- **Coordinated:** No race conditions
- **Stateful:** Built-in storage
- **Distributed:** Global
- **Per-key:** Identified by name

DOs are the right tool for stateful coordination.

## The "DO class" pattern

For a DO class:
```ts
export class Counter {
  state: DurableObjectState;
  count: number;

  constructor(state: DurableObjectState) {
    this.state = state;
    this.count = 0;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/increment') {
      this.count += 1;
      await this.state.storage.put('count', this.count);
      return Response.json({ count: this.count });
    }

    if (url.pathname === '/get') {
      this.count = (await this.state.storage.get<number>('count')) ?? 0;
      return Response.json({ count: this.count });
    }

    return new Response('Not found', { status: 404 });
  }
}
```

The DO has state + handler.

## The "DO binding" pattern

For a binding:
```toml
[[durable_objects.bindings]]
name = "COUNTER"
class_name = "Counter"

[[migrations]]
tag = "v1"
new_sqlite_classes = ["Counter"]
```

The binding is in `wrangler.toml`.

## The "DO instance" pattern

For an instance:
```ts
const id = env.COUNTER.idFromName('global-counter');
const stub = env.COUNTER.get(id);
const response = await stub.fetch('https://example.com/increment');
```

The instance is by name.

## The "DO per tenant" pattern

For per-tenant:
```ts
const id = env.TENANT_DO.idFromName(`tenant:${tenantId}`);
const stub = env.TENANT_DO.get(id);
```

The DO is per tenant.

## The "DO WebSocket" pattern

For WebSocket:
```ts
export class ChatRoom {
  state: DurableObjectState;
  sessions: WebSocket[] = [];

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    if (new URL(request.url).pathname === '/websocket') {
      const pair = new WebSocketPair();
      const [client, server] = Object.values(pair);

      server.accept();
      this.sessions.push(server);

      server.addEventListener('message', (event) => {
        for (const session of this.sessions) {
          try {
            session.send(event.data);
          } catch (err) {
            this.sessions = this.sessions.filter(s => s !== session);
          }
        }
      });

      server.addEventListener('close', () => {
        this.sessions = this.sessions.filter(s => s !== server);
      });

      return new Response(null, { status: 101, webSocket: client });
    }

    return new Response('Not found', { status: 404 });
  }
}
```

The DO holds the WebSocket sessions.

**Source:** DO WebSocket:
https://developers.cloudflare.com/durable-objects/best-practices/websockets/

## The "DO storage" pattern

For storage:
```ts
// Get
const value = await this.state.storage.get<MyType>('key');

// Put
await this.state.storage.put('key', value);

// Delete
await this.state.storage.delete('key');

// List
const entries = await this.state.storage.list<MyType>({ prefix: 'user:' });

// Transactional
await this.state.storage.transaction(async (txn) => {
  await txn.put('count', 1);
  await txn.put('updatedAt', new Date().toISOString());
});
```

The storage is per-DO.

## The "DO alarms" pattern

For alarms (delayed work):
```ts
// Schedule
await this.state.storage.setAlarm(Date.now() + 60_000);

// Handle
async alarm(): Promise<void> {
  // Do work
  await this.cleanup();

  // Reschedule
  await this.state.storage.setAlarm(Date.now() + 60_000);
}
```

The alarm is delayed.

## The "DO RPC" pattern

For RPC (class methods):
```ts
export class UserService {
  state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async getUser(id: string): Promise<User | null> {
    return this.state.storage.get<User>(`user:${id}`);
  }

  async createUser(user: User): Promise<void> {
    await this.state.storage.put(`user:${user.id}`, user);
  }
}
```

The DO has typed methods.

## The "DO input/output" pattern

For I/O:
```ts
// Inside the DO, you can use env
export class MyDO {
  state: DurableObjectState;
  env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    // Use this.env.DB, this.env.R2, etc.
    const user = await this.env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind('u_1').first();
    return Response.json(user);
  }
}
```

The DO has the env.

## The "DO hibernation" pattern

For hibernation, use Hibernation API:
```ts
server.addEventListener('message', (event) => {
  // Process the message
  processMessage(event.data);

  // Hibernation: the server can be evicted; the state is restored on resume
});
```

The hibernation is built-in.

## The "DO limit" pattern

For limits:
- **Memory:** 128MB
- **CPU:** 30s (default), 5min (unbound)
- **Storage:** 10GB
- **WebSocket:** 32k per DO

The limits are checked.

## The "DO observability" pattern

For observability:
- **DO calls:** Per minute
- **Storage:** Per DO
- **WebSocket:** Active sessions
- **Latency:** p99

The metrics are in the CF dashboard.

## The "DO anti-pattern" anti-patterns

### 1. Global state in DO
- **Issue:** Race conditions
- **Fix:** Per-key DO

### 2. Long CPU in DO
- **Issue:** CPU timeout
- **Fix:** Optimize or alarm

### 3. Many DOs
- **Issue:** Cost + complexity
- **Fix:** Coalesce where possible

### 4. No idempotency
- **Issue:** Retries do the work twice
- **Fix:** Idempotency keys

## Verification
- **Test:** DO works
- **Test:** WebSocket works
- **Test:** Storage works
- **Live:** DO metrics monitored
- **Audit:** Quarterly review

## Gotchas
- **The "global state" anti-pattern.** Per-key DO.
- **The "long CPU" anti-pattern.** Optimize.
- **The "no idempotency" anti-pattern.** Idempotency
  keys.

## Related
- `cloudflare/durable-objects-patterns.md`
- `feature-cookbook-realtime.md`
- `feature-cookbook-saga.md`
- CF DO: https://developers.cloudflare.com/durable-objects/
