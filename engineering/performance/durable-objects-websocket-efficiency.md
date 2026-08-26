# WebSocket Connection Efficiency with Durable Objects

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A multiplayer game's Durable Object serves 200 concurrent WebSocket connections.  The DO is billed for the entire duration those connections are held open — even when players are idle between moves.  CPU billing spikes unexpectedly because the DO cannot hibernate while any WebSocket is "active."  When a mobile user's connection drops in a tunnel and silently reconnects, the DO holds both the dead socket and the new one, doubling memory pressure.  A collaborative editor's DO broadcasts every keystroke to all 50 connected clients using a naïve loop, causing the broadcast to block new messages for 50 ms per keystroke.  These are all WebSocket efficiency problems specific to the Durable Objects execution model.

## Context

Cloudflare Durable Objects support two WebSocket management modes:

| Mode | API | DO billed while idle? | Memory held? |
|------|-----|-----------------------|-------------|
| **Standard** (`ws.accept()`) | `WebSocketPair` + manual `.accept()` | Yes — DO stays in memory | All sockets |
| **Hibernation** (`state.acceptWebSocket()`) | Hibernation API | No — DO evicted between messages | Runtime-managed |

**Hibernation mode** is the correct default for most WebSocket DOs.  The runtime holds the WebSocket connection itself (TCP/TLS layer) but evicts the JavaScript isolate when no message is in flight.  When a new message arrives, the isolate is re-instantiated, and the `webSocketMessage` handler is called.  This means:

- CPU billing: only during `webSocketMessage`, `webSocketClose`, `webSocketError`, and `alarm` execution
- Memory: only allocated during active message handling, not for idle sockets
- Scale: a single DO can hold **thousands** of hibernated WebSocket connections without proportional memory cost

The trade-off is that in-memory JavaScript state (instance variables) is not guaranteed to survive between messages in hibernation mode — all durable state must be in SQLite/KV storage.

## Section 1 — Setting Up WebSocket Hibernation

```javascript
// src/RoomDO.js
export class RoomDO {
  constructor(state, env) {
    this.state = state;
    this.env   = env;
    // DO NOT initialize large in-memory state here —
    // in hibernation mode the constructor may be called for every message
    this.state.blockConcurrencyWhile(async () => {
      this.roomName = await this.state.storage.get('roomName') ?? 'unnamed';
    });
  }

  async fetch(request) {
    const upgradeHeader = request.headers.get('Upgrade');
    if (!upgradeHeader || upgradeHeader !== 'websocket') {
      return new Response('Expected WebSocket upgrade', { status: 426 });
    }

    const [client, server] = Object.values(new WebSocketPair());

    // Use state.acceptWebSocket (hibernation) NOT server.accept() (standard)
    // Tags allow grouping sockets; used later with state.getWebSockets(tag)
    const userId = new URL(request.url).searchParams.get('userId') ?? 'anon';
    this.state.acceptWebSocket(server, [userId, 'room']);

    // Attach metadata — survives hibernation via the serialized attachment
    server.serializeAttachment({ userId, joinedAt: Date.now() });

    return new Response(null, {
      status:    101,
      webSocket: client,
    });
  }

  // Called by the runtime when a message arrives for any hibernated socket
  async webSocketMessage(ws, message) {
    const { userId, joinedAt } = ws.deserializeAttachment();
    let data;
    try {
      data = JSON.parse(message);
    } catch {
      ws.send(JSON.stringify({ error: 'invalid_json' }));
      return;
    }

    if (data.type === 'ping') {
      ws.send(JSON.stringify({ type: 'pong', ts: Date.now() }));
      return;
    }

    if (data.type === 'message') {
      const record = { userId, text: data.text, ts: Date.now() };
      // Persist to SQLite
      this.state.storage.sql.exec(
        `INSERT INTO messages (user_id, text, ts) VALUES (?, ?, ?)`,
        record.userId, record.text, record.ts
      );
      // Broadcast to all sockets in the room
      this.broadcastToRoom(JSON.stringify({ type: 'message', ...record }), ws);
    }
  }

  async webSocketClose(ws, code, reason, wasClean) {
    const { userId } = ws.deserializeAttachment();
    this.broadcastToRoom(
      JSON.stringify({ type: 'presence', userId, status: 'offline' }),
      ws
    );
  }

  async webSocketError(ws, error) {
    // Log but do not re-throw — let the runtime clean up the socket
    console.error('WebSocket error:', error);
  }

  broadcastToRoom(message, excludeWs) {
    for (const socket of this.state.getWebSockets('room')) {
      if (socket === excludeWs) continue;
      try {
        socket.send(message);
      } catch {
        // Socket may have closed between getWebSockets() and send()
      }
    }
  }
}
```

