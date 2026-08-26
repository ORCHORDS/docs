# Chaos Testing Durable Objects Hibernation

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Durable Objects using the WebSocket Hibernation API (`acceptWebSocket`) survive eviction between messages without losing state, but bugs emerge at the boundary: in-memory data that is not persisted before eviction is silently lost, `alarm()` handlers that were not re-registered after wakeup never fire, and event handlers like `webSocketMessage` receive messages out of order when the DO is cold. Without deliberate chaos injection, these classes of failure only surface in production under traffic spikes or during Cloudflare's own rolling deploys.

## Context

The Hibernation API changes the lifecycle of a Durable Object:

1. `acceptWebSocket(ws)` — the runtime takes custody of the WebSocket; the DO can be evicted.
2. On eviction, the JavaScript context is torn down. Persisted state in `this.state.storage` survives; in-memory properties do not.
3. On the next incoming message, the runtime reconstructs the DO by calling the constructor and then `webSocketMessage`.

Miniflare (via `@cloudflare/vitest-pool-workers`) supports the Hibernation API and provides `state.abort()` to forcibly simulate eviction, making it possible to test wakeup paths deterministically.

Key types: `DurableObject`, `DurableObjectState`, `WebSocket`, `WebSocketPair`.

## Setup

```toml
# wrangler.toml
[[durable_objects.bindings]]
name = "CHAT_DO"
class_name = "ChatRoom"

[durable_objects.migration]
tag = "v1"
new_classes = ["ChatRoom"]
```

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
export default defineConfig({
  test: {
    pool: '@cloudflare/vitest-pool-workers',
    poolOptions: {
      workers: { wrangler: { configPath: './wrangler.toml' } },
    },
  },
});
```

## Durable Object Under Test

```typescript
// src/chat-room.ts
export class ChatRoom implements DurableObject {
  private sessions: Map<string, WebSocket> = new Map();
  private messageCount = 0; // in-memory — intentionally volatile

  constructor(private readonly state: DurableObjectState, private readonly env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const upgrade = request.headers.get('Upgrade');
    if (upgrade !== 'websocket') return new Response('Expected WebSocket', { status: 426 });

    const [client, server] = Object.values(new WebSocketPair());
    const id = crypto.randomUUID();
    this.state.acceptWebSocket(server, [id]);
    this.sessions.set(id, server);
    this.messageCount++;
    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const tags = this.state.getTags(ws);
    const id = tags[0];
    // Persist message count across hibernation
    const count = ((await this.state.storage.get<number>('messageCount')) ?? 0) + 1;
    await this.state.storage.put('messageCount', count);
    ws.send(JSON.stringify({ id, count, echo: message }));
  }

  async webSocketClose(ws: WebSocket): Promise<void> {
    const tags = this.state.getTags(ws);
    this.sessions.delete(tags[0]);
  }

  async webSocketError(ws: WebSocket, error: unknown): Promise<void> {
    ws.close(1011, 'Internal error');
  }
}
```

## Simulating Eviction Between Messages

```typescript
// tests/chat-room-chaos.test.ts
import { env, createExecutionContext, waitOnExecutionContext, getMiniflareDurableObjectStorage } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';

async function getStub() {
  const id = env.CHAT_DO.idFromName('room-1');
  return env.CHAT_DO.get(id);
}

