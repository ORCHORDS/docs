# WebSocket and Real-Time Feature Testing

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You build a chat feature, a live dashboard, or a collaborative editor backed by WebSockets or Server-Sent Events. The feature works when you click around manually, but you have no automated tests for it. Six months later a refactor breaks message ordering, broadcast fanout silently drops one recipient out of five, and a reconnect loop eats 100% CPU on poor network conditions. You discover these bugs from users, not from CI.

Real-time features are harder to test than request/response APIs because they involve stateful connections, asynchronous server-side events, timing-sensitive message ordering, and bidirectional communication. This article covers unit testing message handlers, integration testing the server-side WebSocket lifecycle, end-to-end testing with Playwright, and load testing connection fanout.

## Context

WebSocket tests operate at several levels:

| Level | What it tests | Tool |
|---|---|---|
| Unit | Message parsing, handler logic | Vitest with mock WS |
| Integration | Server lifecycle, broadcast, rooms | `ws` library, `supertest` + custom WS setup |
| E2E | Real browser connecting, UI reflecting messages | Playwright |
| Load | Concurrent connections, message fanout throughput | k6, Artillery with WebSocket plugin |

The hardest part is handling async message exchange without race conditions in your test code. Wrap WebSocket communication in helper utilities that convert event-based APIs into Promise-based ones.

## Unit Testing Message Handlers

Separate the message-handling logic from the WebSocket infrastructure so you can test it synchronously.

### Handler Architecture

```typescript
// src/realtime/message-handler.ts
export type IncomingMessage =
  | { type: 'join'; roomId: string }
  | { type: 'leave'; roomId: string }
  | { type: 'chat'; roomId: string; text: string };

export type OutgoingMessage =
  | { type: 'joined'; roomId: string; memberCount: number }
  | { type: 'chat'; roomId: string; from: string; text: string; ts: number }
  | { type: 'error'; code: string; message: string };

export interface RoomStore {
  join(roomId: string, userId: string): Promise<number>;
  leave(roomId: string, userId: string): Promise<void>;
  broadcast(roomId: string, message: OutgoingMessage, excludeUserId?: string): Promise<void>;
}

export class MessageHandler {
  constructor(private store: RoomStore, private userId: string) {}

  async handle(raw: string): Promise<OutgoingMessage | null> {
    let msg: IncomingMessage;
    try {
      msg = JSON.parse(raw);
    } catch {
      return { type: 'error', code: 'INVALID_JSON', message: 'Message must be valid JSON' };
    }

    if (!msg.type) {
      return { type: 'error', code: 'MISSING_TYPE', message: 'Message must have a type field' };
    }

    switch (msg.type) {
      case 'join': {
        const memberCount = await this.store.join(msg.roomId, this.userId);
        await this.store.broadcast(msg.roomId, { type: 'joined', roomId: msg.roomId, memberCount }, this.userId);
        return { type: 'joined', roomId: msg.roomId, memberCount };
      }
      case 'chat': {
        const outgoing: OutgoingMessage = {
          type: 'chat', roomId: msg.roomId, from: this.userId,
          text: msg.text, ts: Date.now(),
        };
        await this.store.broadcast(msg.roomId, outgoing);
        return null; // sender already sees the echo via broadcast
      }
      case 'leave': {
        await this.store.leave(msg.roomId, this.userId);
        return null;
      }
      default: {
        return { type: 'error', code: 'UNKNOWN_TYPE', message: `Unknown message type: ${(msg as any).type}` };
      }
    }
  }
}
```