The critical change is `this.state.acceptWebSocket(server, tags)` instead of `server.accept()`.  Everything else — message handling, broadcast, presence — is the same, but the DO is now billed only for CPU during handler execution, not for idle connection time.

## Section 2 — Serialized Attachments for Per-Connection Metadata

In hibernation mode, the DO's JavaScript isolate is evicted between messages.  Instance variables (e.g., `this.userMap`) do not survive eviction.  Use **serialized attachments** on the WebSocket handle to persist per-connection metadata:

```javascript
// Attach metadata when the WebSocket is accepted
server.serializeAttachment({
  userId:    userId,
  joinedAt:  Date.now(),
  role:      'editor',        // custom fields
  sessionId: crypto.randomUUID(),
});

// Retrieve in any handler — survives hibernation
async webSocketMessage(ws, message) {
  const { userId, role, sessionId } = ws.deserializeAttachment();
  // ...
}
```

**Limits:** attachments are serialized with the structured clone algorithm.  They must be JSON-serializable-equivalent (no functions, no DOM nodes, no circular references).  Keep attachments small (< 2 KB) — each WebSocket's attachment contributes to the DO's storage overhead.

For large per-connection state, store it in SQLite keyed by a UUID that is stored in the attachment:

```javascript
// Accept
const connId = crypto.randomUUID();
server.serializeAttachment({ userId, connId });
this.state.storage.sql.exec(
  `INSERT INTO connections (id, user_id, state_json, created_at)
   VALUES (?, ?, ?, ?)`,
  connId, userId, JSON.stringify({ role: 'editor' }), Date.now()
);

// Later, on message
async webSocketMessage(ws, message) {
  const { connId } = ws.deserializeAttachment();
  const row = this.state.storage.sql.exec(
    `SELECT state_json FROM connections WHERE id = ?`, connId
  ).one();
  const connState = JSON.parse(row.state_json);
  // ...
}
```

## Section 3 — Efficient Broadcast with Tagging

Broadcasting to every connected client with `this.state.getWebSockets('room')` iterates over all sockets.  For large rooms (1,000+ connections), this is a synchronous loop that can block the event loop.  Optimize with **sub-room tagging** to broadcast only to relevant subsets:

```javascript
// Tag sockets by channel/shard when accepting
const channel = new URL(request.url).searchParams.get('channel') ?? 'main';
this.state.acceptWebSocket(server, [userId, 'room', `channel:${channel}`]);

// Broadcast only to a channel — avoids iterating all 1000 room sockets
broadcastToChannel(channel, message, excludeWs) {
  const tag = `channel:${channel}`;
  for (const socket of this.state.getWebSockets(tag)) {
    if (socket === excludeWs) continue;
    try { socket.send(message); } catch {}
  }
}
```

Tag granularity trades off memory (more tag indexes) against broadcast selectivity.  For games with rooms and teams, use `['room:${roomId}', 'team:${teamId}']` — broadcast to a team with `getWebSockets('team:red')` touches only team members.

**Chunked broadcast** for very large broadcasts (> 500 sockets) to avoid blocking:

```javascript
async broadcastChunked(tag, message) {
  const sockets = this.state.getWebSockets(tag);
  const CHUNK   = 100;

  for (let i = 0; i < sockets.length; i += CHUNK) {
    const batch = sockets.slice(i, i + CHUNK);
    for (const socket of batch) {
      try { socket.send(message); } catch {}
    }
    // Yield to the event loop between chunks to allow other messages to interleave
    await scheduler.yield();
  }
}
```

`scheduler.yield()` (available in Workers runtime 2024+) yields the current microtask queue, allowing other in-flight messages to be processed between broadcast chunks.

## Section 4 — Detecting and Evicting Zombie Connections

Mobile connections silently drop (airplane mode, background tab throttling, OS socket teardown) without sending a WebSocket close frame.  The DO holds these zombie connections indefinitely until it detects them.  Use **heartbeat pings** to identify and evict dead connections:

```javascript
// In fetch() — ensure heartbeat alarm is scheduled
async fetch(request) {
  // ... WebSocket upgrade logic from Section 1 ...

  // Schedule heartbeat if not already scheduled
  const alarmTime = await this.state.storage.getAlarm();
  if (alarmTime === null) {
    await this.state.storage.setAlarm(Date.now() + 30_000);
  }

  return new Response(null, { status: 101, webSocket: client });
}

// In webSocketMessage — track last pong receipt
async webSocketMessage(ws, message) {
  if (message === 'pong') {
    // Update last-seen timestamp in the attachment
    const attachment = ws.deserializeAttachment();
    ws.serializeAttachment({ ...attachment, lastPong: Date.now() });
    return;
  }
  // ... regular message handling ...
}

// Alarm fires every 30 s — ping all sockets, evict those that missed 2 pings
async alarm() {
  const now      = Date.now();
  const TIMEOUT  = 65_000;  // missed 2 × 30 s pings + buffer

  for (const socket of this.state.getWebSockets('room')) {
    const { lastPong } = socket.deserializeAttachment() ?? {};

    if (lastPong && now - lastPong > TIMEOUT) {
      // Zombie — close it
      try { socket.close(1001, 'heartbeat timeout'); } catch {}
    } else {
      // Alive (or first ping cycle) — send ping
      try { socket.send('ping'); } catch {}
    }
  }

  // Reschedule
  await this.state.storage.setAlarm(Date.now() + 30_000);
}
```

This pattern limits zombie connection hold-time to at most 65 seconds, preventing dead connections from accumulating in long-lived DOs.

## Anti-patterns

- **Calling `server.accept()` (standard mode) when you need hibernation** — standard mode keeps the DO in memory for the entire connection lifetime and is billed accordingly.  Always use `state.acceptWebSocket()` unless you have a specific reason not to.
- **Storing large objects in `serializeAttachment()`** — attachments are serialized to disk per-socket.  Large attachments (> 10 KB) inflate DO storage usage for every connected client.  Store large state in SQLite and keep the attachment as a lookup key.
- **Broadcasting inside `webSocketMessage` without error handling** — a single failed `socket.send()` (disconnected client) will throw and abort the entire broadcast.  Wrap every `send()` in a `try/catch`.
- **Not rescheduling alarms after eviction** — if the DO is evicted and the alarm fires during a period of no active connections, the DO wakes just for the alarm.  If you forget to reschedule, the heartbeat loop silently stops.
- **Using one DO instance for millions of connections** — a single DO is single-threaded.  A broadcast to 10,000 sockets takes real CPU time.  Shard large rooms into multiple DOs using consistent hashing on `roomId + shardIndex`.

## Gotchas

- `state.getWebSockets(tag)` is an O(n) scan over all sockets with that tag.  For rooms with thousands of connections, this scan runs on every message.  Benchmark your DO's broadcast latency as connection count scales.
- In hibernation mode, the DO constructor runs on **every message delivery** (the isolate is re-instantiated).  Keep the constructor fast — avoid any `await` in the constructor body that is not inside `blockConcurrencyWhile`.
- WebSocket message size limit: Workers runtime imposes a **1 MB** per-message limit (both send and receive).  Larger messages must be chunked at the application layer.
- `ws.close()` inside `webSocketClose` handler is a no-op if called after the socket is already closed — this is safe to call defensively.
- Tags must be strings of ≤ 256 bytes each, and a socket may have at most 10 tags.

## Verification

1. Connect 500 WebSocket clients to the DO using a load test tool (k6 or Artillery).  Set all clients to idle (no messages).  Verify that `wrangler tail` shows no CPU activity and no ongoing invocations during the idle period — confirming hibernation is active.
2. Kill 100 clients at the TCP level without sending a close frame (simulate mobile drop: `iptables -A INPUT -p tcp --sport <port> -j DROP`).  After 65 seconds, verify that `state.getWebSockets('room').length` has decreased by 100, confirming zombie eviction via heartbeat.
3. Benchmark broadcast latency: from 1 connected client, measure the time from sending a message to receiving the echo broadcast.  At 500 connected clients, this latency should stay under 50 ms if chunked broadcast with `scheduler.yield()` is applied.

## Related

- `durable-objects-low-latency-stateful.md` — DO fundamentals and storage API
- `durable-objects-memory-optimization.md` — memory management in long-lived DOs
- `websocket-sse-transport-performance.md` — WebSocket vs SSE transport selection
- `workers-cpu-time-optimization.md` — CPU budget and billing model
- `sse-vs-websockets-real-time-streaming.md` — choosing the right real-time transport

## Sources

- WebSocket Hibernation API: https://developers.cloudflare.com/durable-objects/api/websockets/
- Durable Objects best practices: https://developers.cloudflare.com/durable-objects/best-practices/
- Workers scheduler.yield(): https://developers.cloudflare.com/workers/runtime-apis/scheduler/
- WebSocket limits: https://developers.cloudflare.com/durable-objects/platform/limits/
