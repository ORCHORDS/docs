# K6 Workers Durable Objects Connection Limit Load Test

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project uses a Durable Object per anonymous chat room to fan out messages to connected WebSocket
clients. Under load, each DO instance has a finite number of concurrent WebSocket connections it
can hold before the runtime starts rejecting new connections or hibernating idle sockets. The team
needed a k6 load test that ramps connections toward the documented limit to find where the DO
instance starts returning errors, latency spikes, or starts evicting hibernated sessions.

## Context

Cloudflare Durable Objects support WebSocket Hibernation API, which allows the DO to sleep between
messages while keeping sockets open — but the DO still has a per-instance connection ceiling. The
k6 test targets a single DO instance (fixed room ID) to concentrate load on one object rather than
spreading it across many shards. The `k6-websocket` API (built-in `ws` module) is used; k6 Cloud
or a self-hosted k6 runner with `--out cloud` is recommended so that output metrics are preserved.

## K6 Script: Ramping WebSocket Connections to a Single DO

```javascript
// tests/load/do-connection-limit.js
import ws from "k6/ws";
import { check, sleep } from "k6";
import { Counter, Gauge, Rate, Trend } from "k6/metrics";

const connectErrors = new Counter("do_connect_errors");
const activeConnections = new Gauge("do_active_connections");
const messageLatency = new Trend("do_message_latency_ms");
const errorRate = new Rate("do_error_rate");

// Target a single DO instance by using a fixed room ID
const ROOM_ID = "load-test-room-fixed";
const BASE_URL = __ENV.WORKER_WS_URL ?? "wss://preview.example.com";
const WS_URL = `${BASE_URL}/room/${ROOM_ID}/ws`;

export const options = {
  scenarios: {
    ramp_connections: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 50 },   // warm up
        { duration: "60s", target: 200 },  // approach limit
        { duration: "60s", target: 400 },  // push past expected limit
        { duration: "30s", target: 0 },    // drain
      ],
      gracefulRampDown: "15s",
    },
  },
  thresholds: {
    do_error_rate: ["rate<0.05"],          // <5% connection errors acceptable
    do_message_latency_ms: ["p95<500"],
    do_connect_errors: ["count<20"],
  },
};

export default function () {
  const res = ws.connect(
    WS_URL,
    { headers: { "x-anon-token": __ENV.ANON_TOKEN ?? "test" } },
    function (socket) {
      activeConnections.add(1);

      socket.on("open", () => {
        socket.send(JSON.stringify({ type: "ping", ts: Date.now() }));
      });

      socket.on("message", (raw) => {
        const msg = JSON.parse(raw);
        if (msg.type === "pong" && msg.ts) {
          messageLatency.add(Date.now() - msg.ts);
        }
      });

      socket.on("error", (e) => {
        connectErrors.add(1);
        errorRate.add(1);
      });

      socket.on("close", () => {
        activeConnections.add(-1);
        errorRate.add(0);
      });

      // Hold the connection for 10 s then close cleanly
      sleep(10);
      socket.close();
    }
  );

  check(res, {
    "WebSocket connection established": (r) => r && r.status === 101,
  });
}
```

## Durable Object Handler Under Test

```typescript
// src/objects/ChatRoom.ts (excerpt — connection bookkeeping)
import { DurableObject } from "cloudflare:workers";

interface Session {
  socket: WebSocket;
  connectedAt: number;
}

export class ChatRoom extends DurableObject {
  private sessions: Map<string, Session> = new Map();

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }

    const currentCount = this.sessions.size;
    const MAX_CONNECTIONS = 900; // conservative ceiling below the runtime limit
    if (currentCount >= MAX_CONNECTIONS) {
      return new Response("Room full", { status: 503 });
    }

    const [client, server] = Object.values(new WebSocketPair()) as [
      WebSocket,
      WebSocket
    ];

    const id = crypto.randomUUID();
    this.ctx.acceptWebSocket(server, [id]);
    this.sessions.set(id, { socket: server, connectedAt: Date.now() });

    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, message: string): Promise<void> {
    const msg = JSON.parse(message);
    if (msg.type === "ping") {
      ws.send(JSON.stringify({ type: "pong", ts: msg.ts }));
    }
  }

  async webSocketClose(ws: WebSocket, code: number): Promise<void> {
    const tags = this.ctx.getTags(ws);
    if (tags[0]) this.sessions.delete(tags[0]);
  }
}
```