```typescript
// src/realtime/message-handler.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MessageHandler, RoomStore } from './message-handler';

const makeStore = (): RoomStore => ({
  join: vi.fn().mockResolvedValue(2),
  leave: vi.fn().mockResolvedValue(undefined),
  broadcast: vi.fn().mockResolvedValue(undefined),
});

describe('MessageHandler', () => {
  let store: ReturnType<typeof makeStore>;
  let handler: MessageHandler;

  beforeEach(() => {
    store = makeStore();
    handler = new MessageHandler(store, 'user-alice');
  });

  it('returns error for invalid JSON', async () => {
    const result = await handler.handle('not json {{{');
    expect(result).toMatchObject({ type: 'error', code: 'INVALID_JSON' });
  });

  it('returns error for message without type', async () => {
    const result = await handler.handle(JSON.stringify({ roomId: 'r1' }));
    expect(result).toMatchObject({ type: 'error', code: 'MISSING_TYPE' });
  });

  it('returns error for unknown message type', async () => {
    const result = await handler.handle(JSON.stringify({ type: 'unknown' }));
    expect(result).toMatchObject({ type: 'error', code: 'UNKNOWN_TYPE' });
  });

  it('join: calls store.join and returns member count', async () => {
    const result = await handler.handle(JSON.stringify({ type: 'join', roomId: 'room-1' }));
    expect(store.join).toHaveBeenCalledWith('room-1', 'user-alice');
    expect(result).toMatchObject({ type: 'joined', roomId: 'room-1', memberCount: 2 });
  });

  it('join: broadcasts the joined event to other members', async () => {
    await handler.handle(JSON.stringify({ type: 'join', roomId: 'room-1' }));
    expect(store.broadcast).toHaveBeenCalledWith(
      'room-1',
      expect.objectContaining({ type: 'joined' }),
      'user-alice' // excludes the joining user
    );
  });

  it('chat: broadcasts message and returns null (no self-echo)', async () => {
    const result = await handler.handle(JSON.stringify({ type: 'chat', roomId: 'room-1', text: 'hello' }));
    expect(store.broadcast).toHaveBeenCalledWith(
      'room-1',
      expect.objectContaining({ type: 'chat', from: 'user-alice', text: 'hello' }),
      // No excludeUserId — sender sees the echo through broadcast
    );
    expect(result).toBeNull();
  });

  it('chat: includes a timestamp', async () => {
    const before = Date.now();
    await handler.handle(JSON.stringify({ type: 'chat', roomId: 'r1', text: 'hi' }));
    const [, outgoing] = vi.mocked(store.broadcast).mock.calls[0] as any;
    expect(outgoing.ts).toBeGreaterThanOrEqual(before);
    expect(outgoing.ts).toBeLessThanOrEqual(Date.now());
  });
});
```

## Integration Testing the WebSocket Server

Test the full server stack — connection lifecycle, room management, and message relay — using Node.js's `ws` library as the test client.

### Test Helper: Promise-based WebSocket Client

```typescript
// tests/helpers/ws-client.ts
import WebSocket from 'ws';

export function createWsClient(url: string): {
  send: (msg: object) => void;
  next: () => Promise<object>;
  close: () => void;
  waitForClose: () => Promise<{ code: number; reason: string }>;
} {
  const ws = new WebSocket(url);
  const messageQueue: object[] = [];
  const waiters: Array<(msg: object) => void> = [];

  ws.on('message', data => {
    const msg = JSON.parse(data.toString());
    const waiter = waiters.shift();
    if (waiter) waiter(msg);
    else messageQueue.push(msg);
  });

  return {
    send: (msg) => ws.send(JSON.stringify(msg)),
    next: () =>
      new Promise(resolve => {
        if (messageQueue.length > 0) return resolve(messageQueue.shift()!);
        waiters.push(resolve);
      }),
    close: () => ws.close(),
    waitForClose: () =>
      new Promise(resolve =>
        ws.on('close', (code, reason) => resolve({ code, reason: reason.toString() }))
      ),
  };
}

export function waitForOpen(url: string): Promise<ReturnType<typeof createWsClient>> {
  return new Promise((resolve, reject) => {
    const client = createWsClient(url);
    const ws = (client as any)._ws ?? client; // hook if needed
    // Small delay for open event
    setTimeout(() => resolve(client), 50);
  });
}
```

### Server Integration Tests

```typescript
// src/realtime/server.integration.test.ts
import { beforeAll, afterAll, beforeEach, describe, it, expect } from 'vitest';
import { createRealtimeServer } from './server';
import { createWsClient } from '../../tests/helpers/ws-client';
import type { Server } from 'node:http';

let server: Server;
let port: number;

beforeAll(async () => {
  server = await createRealtimeServer();
  await new Promise<void>(res => server.listen(0, res));
  port = (server.address() as { port: number }).port;
});

afterAll(() => server.close());

async function connect(): Promise<ReturnType<typeof createWsClient>> {
  const client = createWsClient(`ws://localhost:${port}`);
  // Wait for connection to open
  await new Promise(res => setTimeout(res, 30));
  return client;
}

