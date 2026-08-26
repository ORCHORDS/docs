# feature-cookbook-realtime

**Issue:** Realtime — WebSockets, SSE, long polling
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a chat app. The user sends a message. The
other user doesn't see it for 5 seconds. You poll. The
poll misses messages. You wish you had realtime.

## Root cause
**Polling is not realtime.** Use WebSockets, SSE, or
DOs.

**Source:** WebSocket RFC 6455.

## Realtime strategies

### Polling
- **How:** Client polls every N seconds
- **Pros:** Simple, works everywhere
- **Cons:** Latency, server load

### Long polling
- **How:** Client opens a connection; server holds
- **Pros:** Lower latency
- **Cons:** Server connections

### Server-Sent Events (SSE)
- **How:** Server pushes; client listens
- **Pros:** Simple, one-way
- **Cons:** One-way only

### WebSockets
- **How:** Bidirectional, full-duplex
- **Pros:** Real-time, bi-directional
- **Cons:** More complex

### Durable Objects (CF)
- **How:** Centralized state, WebSocket coordination
- **Pros:** Built for realtime
- **Cons:** CF-specific

For most apps, **SSE or DOs** is the right answer.

## The "SSE" pattern

For SSE:
```ts
// Server
async function handleSSE(request: Request, env: Env): Promise<Response> {
  const stream = new ReadableStream({
    start(controller) {
      // Send an initial event
      controller.enqueue(`data: ${JSON.stringify({ type: 'connected' })}\n\n`);

      // Send events as they happen
      setInterval(() => {
        controller.enqueue(`data: ${JSON.stringify({ type: 'update', value: Date.now() })}\n\n`);
      }, 1000);
    },
  });

  return new Response(stream, {
    headers: {
      'content-type': 'text/event-stream',
      'cache-control': 'no-cache',
    },
  });
}

// Client
const events = new EventSource('/api/events');
events.onmessage = (event) => {
  console.log(JSON.parse(event.data));
};
```

The SSE is one-way.

**Source:** MDN — SSE:
https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events

## The "WebSocket" pattern

For WebSocket:
```ts
// Server
async function handleWebSocket(request: Request, env: Env): Promise<Response> {
  const pair = new WebSocketPair();
  const [client, server] = Object.values(pair);

  server.accept();
  server.addEventListener('message', (event) => {
    // Echo back
    server.send(`Echo: ${event.data}`);
  });

  return new Response(null, { status: 101, webSocket: client });
}
```

The WebSocket is bi-directional.

**Source:** RFC 6455 — WebSocket:
https://datatracker.ietf.org/doc/html/rfc6455

## The "CF Durable Objects" pattern

For DOs + WebSocket:
```ts
export class ChatRoom {
  state: DurableObjectState;
  sessions: WebSocket[] = [];

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/websocket') {
      const pair = new WebSocketPair();
      const [client, server] = Object.values(pair);

      server.accept();
      this.sessions.push(server);

      server.addEventListener('message', (event) => {
        // Broadcast to all
        for (const session of this.sessions) {
          session.send(event.data);
        }
      });

      return new Response(null, { status: 101, webSocket: client });
    }

    return new Response('Not found', { status: 404 });
  }
}
```

The DO holds the connections.

**Source:** CF DO WebSocket:
https://developers.cloudflare.com/durable-objects/best-practices/websockets/

## The "presence" pattern

For presence (who's online):
```ts
// Server
async function trackPresence(userId: string, isOnline: boolean, env: Env): Promise<void> {
  await env.DB!.prepare(
    `UPDATE users SET last_seen_at = ? WHERE id = ?`
  ).bind(isOnline ? new Date().toISOString() : null, userId).run();
}

// Client: ping every 30s
setInterval(() => fetch('/api/presence', { method: 'POST' }), 30_000);
```

The presence is tracked.

## The "broadcast" pattern

For broadcast (one-to-many):
```ts
// Using DOs
class ChatRoom {
  sessions: WebSocket[] = [];

  broadcast(message: any): void {
    for (const session of this.sessions) {
      try {
        session.send(JSON.stringify(message));
      } catch (err) {
        // Dead connection
        this.sessions = this.sessions.filter(s => s !== session);
      }
    }
  }
}
```

The broadcast is one-to-many.

## The "fanout" pattern

For fanout (one-to-one with many users):
```ts
// 1. Get the recipients
const recipients = await env.DB!.prepare(
  `SELECT id FROM users WHERE tenant_id = ? AND id != ?`
).bind(tenantId, senderId).all();

// 2. Send to each
for (const recipient of recipients.results) {
  const doId = env.CHAT_ROOM.idFromName(recipient.id);
  const doStub = env.CHAT_ROOM.get(doId);
  await doStub.fetch(`https://example.com/send`, {
    method: 'POST',
    body: JSON.stringify({ from: senderId, message }),
  });
}
```

The fanout is per-recipient.

## The "reconnection" pattern

For reconnection, exponential backoff:
```ts
// Client
let attempts = 0;
function connect() {
  const ws = new WebSocket('wss://api.example.com/websocket');

  ws.addEventListener('close', () => {
    attempts++;
    setTimeout(connect, Math.min(2 ** attempts * 1000, 30_000));
  });

  ws.addEventListener('open', () => {
    attempts = 0;
  });
}
```

The client reconnects.

## The "heartbeat" pattern

For heartbeat (keep alive):
```ts
// Server
setInterval(() => {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'ping' }));
  }
}, 30_000);

// Client
ws.addEventListener('message', (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'ping') {
    ws.send(JSON.stringify({ type: 'pong' }));
  }
});
```

The heartbeat keeps the connection alive.

## The "realtime observability" pattern

For observability:
- **Connections:** How many?
- **Latency:** Message delivery time
- **Drop rate:** Lost messages
- **Errors:** Failed sends

```ts
metrics.gauge('realtime.connections', this.sessions.length, { room: this.name });
metrics.histogram('realtime.message_latency_ms', latency, { type: 'broadcast' });
```

The realtime is monitored.

## The "realtime anti-pattern" anti-patterns

### 1. Polling for realtime
- **Issue:** Latency, server load
- **Fix:** Use WebSocket or SSE

### 2. No heartbeat
- **Issue:** Connection dies silently
- **Fix:** Heartbeat ping/pong

### 3. No reconnection
- **Issue:** Disconnect = done
- **Fix:** Exponential backoff

### 4. No presence
- **Issue:** User doesn't know who's online
- **Fix:** Track presence

### 5. Memory leak
- **Issue:** Dead sessions accumulate
- **Fix:** Clean up on close

## Verification
- **Test:** Realtime works
- **Test:** Reconnection works
- **Test:** Heartbeat works
- **Live:** Realtime is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "polling for realtime" anti-pattern.** Use
  WebSocket.
- **The "no heartbeat" anti-pattern.** Add heartbeat.
- **The "no reconnection" anti-pattern.** Reconnect.

## Related
- `feature-cookbook-comms-channels.md`
- `cloudflare/durable-objects-patterns.md`
- `feature-cookbook-saga.md`
- CF WebSocket: https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- MDN WebSocket: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket
- RFC 6455: https://datatracker.ietf.org/doc/html/rfc6455
