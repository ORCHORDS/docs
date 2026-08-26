# durable-objects-websocket-hibernation

**Issue:** Handling thousands of WebSocket connections efficiently using DO WebSocket Hibernation API
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without hibernation, a Durable Object with open WebSocket connections stays fully alive (billing CPU duration) even when no messages are flowing. WebSocket Hibernation suspends the DO between messages, dramatically reducing cost for chat rooms, live dashboards, and collaboration tools.

## Pattern / Solution

```typescript
import { DurableObject } from 'cloudflare:workers';

export class ChatRoom extends DurableObject {
  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
  }

  async fetch(request: Request): Promise<Response> {
    const upgrade = request.headers.get('Upgrade');
    if (upgrade !== 'websocket') {
      return new Response('Expected WebSocket', { status: 426 });
    }

    // Accept via the Hibernation API (not new WebSocketPair())
    const [client, server] = Object.values(new WebSocketPair());

    // ctx.acceptWebSocket() enables hibernation for this socket
    this.ctx.acceptWebSocket(server, ['room', 'broadcast']); // optional tags

    return new Response(null, { status: 101, webSocket: client });
  }

  // Called when a message arrives — DO is woken from hibernation
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const text = typeof message === 'string' ? message : new TextDecoder().decode(message);
    const parsed = JSON.parse(text) as { type: string; body: string };

    if (parsed.type === 'broadcast') {
      // Get all connected sockets and broadcast
      const peers = this.ctx.getWebSockets('broadcast'); // filter by tag
      for (const peer of peers) {
        if (peer !== ws && peer.readyState === WebSocket.OPEN) {
          peer.send(JSON.stringify({ type: 'message', body: parsed.body }));
        }
      }
    }

    // Persist last activity
    await this.ctx.storage.put('lastActivity', Date.now());
  }

  // Called on close — DO woken from hibernation
  async webSocketClose(ws: WebSocket, code: number, reason: string): Promise<void> {
    console.log(`WebSocket closed: ${code} ${reason}`);
    ws.close(code, reason);
  }

  // Called on error
  async webSocketError(ws: WebSocket, error: unknown): Promise<void> {
    console.error('WebSocket error:', error);
    ws.close(1011, 'Internal error');
  }
}
```

**Attaching per-socket state:**
```typescript
// Store metadata on the socket itself (survives hibernation)
this.ctx.acceptWebSocket(server);
server.serializeAttachment({ userId, roomId });

// Retrieve in webSocketMessage
async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
  const { userId } = ws.deserializeAttachment() as { userId: string };
  // ...
}
```

## Gotchas
- Use `ctx.acceptWebSocket()` (Hibernation API) instead of `server.accept()` — they are mutually exclusive.
- `ctx.getWebSockets()` returns all sockets accepted in the current DO instance, including hibernated ones.
- Serialized attachment (`serializeAttachment`) data must be JSON-serializable and is limited to 2048 bytes.
- `webSocketMessage`, `webSocketClose`, and `webSocketError` are **class methods**, not event listeners.
- With hibernation, the DO **does not** stay awake between messages — do not use `setInterval` or expect in-memory timers to fire.
- Sending from `webSocketMessage` does not require the socket to be re-accepted; use the `ws` parameter directly.
- Regular (`non-hibernated`) DOs can handle ~32k concurrent WebSocket connections per instance; hibernated DOs scale further.

## Related
- `durable-objects-hibernation.md`
- `durable-objects-alarms.md`
- `workers-websocket-upgrade.md`
- `durable-objects-patterns.md`