## Interpreting Results and Finding the Connection Ceiling

```typescript
// scripts/analyze-do-limit.ts — post-processing k6 JSON summary
import * as fs from "node:fs";

interface K6Summary {
  metrics: {
    do_connect_errors: { values: { count: number } };
    do_active_connections: { values: { max: number } };
    do_error_rate: { values: { rate: number } };
    do_message_latency_ms: { values: { "p(95)": number } };
  };
}

const summary: K6Summary = JSON.parse(
  fs.readFileSync("./k6-summary.json", "utf8")
);

const peakConnections = summary.metrics.do_active_connections.values.max;
const errorRate = summary.metrics.do_error_rate.values.rate;
const connectErrors = summary.metrics.do_connect_errors.values.count;
const p95Latency = summary.metrics.do_message_latency_ms.values["p(95)"];

console.log(`Peak simultaneous connections : ${peakConnections}`);
console.log(`Error rate                    : ${(errorRate * 100).toFixed(2)}%`);
console.log(`Total connect errors          : ${connectErrors}`);
console.log(`p95 message latency           : ${p95Latency.toFixed(0)} ms`);

if (connectErrors > 0) {
  console.warn(
    `DO started rejecting connections before ${peakConnections} peers.`
  );
}
```

```bash
# Run the load test and capture a JSON summary
k6 run \
  --out json=k6-output.json \
  --summary-export=k6-summary.json \
  -e WORKER_WS_URL=wss://preview.example.com \
  -e ANON_TOKEN=load-test-token \
  tests/load/do-connection-limit.js

npx tsx scripts/analyze-do-limit.ts
```

## Anti-patterns

- Spreading VUs across many different room IDs — this shards the load across many DO instances and never stress-tests a single object.
- Using HTTP polling instead of WebSockets — the DO connection model is fundamentally WebSocket-based; polling tests a different code path.
- Checking only HTTP status 200 instead of 101 for WebSocket upgrades — all connections will appear successful even when the DO rejects the upgrade.
- Running the ramp test against the production Worker — always target a preview or staging environment; a room can fill up and deny real users.
- Omitting `gracefulRampDown` — VUs cut off mid-connection leave unclosed sockets on the DO, which can inflate apparent connection counts in the next test run.

## Gotchas

- The k6 built-in `ws` module does not support the WebSocket Hibernation API from the client side; test `close` events are still sent after the `sleep`.
- Cloudflare does not publish an exact per-DO WebSocket connection limit; empirically it is in the hundreds to low thousands depending on message size and DO region.
- `activeConnections` is a `Gauge` — it can go negative momentarily if a socket fires `close` before `open`; clamp at 0 in analysis scripts.
- The DO must be in the same Cloudflare account as the test runner's IP; cross-account targeting may trigger bot-mitigation rules that distort results.
- `ctx.getTags(ws)` returns an array; the connection ID is at index 0 — ensure the tag is set during `acceptWebSocket` or session cleanup silently fails.

## Verification

Run the test against preview, check that:
1. `do_active_connections` max matches expected VU count at peak stage.
2. `do_connect_errors` count is 0 below your `MAX_CONNECTIONS` guard.
3. `do_message_latency_ms p95` stays under 500 ms through all ramp stages.
4. The Worker returns HTTP 503 with body `"Room full"` once the limit is reached — confirm in k6 output with `check` assertions.

## Related

- documentation/categories/testing/k6-durable-objects-websocket-load-test.md
- documentation/categories/testing/durable-objects-websocket-hibernation-testing.md
- documentation/categories/testing/k6-workers-rate-limiter-load-test.md
- documentation/categories/testing/grafana-k6-cloud-workers-stress-test.md

## Sources

- https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- https://developers.cloudflare.com/durable-objects/reference/websockets/
- https://k6.io/docs/using-k6/metrics/create-custom-metrics/
- https://k6.io/docs/javascript-api/k6-ws/
- https://developers.cloudflare.com/durable-objects/platform/limits/