describe('WebSocket server', () => {
  it('accepts a connection and echoes a welcome message', async () => {
    const client = await connect();
    const msg = await client.next();
    expect(msg).toMatchObject({ type: 'welcome' });
    client.close();
  });

  it('delivers a chat message to all room members', async () => {
    const alice = await connect();
    const bob = await connect();

    // Both join the same room
    alice.send({ type: 'join', roomId: 'test-room' });
    await alice.next(); // welcome
    await alice.next(); // joined confirmation

    bob.send({ type: 'join', roomId: 'test-room' });
    await bob.next(); // welcome
    await bob.next(); // joined confirmation

    // Alice sends a message
    alice.send({ type: 'chat', roomId: 'test-room', text: 'Hello Bob!' });

    // Bob should receive it
    const bobReceived = await bob.next();
    expect(bobReceived).toMatchObject({ type: 'chat', text: 'Hello Bob!', roomId: 'test-room' });

    alice.close(); bob.close();
  });

  it('does not deliver messages to members of a different room', async () => {
    const alice = await connect();
    const charlie = await connect();

    alice.send({ type: 'join', roomId: 'room-a' });
    charlie.send({ type: 'join', roomId: 'room-b' });

    // Let both joins complete
    await new Promise(res => setTimeout(res, 50));
    alice.send({ type: 'chat', roomId: 'room-a', text: 'Private message' });

    // Charlie should not receive the message from room-a
    const received = await Promise.race([
      charlie.next().then(() => 'received'),
      new Promise(res => setTimeout(() => res('timeout'), 300)),
    ]);
    expect(received).toBe('timeout');

    alice.close(); charlie.close();
  });

  it('removes user from room on disconnect', async () => {
    const alice = await connect();
    const bob = await connect();

    alice.send({ type: 'join', roomId: 'disconnect-room' });
    bob.send({ type: 'join', roomId: 'disconnect-room' });
    await new Promise(res => setTimeout(res, 50));

    alice.close();
    await new Promise(res => setTimeout(res, 100));

    // Bob should receive a 'left' notification
    const leftMsg = await bob.next();
    expect(leftMsg).toMatchObject({ type: 'member_left', roomId: 'disconnect-room' });

    bob.close();
  });
});
```

## End-to-End Testing with Playwright

```typescript
// e2e/chat.spec.ts
import { test, expect } from '@playwright/test';

test('two users can exchange messages in real time', async ({ browser }) => {
  // Open two separate browser contexts to simulate two users
  const alice = await browser.newContext();
  const bob = await browser.newContext();
  const alicePage = await alice.newPage();
  const bobPage = await bob.newPage();

  await alicePage.goto('/chat/room-e2e');
  await bobPage.goto('/chat/room-e2e');

  // Wait for both to connect (WebSocket status indicator)
  await expect(alicePage.getByTestId('connection-status')).toHaveText('Connected');
  await expect(bobPage.getByTestId('connection-status')).toHaveText('Connected');

  // Alice sends a message
  await alicePage.getByLabel('Message').fill('Hello from Alice');
  await alicePage.getByRole('button', { name: 'Send' }).click();

  // Bob sees it in his message list
  await expect(bobPage.getByRole('listitem').filter({ hasText: 'Hello from Alice' })).toBeVisible();

  // Bob replies
  await bobPage.getByLabel('Message').fill('Hi Alice!');
  await bobPage.getByRole('button', { name: 'Send' }).click();
  await expect(alicePage.getByRole('listitem').filter({ hasText: 'Hi Alice!' })).toBeVisible();

  await alice.close();
  await bob.close();
});

test('UI shows reconnecting state when connection drops', async ({ page }) => {
  await page.goto('/chat/room-e2e');
  await expect(page.getByTestId('connection-status')).toHaveText('Connected');

  // Simulate network offline
  await page.context().setOffline(true);
  await expect(page.getByTestId('connection-status')).toHaveText('Reconnecting…', { timeout: 5000 });

  // Restore connection
  await page.context().setOffline(false);
  await expect(page.getByTestId('connection-status')).toHaveText('Connected', { timeout: 10000 });
});
```

## Load Testing WebSocket Connections

```javascript
// load-tests/ws-fanout.js  (k6 with k6-websockets)
import { WebSocket } from 'k6/experimental/websockets';
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';

const messagesReceived = new Counter('ws_messages_received');
const messageLatency = new Trend('ws_message_latency_ms');

