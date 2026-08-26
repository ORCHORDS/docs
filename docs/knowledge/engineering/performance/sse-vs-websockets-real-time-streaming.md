# Server-Sent Events vs WebSockets — Real-Time Streaming Architecture

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your dashboard application uses WebSockets to push live metrics to the
browser. The implementation requires a custom reconnection layer, a
heartbeat protocol, sticky sessions at the load balancer, and special
NGINX configuration for the protocol upgrade. Corporate proxies
intermittently drop the WebSocket connection because they do not
understand the `Upgrade` header. Meanwhile, a teammate points out that
data only flows server-to-client — the browser never sends messages
back through the socket.

## Context

Server-Sent Events (SSE) is a browser-native protocol for server-to-
client streaming over plain HTTP. In 2026, SSE has become the dominant
transport for LLM token streaming (OpenAI, Anthropic, and others use
it), live feeds, CI logs, and notification systems. The EventSource API
provides automatic reconnection and last-event-ID replay out of the
box. Under HTTP/2, SSE streams multiplex over a single TCP connection,
eliminating the old 6-connection-per-origin limit. WebSockets remain
the right choice for bidirectional communication — chat, gaming,
collaborative editing — but most real-time use cases are unidirectional
and better served by SSE.

## SSE protocol format

```
SSE message format (plain text over HTTP):

  id: 42
  event: progress
  retry: 3000
  data: {"step": 5, "message": "Processing..."}

Fields:
  data:     Payload (required). Multiple data: lines concatenated with \n
  id:       Event ID. Sent back as Last-Event-ID on reconnect
  event:    Named event type (default: "message")
  retry:    Reconnection delay in milliseconds
  :         Comment line (used for heartbeats)

Each message terminated by two newlines: \n\n
```

## Client implementation

```javascript
// Standard EventSource — built-in reconnection
const es = new EventSource("/stream");

es.addEventListener("progress", (event) => {
  const payload = JSON.parse(event.data);
  updateUI(payload);
});

es.addEventListener("done", () => es.close());
es.onerror = () => console.log("Reconnecting automatically...");
```

```javascript
// Fetch + ReadableStream — when custom headers are needed
// EventSource does not support Authorization headers
import { fetchEventSource } from '@microsoft/fetch-event-source';

await fetchEventSource('/api/stream', {
  headers: { Authorization: `Bearer ${token}` },
  onmessage(ev) {
    const data = JSON.parse(ev.data);
    updateUI(data);
  },
  onclose() { console.log('Stream ended'); },
  onerror(err) { console.error('SSE error', err); },
});
```

## Server implementation

```javascript
// Node.js — critical headers for SSE
app.get('/events', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache, no-transform',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no',
  });

  const heartbeat = setInterval(() => res.write(':hb\n\n'), 25000);

  req.on('close', () => {
    clearInterval(heartbeat);
    // Remove from subscriber list — forgetting this is the #1 SSE bug
  });
});
```

```python
# FastAPI — with event IDs for reconnection replay
async def event_generator(request: Request):
    yield "retry: 3000\n\n"
    for i in range(1, 100):
        if await request.is_disconnected():
            break
        data = {"step": i, "ts": time.time()}
        yield f"id: {i}\nevent: progress\ndata: {json.dumps(data)}\n\n"
        await asyncio.sleep(0.1)
```

## When to use each

```
                   SSE                          WebSocket
─────────────────────────────────────────────────────────────────
Direction:         Server → Client              Bidirectional
Protocol:          HTTP (no upgrade)             WS (upgrade handshake)
Reconnection:      Built-in (EventSource)        Manual implementation
Data format:       UTF-8 text only               Text + binary frames
Auth headers:      Not with EventSource          On upgrade handshake
                   (use fetch-event-source)
Proxy compat:      Excellent (plain HTTP)         Poor (upgrade issues)
HTTP/2 benefit:    Stream multiplexing            Separate TCP connection
Typical use:       Notifications, AI streaming,   Chat, gaming,
                   dashboards, CI logs             collaborative editing
```

## Scalability architecture

```
Fan-out pattern (recommended at scale):

  Business logic → Pub/Sub (Redis Streams / NATS / Kafka)
                        ↓
              SSE fan-out tier (lightweight Node.js)
                   ↓          ↓          ↓
              Client A    Client B    Client C

Single Node.js process capacity: 5,000-10,000 idle SSE connections
Documented case study: 2 pods handling ~60k concurrent SSE connections
  at ~50MB/s outbound with 35% infrastructure cost reduction vs WebSockets
```

```nginx
# NGINX reverse proxy configuration for SSE
location /events {
    proxy_pass http://backend;
    proxy_read_timeout 1h;
    proxy_send_timeout 1h;
    proxy_buffering off;
    chunked_transfer_encoding off;
    proxy_set_header X-Accel-Buffering no;
}
```

## Anti-patterns

- **Using WebSockets for unidirectional streams** — SSE is simpler,
  proxy-friendly, and auto-reconnects. WebSockets add complexity for
  no benefit when data flows one way.
- **Forgetting `req.on('close')` cleanup** — the number one SSE bug.
  Leaked connections cause memory growth and eventually crash the
  process.
- **Relying on sticky sessions at scale** — use a pub/sub backbone
  (Redis Streams, NATS) instead of pinning clients to servers.
- **Large payloads per event** — keep SSE messages under a few KB.
  For larger data, send a reference and let the client fetch.

## Gotchas

- **EventSource does not support custom headers** — no Authorization
  header means you cannot use it with bearer token auth. Use
  `@microsoft/fetch-event-source` or query-parameter tokens instead.
- **HTTP/1.1 connection limit** — browsers allow only 6 concurrent
  connections per origin under HTTP/1.1. Multiple SSE streams from
  the same origin exhaust this. HTTP/2 fixes this via multiplexing.
- **Proxy buffering kills streaming** — corporate proxies, CDNs, and
  reverse proxies may buffer SSE responses. Set `X-Accel-Buffering:
  no`, `Cache-Control: no-transform`, and disable compression on SSE
  routes.
- **Heartbeat timing** — send heartbeat comments (`:hb\n\n`) every
  15-30 seconds. Load balancers typically drop idle connections after
  60 seconds. Too frequent wastes bandwidth; too infrequent causes
  disconnects.
- **Reconnection thundering herd** — add 25% jitter to the `retry:`
  delay. Without jitter, a server restart causes all clients to
  reconnect simultaneously.

## Verification

- SSE is used for all server-to-client-only streams.
- EventSource reconnection tested (kill server, verify auto-reconnect).
- `Last-Event-ID` replay works correctly after reconnection.
- NGINX/proxy configuration disables buffering on SSE routes.
- Heartbeats prevent idle timeout disconnections.
- Fan-out architecture separates business logic from connection management.

## Related

- `documentation/docs/policies/performance/critical-rendering-path-css-optimization.md`
- `documentation/docs/policies/performance/api-rate-limiting-throttling-strategies.md`
- `documentation/docs/policies/architecture/event-sourcing-projections-snapshots.md`

## Source URLs (verified 2026-08-16)

- WebSockets vs SSE: Key Differences and Which to Use in 2026 — https://ably.com/blog/websockets-vs-sse
- Server-Sent Events in 2026: Streaming Architecture, Scalability, and Real-Time UX — https://thebackenddevelopers.substack.com/p/server-sent-events-in-2026-streaming
- Streaming from the Browser: SSE That Actually Scales — https://medium.com/@Modexa/streaming-from-the-browser-sse-that-actually-scales-f6c91a0faaf0
- Node.js SSE in 2026: The Production Guide — https://www.hirenodejs.com/blog/nodejs-server-sent-events-sse-2026