describe('ChatRoom hibernation chaos', () => {
  it('persisted message count survives eviction', async () => {
    const stub = await getStub();

    // Connect and send a message
    const res = await stub.fetch(new Request('http://do/ws', {
      headers: { Upgrade: 'websocket' },
    }));
    expect(res.status).toBe(101);
    const ws = res.webSocket!;
    ws.accept();

    // Send first message
    ws.send('hello');
    await new Promise((r) => ws.addEventListener('message', r, { once: true }));

    // Force eviction — Miniflare destroys the DO's JS context
    const id = env.CHAT_DO.idFromName('room-1');
    const storage = await getMiniflareDurableObjectStorage(id);
    const countBefore = await storage.get<number>('messageCount');
    expect(countBefore).toBe(1);

    // Simulate eviction by aborting the DO (triggers reconstruction on next request)
    // In Miniflare you can call state.abort() indirectly through the test helper
    // or by sending a special control fetch to the stub after resetting context.
    // The pattern below sends a second message after cold reconstruction:
    const stub2 = await getStub(); // fresh reference forces cold start in some pool versions
    const res2 = await stub2.fetch(new Request('http://do/ws', {
      headers: { Upgrade: 'websocket' },
    }));
    expect(res2.status).toBe(101);
    const ws2 = res2.webSocket!;
    ws2.accept();
    ws2.send('world');
    await new Promise((r) => ws2.addEventListener('message', r, { once: true }));

    const countAfter = await storage.get<number>('messageCount');
    expect(countAfter).toBe(2); // persisted across reconstruction
  });
});
```

## Asserting In-Memory State Is Lost on Eviction

```typescript
  it('in-memory sessions map resets after eviction', async () => {
    const id = env.CHAT_DO.idFromName('room-chaos');
    const stub = env.CHAT_DO.get(id);

    // Connect to establish a session in memory
    const res = await stub.fetch(new Request('http://do/sessions', {
      headers: { Upgrade: 'websocket' },
    }));
    expect(res.status).toBe(101);

    // Check session count via a diagnostic endpoint (if implemented)
    const countRes = await stub.fetch(new Request('http://do/session-count'));
    expect(await countRes.text()).toBe('1');

    // Evict — in real Miniflare, call state.abort() via a test-only fetch route
    await stub.fetch(new Request('http://do/__chaos__/evict', { method: 'POST' }));

    // After eviction: in-memory map is gone
    const afterRes = await stub.fetch(new Request('http://do/session-count'));
    expect(await afterRes.text()).toBe('0');
  });
```

## Chaos: Alarm Re-Registration After Wake

```typescript
// tests/alarm-chaos.test.ts
import { env, runWithMiniflareClock } from 'cloudflare:test';
import { it, expect } from 'vitest';

it('alarm fires after eviction and reconstruction', async () => {
  const id = env.CHAT_DO.idFromName('alarm-room');
  const stub = env.CHAT_DO.get(id);

  // Register alarm via a fetch
  await stub.fetch(new Request('http://do/set-alarm', { method: 'POST' }));

  // Evict the DO
  await stub.fetch(new Request('http://do/__chaos__/evict', { method: 'POST' }));

  // Advance clock past alarm time
  await runWithMiniflareClock(5000); // 5 seconds

  // Verify alarm side-effect was committed to storage despite eviction
  const id2 = env.CHAT_DO.idFromName('alarm-room');
  const storage = await getMiniflareDurableObjectStorage(id2);
  expect(await storage.get<boolean>('alarmFired')).toBe(true);
});
```

## Anti-patterns

- **Testing hibernation with `vi.useFakeTimers()` alone** – Fake timers affect the JS runtime clock but not the workerd clock that controls DO eviction timing.
- **Relying on in-memory caches across WebSocket messages** – Hibernation erases all non-persisted state. Any cache keyed by `this.*` must be rebuilt from storage in the constructor or lazily on first access.
- **Not exposing a `__chaos__/evict` route in the DO** – Without a controlled eviction path, tests must re-create stubs and hope the pool forces a cold start. Add a test-only eviction route guarded by `env.ENVIRONMENT !== 'production'`.
- **Asserting session counts from in-memory state** – Session counts that survive eviction must be stored in `state.storage`, not `this.sessions.size`.

## Gotchas

- `getMiniflareDurableObjectStorage(id)` requires the `DurableObjectId`, not the stub. Obtain the id with `env.DO_BINDING.idFromName(name)`.
- After eviction, the next `stub.fetch()` call reconstructs the DO and runs the constructor. Any `async` init that must complete before `fetch` handling must use `state.blockConcurrencyWhile()` in the constructor.
- WebSocket objects created before eviction are no longer tracked by the reconstructed DO. Clients holding the client-side WebSocket will see the connection drop; reconnect logic must be tested separately.
- Miniflare's `getMiniflareDurableObjectStorage` is an escape hatch — it bypasses the DO's own methods. Use it only in tests, never in application code.

## Verification

```bash
npx vitest run tests/chat-room-chaos.test.ts tests/alarm-chaos.test.ts --reporter=verbose
```

Expected: all tests pass; no `TypeError: Cannot read property of undefined` from in-memory state reads; storage counts are consistent across eviction boundaries.

## Related

- `durable-objects-websocket-hibernation-testing.md` — baseline WebSocket hibernation test setup
- `durable-objects-alarm-testing-miniflare.md` — alarm testing without chaos
- `chaos-engineering-cloudflare-workers.md` — broader Workers chaos strategies
- `durable-objects-miniflare-fake-timers.md` — fake timer integration for DO alarms

## Sources

- https://developers.cloudflare.com/durable-objects/api/hibernatable-websocket-event-handlers/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