export const options = {
  scenarios: {
    fanout: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 200 },  // ramp to 200 concurrent connections
        { duration: '60s', target: 200 },  // hold
        { duration: '10s', target: 0 },    // ramp down
      ],
    },
  },
  thresholds: {
    ws_message_latency_ms: ['p(95)<500'],  // 95th percentile under 500ms
    ws_messages_received: ['count>1000'],
  },
};

export default function () {
  const ws = new WebSocket('wss://api.example.com/ws');
  let sentAt: number;

  ws.onopen = () => {
    ws.send(JSON.stringify({ type: 'join', roomId: 'load-test-room' }));
    sleep(1);
    sentAt = Date.now();
    ws.send(JSON.stringify({ type: 'chat', roomId: 'load-test-room', text: 'ping' }));
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'chat') {
      messagesReceived.add(1);
      messageLatency.add(Date.now() - sentAt);
    }
    check(msg, { 'message has type': m => !!m.type });
  };

  ws.onerror = (e) => console.error('WS error', e);
  sleep(10);
  ws.close();
}
```

## Anti-patterns

- **Using `setTimeout` for synchronization in tests** — `await new Promise(res => setTimeout(res, 500))` makes tests slow and flaky. Use event-driven helpers that resolve when a specific message arrives, not after an arbitrary delay.
- **Testing a single connection in isolation** — the most common WebSocket bugs involve multiple concurrent connections (broadcast fanout, room membership, disconnect cleanup). Always write multi-client tests.
- **Not testing disconnection cleanup** — if a client disconnects without sending a `leave` message (e.g., browser tab close, network drop), the server must clean up room membership. Explicitly test `client.close()` cleanup.
- **Asserting exact message ordering without acknowledging async non-determinism** — if two messages arrive in rapid succession, queue them and assert on the full batch, not on individual `next()` calls with interleaved `send()`.
- **Not testing the reconnect loop** — clients reconnect after drops. If the server creates a new room session for each connection without merging state, the user silently loses unread messages. Test the reconnect flow.

## Gotchas

- **`ws.onopen` may fire before your test setup completes** — buffer messages and wait for an explicit ready signal, or add a small delay after constructing the client before sending the first message.
- **Cloudflare Workers WebSocket hibernation** — Workers with WebSocket connections enter hibernation between messages. The `webSocketMessage` handler is invoked fresh on each message. Do not store per-connection state in local variables; use Durable Object storage.
- **Node.js `ws` library vs browser WebSocket** — the Node.js `ws` package uses `ws.on('message', ...)` while the browser uses `ws.onmessage = ...`. Write integration test helpers around the Node API; write E2E tests via Playwright which uses a real browser.
- **k6 experimental WebSockets** — the `k6/experimental/websockets` module follows the browser WebSocket API. Earlier k6 versions use `k6/ws` with a different API. Check your k6 version.
- **`page.context().setOffline(true)` in Playwright** — this disables all network, including requests needed to restore the WebSocket. Reconnect tests may need a short delay before going offline to ensure the initial connection is established.

## Verification

```bash
# Unit tests for message handler
npx vitest run src/realtime/message-handler.test.ts

# Integration tests (requires the server to start)
npx vitest run src/realtime/server.integration.test.ts

# E2E tests (requires full app)
npx playwright test e2e/chat.spec.ts

# Load test against local server
npm run start &
k6 run load-tests/ws-fanout.js --env WS_URL=ws://localhost:3000/ws
```

Confirm:
- The multi-client broadcast test passes (bob receives alice's message).
- The disconnect cleanup test passes (bob receives `member_left` after alice disconnects).
- The reconnect E2E test passes (UI shows "Reconnecting…" then "Connected").
- The k6 load test shows `ws_message_latency_ms` p95 under 500 ms at 200 concurrent connections.

## Related

- `streaming-sse-testing.md`
- `event-driven-async-api-testing.md`
- `event-driven-testing.md`
- `playwright-network-interception.md`
- `rate-limit-testing-strategies.md`
- `k6-load-testing-cloudflare-workers-api.md`

## Sources

- Cloudflare Workers WebSocket hibernation: https://developers.cloudflare.com/workers/configuration/compatibility-dates/#new-websocket-hibernation-behavior
- Playwright `setOffline`: https://playwright.dev/docs/api/class-browsercontext#browser-context-set-offline
- k6 experimental WebSockets: https://grafana.com/docs/k6/latest/javascript-api/k6-experimental/websockets/
- Node.js `ws` library: https://github.com/websockets/ws
- MDN WebSocket API: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket
