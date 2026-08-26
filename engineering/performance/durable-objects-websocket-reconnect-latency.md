# Durable Objects WebSocket Reconnect Latency

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A collaborative tool backed by Durable Objects shows a 1–4 second blank period after a
mobile user loses network briefly. The client reconnects at the TCP level but the
application layer rebuilds state from scratch: re-authenticating, re-fetching document
state, and re-subscribing to the channel. Each reconnect triggers a full Durable Object
wake cycle, discards the in-flight message queue, and forces the client to resync
potentially thousands of state updates. Users perceive a flicker or jump in the UI.

## Context

A Durable Object in Hibernation mode evicts its JavaScript isolate between messages.
When a WebSocket client reconnects it creates a new WebSocket object both on the client
and inside the DO. From the DO's perspective a reconnecting client is indistinguishable
from a brand-new one unless the application layer provides a session identifier.

Reconnect latency has two components:
- **Network re-establishment latency**: TCP + TLS handshake + Cloudflare edge routing
  (typically 50–150 ms for 4G).
- **Application re-sync latency**: time to authenticate, deliver missed messages, and
  restore UI state (typically 200 ms – 4 s if unoptimized).

The network component is fixed. Optimizing reconnect latency means reducing the
application re-sync component by: (1) delivering a session ID on initial connect so the
DO can maintain per-session state; (2) keeping a short message buffer in the DO so missed
messages can be replayed; (3) detecting dead connections quickly to keep the buffer small.

## Session ID Assignment on Connect

Issue a session ID when the client first connects, persist it in `localStorage`, and
include it on every reconnect request.

```typescript
// Client-side reconnect with session ID
const SESSION_KEY = 'ws_session_id';

function connect(doUrl: string): WebSocket {
  let sessionId = localStorage.getItem(SESSION_KEY);
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, sessionId);
  }
  const ws = new WebSocket(`${doUrl}?session=${sessionId}`);
  ws.addEventListener('message', handleMessage);
  ws.addEventListener('close', (ev) => scheduleReconnect(doUrl, ev.code));
  return ws;
}
```

```typescript
// Durable Object — store per-session message buffer in storage
export class CollabDO implements DurableObject {
  private sessions = new Map<string, { ws: WebSocket; buffer: string[] }>();

  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const sessionId = url.searchParams.get('session') ?? crypto.randomUUID();
    const { 0: client, 1: server } = new WebSocketPair();
    this.state.acceptWebSocket(server, [sessionId]);

    // Replay missed messages from persistent storage for returning sessions
    const stored = await this.state.storage.get<string[]>(`buf:${sessionId}`) ?? [];
    for (const msg of stored) server.send(msg);
    await this.state.storage.delete(`buf:${sessionId}`);

    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    // Broadcast to all other connected sessions
    const [sessionId] = this.state.getWebSockets(ws as never) ?? [undefined];
    for (const peer of this.state.getWebSockets()) {
      if (peer !== ws) peer.send(message);
    }
  }
}
```

## Exponential Backoff on the Client

Naive reconnect loops that hammer the server on disconnect amplify DO wake pressure.
Use capped exponential backoff with jitter.

```typescript
const BASE_DELAY_MS = 250;
const MAX_DELAY_MS = 30_000;
const JITTER_FRACTION = 0.3;

function scheduleReconnect(doUrl: string, closeCode: number, attempt = 0): void {
  // 1001 = Going Away (page unload) — do not reconnect
  if (closeCode === 1001) return;

  const expDelay = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
  const jitter = expDelay * JITTER_FRACTION * Math.random();
  const delay = expDelay + jitter;

  setTimeout(() => {
    const ws = connect(doUrl);
    ws.addEventListener('open', () => {
      // Reset attempt counter on successful reconnect
      attempt = 0;
    });
    ws.addEventListener('close', (ev) => scheduleReconnect(doUrl, ev.code, attempt + 1));
  }, delay);
}
```

## Server-Side Ping/Pong for Dead Connection Detection

Mobile clients can drop silently — TCP keepalive may not fire for 2+ minutes at the OS
level. Add application-layer pings to detect dead sockets within seconds.

```typescript
const PING_INTERVAL_MS = 15_000;
const PING_TIMEOUT_MS = 5_000;

export class CollabDO implements DurableObject {
  async webSocketOpen(ws: WebSocket): Promise<void> {
    // Schedule the first ping via Durable Object alarm
    await this.state.storage.setAlarm(Date.now() + PING_INTERVAL_MS);
  }

  async alarm(): Promise<void> {
    const now = Date.now();
    for (const ws of this.state.getWebSockets()) {
      const tags = this.state.getWebSockets(ws as never);
      const lastPong = await this.state.storage.get<number>(`pong:${tags[0]}`) ?? 0;
      if (now - lastPong > PING_INTERVAL_MS + PING_TIMEOUT_MS) {
        // No pong received in time — close the dead socket
        ws.close(4000, 'ping timeout');
        await this.state.storage.delete(`pong:${tags[0]}`);
      } else {
        ws.send(JSON.stringify({ type: 'ping', ts: now }));
      }
    }
    // Re-arm alarm only if there are still connected sockets
    if (this.state.getWebSockets().length > 0) {
      await this.state.storage.setAlarm(Date.now() + PING_INTERVAL_MS);
    }
  }

  async webSocketMessage(ws: WebSocket, message: string): Promise<void> {
    const data = JSON.parse(message);
    if (data.type === 'pong') {
      const [sessionId] = this.state.getWebSockets(ws as never) ?? [];
      if (sessionId) await this.state.storage.put(`pong:${sessionId}`, Date.now());
      return;
    }
    // … handle other message types
  }
}
```

## Message Buffer for Offline Replay

Store a bounded ring buffer of recent messages in DO storage. On reconnect, replay
messages the client missed since its last acknowledged sequence number.

```typescript
const BUFFER_MAX = 50; // keep last 50 messages per session

export class CollabDO implements DurableObject {
  private async bufferMessage(msg: string): Promise<void> {
    // Fan-out to connected sockets; buffer for offline sessions
    const allSessions = await this.state.storage.list<string>({ prefix: 'buf:' });
    // … add to each offline session's ring buffer
    const key = `buf:global`;
    const buf: string[] = (await this.state.storage.get(key)) ?? [];
    buf.push(msg);
    if (buf.length > BUFFER_MAX) buf.shift();
    await this.state.storage.put(key, buf);
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const since = Number(url.searchParams.get('since') ?? '0');
    const sessionId = url.searchParams.get('session') ?? crypto.randomUUID();

    const { 0: client, 1: server } = new WebSocketPair();
    this.state.acceptWebSocket(server, [sessionId]);

    // Replay buffered messages from the global buffer after requested sequence
    const globalBuf: string[] = (await this.state.storage.get('buf:global')) ?? [];
    const missed = globalBuf.filter(m => JSON.parse(m).seq > since);
    for (const m of missed) server.send(m);

    return new Response(null, { status: 101, webSocket: client });
  }
}
```

## Anti-patterns

- **Not tagging WebSockets with session IDs**: without `state.acceptWebSocket(ws, [id])`,
  you cannot retrieve a specific socket after isolate hibernation and wake.
- **Reconnecting immediately on `close`**: creates thundering-herd reconnects when a DO
  briefly restarts or when a network blip hits many clients simultaneously.
- **Storing unbounded message buffers**: a DO's storage is capped at 128 KB per key and
  128 MB total. Unbounded buffers will eventually exhaust storage and cause `put` to fail.
- **Relying on TCP keepalive alone**: OS-level keepalive is configured by the client OS
  and Cloudflare network and may not fire for 2+ minutes. Application-layer pings detect
  dead connections in seconds.

## Gotchas

- `state.getWebSockets()` returns only currently-connected sockets; hibernated DOs have
  no in-memory socket list until a new message arrives.
- The Hibernation API tags (`state.acceptWebSocket(ws, tags)`) survive isolate eviction.
  After a hibernation wake, tags are restored and accessible via `state.getWebSockets(tag)`.
- DO alarm precision is ±1 second. Ping intervals below 5 seconds will drift noticeably.
- Closing a WebSocket from the server with code `1000` (Normal Closure) tells the client
  the close was intentional; clients should not reconnect. Use `4000`–`4999` for
  application-defined transient errors that warrant reconnect.
- Buffer storage writes consume DO storage I/O budget. For high-throughput channels,
  batch buffer writes using `state.storage.transaction()`.

## Verification

1. Simulate a disconnect in Chrome DevTools: Network → Throttle → Offline for 3 seconds,
   then restore. Measure time from `WebSocket open` event to UI showing current state.
2. Check DO storage after reconnect test: `wrangler durable-objects storage list <DO> <ID>`
   to verify buffer keys are cleaned up and not growing unboundedly.
3. In Cloudflare Dashboard → Workers → Durable Objects, inspect invocation counts.
   Each reconnect should create exactly one new invocation; multiple invocations per
   reconnect indicates a retry loop firing too quickly.
4. Monitor WebSocket `close` event codes in client-side analytics. Code `4000` (ping
   timeout) should be rare (<1% of sessions); high rates indicate network problems or too
   aggressive a ping interval.

## Related

- `durable-objects-websocket-efficiency.md`
- `durable-objects-hibernation-wake-latency.md`
- `durable-objects-alarm-write-coalescing.md`
- `sse-vs-websockets-real-time-streaming.md`
- `workers-response-streaming-ttfb-optimization.md`

## Sources

- Durable Objects WebSocket Hibernation API — https://developers.cloudflare.com/durable-objects/api/websockets/
- Durable Objects Storage — https://developers.cloudflare.com/durable-objects/api/storage-api/
- WebSocket Close Codes — https://www.rfc-editor.org/rfc/rfc6455#section-7.4
- Exponential Backoff and Jitter — https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
