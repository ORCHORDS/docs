# k6 Workers WebSocket Load Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker exposes a WebSocket endpoint — for chat, live data feeds, or
collaborative editing — and you need to verify it holds up under concurrent connections.
HTTP load testing tools skip the WS handshake, message framing, and backpressure
behaviour entirely. You want to run realistic WebSocket scenarios with k6: concurrent
connections, message round-trips, connection lifetime distribution, and error rates.

## Context

k6 ships a built-in `k6/ws` module that handles the WebSocket upgrade, message
dispatch, and connection teardown. Workers WebSocket endpoints typically live behind
a Durable Object (for room state) or are handled directly in the `fetch` handler with
`new WebSocketPair()`. This article focuses on the load test itself, not on Durable
Objects internals (see `k6-durable-objects-websocket-load-test.md` for that).

Target metrics for a production Workers WS endpoint:
- p95 connection establishment < 200 ms
- p95 message round-trip < 50 ms
- Error rate < 0.1 %
- Zero dropped messages under nominal load

---

## Basic Connection Test

```javascript
// k6/ws-connect.js
import ws from "k6/ws";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";

const connectErrors = new Counter("ws_connect_errors");
const messageRtt = new Trend("ws_message_rtt_ms", true);

export const options = {
  vus: 50,
  duration: "30s",
  thresholds: {
    ws_connect_errors: ["count<5"],
    ws_message_rtt_ms: ["p(95)<50"],
    checks: ["rate>0.99"],
  },
};

export default function () {
  const url = `wss://my-worker.example.workers.dev/ws`;

  const res = ws.connect(url, { headers: { Authorization: `Bearer ${__ENV.WS_TOKEN}` } }, (socket) => {
    socket.on("open", () => {
      const sentAt = Date.now();
      socket.send(JSON.stringify({ type: "ping", ts: sentAt }));
    });

    socket.on("message", (data) => {
      const msg = JSON.parse(data);
      if (msg.type === "pong") {
        messageRtt.add(Date.now() - msg.ts);
      }
      socket.close();
    });

    socket.on("error", (e) => {
      connectErrors.add(1);
      console.error(`WebSocket error: ${e.error()}`);
    });

    socket.setTimeout(() => socket.close(), 5000);
  });

  check(res, { "WS upgrade status 101": (r) => r && r.status === 101 });
  sleep(1);
}
```

---

## Sustained Connection Test

```javascript
// k6/ws-sustained.js
import ws from "k6/ws";
import { check, sleep } from "k6";
import { Counter, Trend, Rate } from "k6/metrics";

const connectErrors = new Counter("ws_connect_errors");
const messageRtt = new Trend("ws_message_rtt_ms", true);
const messageErrors = new Counter("ws_message_errors");
const successRate = new Rate("ws_success_rate");

export const options = {
  stages: [
    { duration: "30s", target: 100 },  // ramp up
    { duration: "2m",  target: 100 },  // sustain
    { duration: "30s", target: 0 },    // ramp down
  ],
  thresholds: {
    ws_connect_errors: ["count<10"],
    ws_message_rtt_ms: ["p(95)<75", "p(99)<150"],
    ws_success_rate: ["rate>0.995"],
  },
};

const MESSAGE_INTERVAL_MS = 2000;
const CONNECTION_DURATION_S = 60;

export default function () {
  const url = `wss://my-worker.example.workers.dev/ws`;
  let messagesSent = 0;
  let messagesAcked = 0;

  const res = ws.connect(url, {}, (socket) => {
    socket.on("open", () => {
      // Send a message every 2 seconds.
      socket.setInterval(() => {
        const ts = Date.now();
        socket.send(JSON.stringify({ type: "echo", seq: messagesSent++, ts }));
      }, MESSAGE_INTERVAL_MS);
    });

    socket.on("message", (data) => {
      try {
        const msg = JSON.parse(data);
        if (msg.type === "echo") {
          messageRtt.add(Date.now() - msg.ts);
          messagesAcked++;
        }
      } catch {
        messageErrors.add(1);
      }
    });

    socket.on("error", () => connectErrors.add(1));

    // Hold the connection for the configured duration.
    socket.setTimeout(() => socket.close(), CONNECTION_DURATION_S * 1000);
  });

  check(res, { "connected": (r) => r && r.status === 101 });

  // At least 90% of messages must be acknowledged.
  successRate.add(messagesAcked / Math.max(1, messagesSent) >= 0.9);
  sleep(1);
}
```

---

## Broadcast Fan-out Test

Simulates one publisher and many subscribers — common for live dashboards.

```javascript
// k6/ws-broadcast.js
import ws from "k6/ws";
import { check } from "k6";
import { Counter, Trend } from "k6/metrics";

const broadcastReceived = new Counter("ws_broadcasts_received");
const broadcastLatency = new Trend("ws_broadcast_latency_ms", true);

export const options = {
  scenarios: {
    publisher: {
      executor: "constant-vus",
      vus: 1,
      duration: "60s",
      env: { ROLE: "publisher" },
      tags: { role: "publisher" },
    },
    subscribers: {
      executor: "ramping-vus",
      stages: [
        { duration: "15s", target: 200 },
        { duration: "30s", target: 200 },
        { duration: "15s", target: 0 },
      ],
      env: { ROLE: "subscriber" },
      tags: { role: "subscriber" },
    },
  },
  thresholds: {
    ws_broadcast_latency_ms: ["p(95)<100"],
    ws_broadcasts_received: ["count>1000"],
  },
};

const ROOM = "load-test-room";

export default function () {
  const role = __ENV.ROLE;
  const url = `wss://my-worker.example.workers.dev/ws?room=${ROOM}&role=${role}`;

  ws.connect(url, {}, (socket) => {
    socket.on("open", () => {
      if (role === "publisher") {
        socket.setInterval(() => {
          socket.send(JSON.stringify({ type: "broadcast", data: "tick", ts: Date.now() }));
        }, 500);
      }
    });

    socket.on("message", (data) => {
      if (role === "subscriber") {
        try {
          const msg = JSON.parse(data);
          if (msg.type === "broadcast") {
            broadcastReceived.add(1);
            broadcastLatency.add(Date.now() - msg.ts);
          }
        } catch { /* ignore */ }
      }
    });

    socket.setTimeout(() => socket.close(), 60_000);
  });
}
```

---

## Running the Tests Against a Local Wrangler Dev Server

```bash
# Terminal 1 — start the Worker
npx wrangler dev --port 8787 --local

# Terminal 2 — run k6 against local
k6 run --env WS_TOKEN=dev-token \
        k6/ws-connect.js

# Against staging
k6 run --env WS_TOKEN="$(cat .staging-token)" \
        --env K6_WS_URL=wss://staging.example.workers.dev/ws \
        k6/ws-sustained.js
```

---

## Integrating with GitHub Actions

```yaml
# .github/workflows/ws-load-test.yml
name: WS Load Test
on:
  push:
    branches: [main]

jobs:
  k6:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install k6
        run: |
          sudo gpg -k
          sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
            --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
          echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
            | sudo tee /etc/apt/sources.list.d/k6.list
          sudo apt-get update && sudo apt-get install k6
      - name: Run WS load test
        env:
          WS_TOKEN: ${{ secrets.WS_LOAD_TEST_TOKEN }}
          K6_CLOUD_TOKEN: ${{ secrets.K6_CLOUD_TOKEN }}
        run: k6 run k6/ws-connect.js
```

---

## Anti-patterns

- Using the `http` module for a WebSocket endpoint. It follows the redirect but never
  completes the WS upgrade, resulting in a silent 426 or 200 treated as success.
- Opening connections without a `setTimeout` or `setInterval` close. Virtual users pile
  up with stale connections; the Worker hits its connection limit long before the VU
  target is reached.
- Setting `vus` to the production connection ceiling without a ramp-up stage. Workers
  WebSocket connections have per-account concurrency limits; a cold spike trips rate
  limiters unrelated to the Worker's performance.
- Measuring only connection establishment time. Message round-trip latency under load is
  the metric that reveals memory pressure and event-loop saturation in the Worker.

## Gotchas

- k6 WebSocket connections are not HTTP/2 multiplexed; each VU holds exactly one TCP
  connection. Plan VU count as a direct proxy for concurrent connection count.
- `wrangler dev --local` does not enforce the same connection limits as production
  Workers. Load results from local dev are useful for regression but not for capacity
  planning.
- Workers have a 25-second CPU time limit per request. Long-lived WebSocket connections
  bypass this limit only because the WS keep-alive does not consume CPU time between
  messages. Burst message processing can still hit the limit.
- `socket.on("close", ...)` receives a code and reason. Check for `1006` (abnormal
  closure) separately — it indicates a network error, not a clean shutdown.
- When running scenarios simultaneously (publisher + subscribers), k6 shares the same
  process. Metric counters are global; use tags to separate per-scenario numbers.

## Verification

```bash
k6 run --summary-trend-stats="avg,p(50),p(95),p(99),max" k6/ws-sustained.js
```

Expected summary shows `ws_message_rtt_ms p(95) < 75` and `ws_connect_errors count=0`.

## Related

- `k6-durable-objects-websocket-load-test.md` — load testing WS endpoints backed by Durable Objects
- `websocket-realtime-testing.md` — unit and integration testing WebSocket message flows
- `playwright-workers-websocket-durable-objects-e2e.md` — E2E browser-side WS testing
- `k6-load-testing-cloudflare-workers-api.md` — HTTP load testing patterns for Workers

## Sources

- https://k6.io/docs/javascript-api/k6-ws/
- https://k6.io/docs/using-k6/scenarios/
- https://developers.cloudflare.com/workers/runtime-apis/websockets/
- https://k6.io/docs/results-output/real-time/
