# k6 Durable Objects WebSocket Load Testing

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Cloudflare Durable Objects WebSocket service (chat room, collaborative editor, game lobby) handles real-time messages through the Hibernation API. You need to verify that a single DO instance stays responsive when 500 concurrent WebSocket connections send messages simultaneously, and that connection draining under load does not lose messages or corrupt shared state.

## Context

k6's `ws` module opens WebSocket connections that map directly to Cloudflare's WebSocket upgrade path. Each DO instance serialises all message handling through a single-threaded event loop. Load tests must distinguish between three failure modes: connection refusal at the Worker edge, message loss inside the DO, and alarm/eviction under memory pressure. Use `k6/ws` with the `k6-reporter` extension and route traffic through a dedicated test DO namespace binding separate from production.

---

## 1. Basic k6 WebSocket Script for a DO Chat Room

```javascript
// load/do-websocket.js
import ws from 'k6/ws';
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';

const msgReceived = new Counter('ws_messages_received');
const msgLatency = new Trend('ws_message_latency_ms', true);

export const options = {
  stages: [
    { duration: '30s', target: 100 },  // ramp up
    { duration: '2m',  target: 500 },  // sustained load
    { duration: '30s', target: 0 },    // ramp down
  ],
  thresholds: {
    ws_messages_received: ['count>10000'],
    ws_message_latency_ms: ['p(95)<300'],
    ws_connecting: ['p(95)<500'],
  },
};

const ROOM_ID = __ENV.ROOM_ID || 'load-test-room';
const BASE_URL = __ENV.BASE_URL || 'wss://my-app.workers.dev';

export default function () {
  const url = `${BASE_URL}/rooms/${ROOM_ID}/ws`;

  const res = ws.connect(url, {}, function (socket) {
    socket.on('open', () => {
      socket.send(JSON.stringify({ type: 'join', userId: `user-${__VU}` }));
    });

    socket.on('message', (data) => {
      const msg = JSON.parse(data);
      if (msg.type === 'pong') {
        msgLatency.add(Date.now() - msg.sentAt);
        msgReceived.add(1);
      }
    });

    socket.on('error', (e) => {
      console.error(`VU ${__VU}: WebSocket error: ${e.error()}`);
    });

    // Send a ping every 2 seconds for 30 seconds
    let count = 0;
    const interval = setInterval(() => {
      if (count >= 15) {
        clearInterval(interval);
        socket.close();
        return;
      }
      socket.send(JSON.stringify({ type: 'ping', sentAt: Date.now() }));
      count++;
    }, 2000);

    socket.setTimeout(() => socket.close(), 35000);
  });

  check(res, { 'WebSocket status 101': (r) => r && r.status === 101 });
  sleep(1);
}
```

---

## 2. DO Worker: Hibernation WebSocket Handler Under Test

```typescript
// src/chat-room.ts
import { DurableObject } from 'cloudflare:workers';
import type { Env } from './types';

export class ChatRoom extends DurableObject<Env> {
  private sessions: Map<WebSocket, { userId: string }> = new Map();

  async fetch(request: Request): Promise<Response> {
    const { 0: client, 1: server } = new WebSocketPair();
    this.ctx.acceptWebSocket(server);
    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const data = JSON.parse(message as string);

    if (data.type === 'join') {
      this.sessions.set(ws, { userId: data.userId });
      return;
    }

    if (data.type === 'ping') {
      ws.send(JSON.stringify({ type: 'pong', sentAt: data.sentAt }));
      return;
    }

    // Broadcast to all sessions
    for (const [client] of this.sessions) {
      if (client !== ws && client.readyState === WebSocket.READY_STATE_OPEN) {
        client.send(message);
      }
    }
  }

  async webSocketClose(ws: WebSocket): Promise<void> {
    this.sessions.delete(ws);
  }

  async webSocketError(ws: WebSocket, error: unknown): Promise<void> {
    this.sessions.delete(ws);
  }

  // Expose connection count for health checks during load test
  async getStats(): Promise<{ connections: number }> {
    return { connections: this.ctx.getWebSockets().length };
  }
}
```

---

## 3. Ramped Scenario with Multiple Rooms (Sharding Test)

```javascript
// load/do-sharded-websocket.js
import ws from 'k6/ws';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

const ROOM_COUNT = 10;
const rooms = new SharedArray('rooms', () =>
  Array.from({ length: ROOM_COUNT }, (_, i) => `load-test-room-${i}`)
);

export const options = {
  scenarios: {
    single_room_spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '20s', target: 200 },
        { duration: '1m',  target: 200 },
        { duration: '10s', target: 0 },
      ],
      env: { ROOM_MODE: 'single' },
    },
    sharded_rooms: {
      executor: 'ramping-vus',
      startTime: '2m',
      startVUs: 0,
      stages: [
        { duration: '20s', target: 200 },
        { duration: '1m',  target: 200 },
        { duration: '10s', target: 0 },
      ],
      env: { ROOM_MODE: 'sharded' },
    },
  },
};

export default function () {
  const roomId =
    __ENV.ROOM_MODE === 'sharded'
      ? rooms[__VU % ROOM_COUNT]
      : 'single-load-test-room';

  const url = `wss://my-app.workers.dev/rooms/${roomId}/ws`;

  ws.connect(url, {}, (socket) => {
    socket.on('open', () => socket.send(JSON.stringify({ type: 'ping', sentAt: Date.now() })));
    socket.on('message', () => socket.close());
    socket.setTimeout(() => socket.close(), 5000);
  });

  sleep(0.5);
}
```

---

## 4. Teardown: Delete DO State After Load Test

```javascript
// load/do-websocket.js (continued)
export function teardown() {
  // Call a test-only HTTP endpoint that resets DO storage
  const res = http.del(
    `https://my-app.workers.dev/__test/rooms/load-test-room`,
    null,
    { headers: { 'X-Test-Key': __ENV.TEST_KEY } }
  );
  check(res, { 'DO state cleared': (r) => r.status === 200 });
}
```

```typescript
// Worker: test-only room deletion endpoint
export async function handleTestRoomDelete(
  request: Request,
  env: Env
): Promise<Response> {
  if (env.ENVIRONMENT !== 'test') return new Response('Not found', { status: 404 });
  if (request.headers.get('X-Test-Key') !== env.TEST_KEY) {
    return new Response('Unauthorized', { status: 401 });
  }

  const roomId = new URL(request.url).pathname.split('/').at(-1)!;
  const id = env.CHAT_ROOM.idFromName(roomId);
  const stub = env.CHAT_ROOM.get(id);
  await stub.deleteAllState(); // custom RPC method
  return new Response(JSON.stringify({ ok: true }));
}
```

---

## 5. Asserting Message Ordering Under Load

```javascript
// load/do-ordering.js — verifies DO serialises messages in order
import ws from 'k6/ws';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const outOfOrder = new Counter('out_of_order_messages');

export const options = { vus: 50, duration: '30s' };

export default function () {
  let expected = 0;

  ws.connect(`wss://my-app.workers.dev/rooms/ordering-test/ws`, {}, (socket) => {
    socket.on('open', () => {
      for (let i = 0; i < 10; i++) {
        socket.send(JSON.stringify({ type: 'ordered', seq: i }));
      }
    });

    socket.on('message', (data) => {
      const { seq } = JSON.parse(data);
      if (seq !== expected) outOfOrder.add(1);
      expected = seq + 1;
      if (expected >= 10) socket.close();
    });

    socket.setTimeout(() => socket.close(), 5000);
  });

  check(null, { 'no out-of-order messages': () => outOfOrder.value === 0 });
}
```

---

## Anti-patterns

- **Using a single DO instance for all load test traffic**: This creates an artificial bottleneck that doesn't exist in production sharded deployments. Test both single-instance saturation and sharded scenarios separately.
- **Not calling `socket.close()` in teardown**: k6 VUs that keep sockets open past test end inflate connection counts and skew the next run.
- **Measuring latency from the k6 VU clock without NTP correction**: If your Workers deployment is in a distant region from the k6 runner, one-way latency measurements are meaningless. Use round-trip (ping/pong) instead.
- **Ignoring WebSocket 1006 (abnormal closure)**: Cloudflare may disconnect idle Hibernated sockets. Track abnormal closures as a separate metric.
- **Pointing load tests at production DO namespaces**: Always use a dedicated test namespace binding and environment flag.

---

## Gotchas

- Cloudflare enforces a 100 WebSocket connection limit per DO instance in the free tier; paid plans allow up to ~32,000 via Hibernation.
- k6's `ws` module does not support the `Sec-WebSocket-Protocol` header negotiation in older versions; upgrade to k6 >= 0.49.
- DO Hibernation evicts in-memory state (`this.sessions`) on sleep. Use `ctx.getWebSockets()` and `ws.deserializeAttachment()` to restore session metadata.
- The Workers edge may return `426 Upgrade Required` if the `Upgrade: websocket` header is missing; check proxy or CDN stripping headers.
- k6 Cloud has an outbound WebSocket limit per instance; for >10,000 VU WS tests, use distributed execution with `k6 run --execution-segment`.

---

## Verification

```bash
# Run a quick smoke test (10 VUs, 30 seconds)
k6 run --vus 10 --duration 30s \
  -e BASE_URL=wss://my-app.workers.dev \
  -e ROOM_ID=smoke-test-room \
  load/do-websocket.js

# Full load test with HTML report
k6 run --out json=results.json load/do-websocket.js
k6 report results.json

# Confirm DO connection count via health endpoint during test
watch -n2 'curl -s https://my-app.workers.dev/rooms/load-test-room/stats'
```

---

## Related

- `durable-objects-websocket-hibernation-testing.md`
- `k6-load-testing-cloudflare-workers-api.md`
- `websocket-realtime-testing.md`
- `durable-objects-alarm-testing-miniflare.md`
- `stress-testing-patterns.md`

---

## Sources

- k6 WebSocket API: https://grafana.com/docs/k6/latest/javascript-api/k6-ws/
- Cloudflare DO WebSocket Hibernation: https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- k6 scenarios: https://grafana.com/docs/k6/latest/using-k6/scenarios/
- DO connection limits: https://developers.cloudflare.com/durable-objects/platform/limits/
