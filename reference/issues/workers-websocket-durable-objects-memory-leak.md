# Durable Object WebSocket Handler Leaks Memory When Connections Are Not Cleaned Up

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Durable Object that manages WebSocket connections grows its memory footprint steadily over time. Connections that were closed by the client or dropped due to network errors remain in an internal `Map`, preventing garbage collection. Eventually the Durable Object is evicted by the runtime or returns errors due to memory pressure, causing active clients to disconnect unexpectedly.

---

## Context

Durable Objects provide a natural home for WebSocket fan-out (chat rooms, live collaboration, presence). A common pattern is to keep a `Map<string, WebSocket>` of active connections so the Durable Object can broadcast messages. The memory leak occurs because `close` and `error` events on individual sockets are never handled, so the `Map` entries are never deleted. The Durable Object's runtime instance is kept alive as long as at least one WebSocket is open, which masks the leak until a large number of zombie entries accumulate. Cloudflare introduced the **WebSocket Hibernation API** specifically to address this problem: `ctx.acceptWebSocket()` lets the runtime serialize the Durable Object to disk between messages, automatically cleaning up dead sockets.

---

## Root Cause

WebSocket references are stored in a `Map` on `upgrade` but never removed when the socket closes or errors. The event listeners for `close` and `error` are missing, so zombie entries accumulate indefinitely.

```typescript
// BAD: WebSocket Map is never pruned — memory leak
import { DurableObject } from 'cloudflare:workers';

export class ChatRoom extends DurableObject {
  private sessions = new Map<string, WebSocket>();

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('Expected WebSocket', { status: 426 });
    }

    const { 0: client, 1: server } = new WebSocketPair();
    server.accept();

    const id = crypto.randomUUID();
    // Stored but NEVER removed
    this.sessions.set(id, server);

    server.addEventListener('message', (evt) => {
      this.broadcast(evt.data as string, id);
    });
    // Missing: 'close' and 'error' handlers that call this.sessions.delete(id)

    return new Response(null, { status: 101, webSocket: client });
  }

  private broadcast(message: string, senderId: string): void {
    for (const [id, ws] of this.sessions) {
      if (id !== senderId) {
        try {
          ws.send(message);
        } catch {
          // Socket is dead but still in the map — error swallowed silently
        }
      }
    }
  }
}
```

## Fix

Use the **WebSocket Hibernation API** (`ctx.acceptWebSocket()`) so the Cloudflare runtime manages socket lifecycle, memory, and eviction automatically. The Durable Object no longer needs to maintain its own `Map` of live sockets.

```typescript
// GOOD: Hibernation API — runtime manages socket lifecycle
import { DurableObject } from 'cloudflare:workers';

type SessionMeta = { userId: string };

export class ChatRoom extends DurableObject {
  // The runtime tracks sockets; we only need lightweight metadata
  // No Map<string, WebSocket> needed

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('Expected WebSocket', { status: 426 });
    }

    const userId = new URL(request.url).searchParams.get('userId') ?? 'anon';

    const { 0: client, 1: server } = new WebSocketPair();
    // Hand the server socket to the runtime; it handles hibernation + cleanup
    this.ctx.acceptWebSocket(server, { tags: [userId] });

    return new Response(null, { status: 101, webSocket: client });
  }

  // Called by the runtime when a message arrives (even after hibernation)
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const meta = this.ctx.getWebSockets().includes(ws)
      ? ws
      : null;
    if (!meta) return;

    // Broadcast to all currently active sockets managed by the runtime
    for (const peer of this.ctx.getWebSockets()) {
      if (peer !== ws) {
        peer.send(typeof message === 'string' ? message : new Uint8Array(message));
      }
    }
  }

  // Runtime calls this automatically when the socket closes
  async webSocketClose(ws: WebSocket, code: number, reason: string): Promise<void> {
    // Runtime has already removed the socket from getWebSockets()
    // Any per-socket cleanup (e.g., presence state) goes here
    ws.close(code, reason);
  }

  // Runtime calls this automatically on network error
  async webSocketError(ws: WebSocket, error: unknown): Promise<void> {
    console.error('WebSocket error:', error);
    ws.close(1011, 'Internal error');
  }
}
```

If you must maintain a manual `Map` for some reason (e.g., targeting specific sockets without hibernation), add explicit cleanup handlers:

```typescript
// Minimal manual fix — add close/error cleanup (less preferred than hibernation)
const cleanup = () => this.sessions.delete(id);
server.addEventListener('close', cleanup);
server.addEventListener('error', cleanup);
```

## Verification

```bash
# Deploy the updated Durable Object
npx wrangler deploy

# Open two WebSocket connections, close one, and check the runtime socket count
# (requires a /debug endpoint that returns this.ctx.getWebSockets().length)
curl -s https://my-worker.example.workers.dev/debug | jq '.activeSockets'
# Should return 1 after closing one of two connections; leaky code returns 2

# Observe memory in wrangler tail (look for eviction warnings)
npx wrangler tail my-worker --format pretty 2>&1 | grep -i 'evict\|memory\|oom'

# Soak test: open 500 connections, close them all, assert socket count returns to 0
for i in $(seq 1 500); do
  wscat -c wss://my-worker.example.workers.dev/ws --execute 'exit' &
done
wait
curl -s https://my-worker.example.workers.dev/debug | jq '.activeSockets'
```

---

## Anti-patterns

- **Storing `WebSocket` objects in a class-level `Map` without cleanup handlers** — The most common cause of this leak. Always pair every `sessions.set()` with a corresponding `sessions.delete()` in both `close` and `error` handlers.
- **Swallowing `ws.send()` errors in a broadcast loop** — A dead socket that throws on `send()` is a clear signal to remove it from the map; catch the error and call `sessions.delete(id)` rather than continuing silently.
- **Using `server.accept()` instead of `ctx.acceptWebSocket()`** — The legacy `accept()` path does not support hibernation. The Durable Object stays in memory for the entire connection lifetime and cannot be checkpointed between messages.
- **Tracking presence state in a plain JS `Set` instead of Durable Object storage** — After hibernation, in-memory state is lost. Use `this.ctx.storage.put()` for any state that must survive the hibernation cycle.

---

## Gotchas

- `ctx.getWebSockets()` returns only sockets accepted via `ctx.acceptWebSocket()`. Sockets accepted via the legacy `server.accept()` path are not visible to the hibernation API.
- After a Durable Object hibernates and wakes, the in-memory class fields (like a plain `Map`) are reset to their initial values. Persist any critical state to `this.ctx.storage` before returning from a handler.
- The hibernation API is available only in Durable Objects, not in plain Workers.
- Tags passed as the second argument to `ctx.acceptWebSocket()` survive hibernation and can be used with `ctx.getWebSockets(tag)` to target specific sockets after wake-up.
- WebSocket hibernation counts against Durable Object storage reads/writes on the metered plan when state is checkpointed.

---

## Related

- `workers-503-service-unavailable-subrequest-limit.md`
- `workers-cron-missed-execution-recovery.md`

---

## Sources

- Cloudflare Durable Objects WebSocket Hibernation API — https://developers.cloudflare.com/durable-objects/api/websockets/
- WebSocket Hibernation tutorial — https://developers.cloudflare.com/durable-objects/examples/websocket-hibernation-server/
- Durable Objects in-memory state and hibernation — https://developers.cloudflare.com/durable-objects/reference/in-memory-state/
